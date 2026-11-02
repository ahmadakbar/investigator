"""Verify currency-only Python summaries with the proved Lean spending checker.

Run ``python -m investigator.verification --help`` for the standalone command.
The input adapter and the compiled checker remain trusted components; see the
accompanying verification README for the exact scope of the theorem.
"""

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, cast, overload

from investigator.processing import summarize_spending
from investigator.schemas import Outcome, Record, SpendingSummary
from investigator.transaction_deck import TransactionDeck, load_transactions


class VerificationError(RuntimeError):
    """Report a rejected summary or an unavailable verification service."""


@dataclass(frozen=True)
class _Snapshot(Sequence[Record]):
    digest: str
    records: tuple[Record, ...]

    def __len__(self) -> int:
        return len(self.records)

    def __iter__(self) -> Iterator[Record]:
        return iter(self.records)

    @overload
    def __getitem__(self, index: int) -> Record: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[Record, ...]: ...

    def __getitem__(self, index: int | slice) -> Record | tuple[Record, ...]:
        return self.records[index]


def _decimal_parts(value: Decimal) -> tuple[int, int]:
    """Extract an exact coefficient/exponent without using decimal arithmetic."""
    if not isinstance(value, Decimal) or not value.is_finite():
        raise VerificationError("Verification requires finite Decimal amounts.")
    sign, digits, exponent = value.as_tuple()
    coefficient = 0
    for digit in digits:
        coefficient = coefficient * 10 + digit
    if coefficient == 0:
        return 0, 0
    exponent = cast(int, exponent)
    while coefficient % 10 == 0:
        coefficient //= 10
        exponent += 1
    return (-coefficient if sign else coefficient), exponent


def _units(value: Decimal, exponent: int) -> int:
    coefficient, actual_exponent = _decimal_parts(value)
    if coefficient == 0:
        return 0
    shift = actual_exponent - exponent
    if shift < 0:
        raise VerificationError("Summary amount has precision absent from its inputs.")
    return coefficient * 10**shift


def _ordinal(value: date | None) -> int | None:
    return value.toordinal() if value is not None else None


def _snapshot(deck: TransactionDeck | _Snapshot) -> _Snapshot:
    if isinstance(deck, _Snapshot):
        return deck
    return _Snapshot(deck.digest, tuple(deck))


def _request(
    deck: _Snapshot,
    summary: SpendingSummary,
    start_date: date | None,
    end_date: date | None,
) -> dict[str, Any]:
    # Choose one exact integer unit per currency from all validated inputs.
    # This handles 0, 2, 3, or more decimal places without imposing rounding.
    exponents: dict[str, int] = {}
    for record in deck:
        if record.dataset_id != deck.digest:
            raise VerificationError("Input record belongs to a different dataset.")
        if record.outcome == Outcome.OK:
            if record.transaction is None:
                raise VerificationError("An OK record has no validated transaction.")
            transaction = record.transaction
            _, exponent = _decimal_parts(transaction.amount)
            currency = str(transaction.currency)
            exponents[currency] = min(exponents.get(currency, exponent), exponent)

    records = []
    for record in deck:
        transaction = record.transaction if record.outcome == Outcome.OK else None
        currency = str(transaction.currency) if transaction is not None else ""
        records.append({
            "sourceRowId": record.source_row_id,
            # A canonical representation of all parsed raw fields, not a hash.
            # Equality matches frozenset(record.row.items()) in the Python core.
            "fingerprint": json.dumps(sorted(record.row.items()), ensure_ascii=False, separators=(",", ":")),
            "status": record.outcome.value,
            "kind": transaction.transaction_type.value if transaction is not None else "",
            "currency": currency,
            "amount": _units(transaction.amount, exponents[currency]) if transaction is not None else 0,
            "day": _ordinal(transaction.date) if transaction is not None else None,
        })

    gross, refunds, net = summary.gross_expenses, summary.refunds, summary.net_spending
    keys = set(gross) | set(refunds)
    if set(net) != keys:
        raise VerificationError("Net-spending keys do not match gross/refund keys.")
    if any(not isinstance(key, tuple) or len(key) != 1 or not isinstance(key[0], str) for key in keys):
        raise VerificationError("This checker accepts currency-only summaries (key=None).")

    totals = []
    for key in sorted(keys):
        currency = key[0]
        if currency not in exponents:
            raise VerificationError("Summary contains a currency absent from its inputs.")
        exponent = exponents[currency]
        totals.append({
            "currency": currency,
            "gross": _units(gross.get(key, Decimal(0)), exponent),
            "refunds": _units(refunds.get(key, Decimal(0)), exponent),
            "net": _units(net[key], exponent),
            "hasExpenses": key in gross,
            "hasRefunds": key in refunds,
        })

    return {
        "protocolVersion": 1,
        "datasetId": deck.digest,
        "query": {"startDay": _ordinal(start_date), "endDay": _ordinal(end_date)},
        "records": records,
        "claim": {
            "datasetId": summary.dataset_id,
            "startDay": _ordinal(summary.start_date),
            "endDay": _ordinal(summary.end_date),
            "totals": totals,
            "sourceRowIds": summary.source_row_ids,
            "expenseCount": summary.expense_count,
            "refundCount": summary.refund_count,
        },
    }


def _checker_path(checker: str | Path | None) -> Path:
    configured = checker if checker is not None else os.environ.get("INVESTIGATOR_SPENDING_CHECKER")
    if configured is not None:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "verification/spending/.lake/build/bin/spending_checker"


def verify_spending_summary(
    deck: TransactionDeck,
    summary: SpendingSummary,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    checker: str | Path | None = None,
    timeout: float = 30,
) -> None:
    """Raise unless Lean accepts a currency summary against the supplied inputs.

    Pass the requested date bounds independently of the claimed summary. This
    function verifies totals, key presence, counts, contributing IDs, dataset
    ID, and date-bound metadata. Exclusion messages/reasons are outside scope.
    """
    request = _request(_snapshot(deck), summary, start_date, end_date)
    executable = _checker_path(checker)
    try:
        completed = subprocess.run(
            [str(executable)],
            input=json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise VerificationError("Lean spending verification timed out.") from error
    except OSError as error:
        raise VerificationError(
            f"Cannot run Lean checker at {executable}. Build it in verification/spending with 'lake build'."
        ) from error

    try:
        response = json.loads(completed.stdout)
    except (ValueError, TypeError) as error:
        raise VerificationError("Lean checker did not return a JSON verdict.") from error
    if (
        not isinstance(response, dict)
        or response.get("protocolVersion") != 1
        or response.get("accepted") is not True
        or completed.returncode != 0
    ):
        message = response.get("message", response.get("error", "invalid checker verdict")) if isinstance(response, dict) else "invalid checker verdict"
        raise VerificationError(f"Lean spending verification failed: {message}")


def summarize_spending_verified(
    deck: TransactionDeck,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    checker: str | Path | None = None,
    timeout: float = 30,
) -> SpendingSummary:
    """Calculate using the existing Python core and return only a checked result."""
    snapshot = _snapshot(deck)
    # The existing function requires only Sequence[Record] and .digest. Its
    # annotation says TransactionDeck; this immutable view supplies that exact
    # interface, so Python and Lean receive the same single-read snapshot.
    summary = summarize_spending(cast(TransactionDeck, snapshot), start_date=start_date, end_date=end_date)
    verify_spending_summary(
        cast(TransactionDeck, snapshot), summary,
        start_date=start_date, end_date=end_date, checker=checker, timeout=timeout,
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    """Write a Lean-checked currency summary as JSON."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--checker", type=Path, help="Path to the compiled spending_checker binary")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        with load_transactions(args.csv) as deck:
            summary = summarize_spending_verified(
                deck, start_date=args.start_date, end_date=args.end_date, checker=args.checker,
            )
        from investigator.reporting import _dumps, write_json

        if args.output is None:
            sys.stdout.write(_dumps(summary) + "\n")
        else:
            write_json(summary, args.output)
    except (OSError, ValueError, VerificationError) as error:
        sys.stderr.write(f"Verification failed: {error}\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
