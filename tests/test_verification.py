"""Exercise the real Python-to-Lean boundary and deliberate incorrect reports."""

import json
import os
import subprocess
import sys
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from investigator.processing import summarize_spending
from investigator.transaction_deck import TransactionDeck
from investigator.verification import (
    VerificationError,
    _decimal_parts,
    _request,
    _snapshot,
    _units,
    summarize_spending_verified,
    verify_spending_summary,
)

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = (
    "transaction_id,merchant,category,amount,currency,account,"
    "transaction_type,date,related_transaction_id,description"
)
EUR = ("EUR",)


@pytest.fixture
def make_deck(tmp_path):
    decks = []

    def make(*rows):
        path = tmp_path / f"data{len(decks)}.csv"
        path.write_text(COLUMNS + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
        deck = TransactionDeck(path)
        decks.append(deck)
        return deck

    yield make
    for deck in decks:
        deck.close()


@pytest.fixture
def checker():
    configured = os.environ.get("INVESTIGATOR_SPENDING_CHECKER")
    path = Path(configured) if configured else ROOT / "verification/spending/.lake/build/bin/spending_checker"
    if not path.is_file():
        pytest.skip("Build the real Lean checker with: cd verification/spending && lake build")
    return path.resolve()


@pytest.fixture
def example(make_deck):
    return make_deck(
        "e,Shop,food,-100.01,EUR,acc,expense,2024-01-10,,",
        "r,Shop,food,20,EUR,acc,refund,2024-01-11,e,",
    )


def test_integer_conversion_ignores_decimal_context():
    value = Decimal("123456789012345678901234567890.0012300")
    with localcontext() as context:
        context.prec = 3
        assert _decimal_parts(value) == (12345678901234567890123456789000123, -5)
        assert _units(value, -5) == 12345678901234567890123456789000123
        assert _units(Decimal("-0.000"), -5) == 0


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_conversion_is_rejected(value):
    with pytest.raises(VerificationError, match="finite"):
        _units(Decimal(value), -2)


def test_unrepresentable_summary_precision_is_rejected():
    with pytest.raises(VerificationError, match="precision"):
        _units(Decimal("1.001"), -2)


def test_request_contains_all_records_and_exact_fields(example):
    summary = summarize_spending(example)
    request = _request(_snapshot(example), summary, None, None)
    assert request["protocolVersion"] == 1
    assert [row["amount"] for row in request["records"]] == [-10001, 2000]
    assert request["claim"]["totals"][0]["net"] == 8001
    assert request["records"][0]["day"] == date(2024, 1, 10).toordinal()
    assert json.loads(request["records"][0]["fingerprint"]) == [list(pair) for pair in sorted(example[0].row.items())]


@pytest.mark.parametrize("failure", ["missing", "timeout", "malformed", "rejected", "wrong_version", "nonzero"])
def test_process_failures_never_release_a_summary(example, monkeypatch, failure):
    def fake_run(*args, **kwargs):
        if failure == "missing":
            raise FileNotFoundError("not built")
        if failure == "timeout":
            raise subprocess.TimeoutExpired("checker", 1)
        response = {"protocolVersion": 1, "accepted": True}
        if failure == "rejected":
            response["accepted"] = False
        if failure == "wrong_version":
            response["protocolVersion"] = 2
        stdout = "not JSON" if failure == "malformed" else json.dumps(response)
        return subprocess.CompletedProcess(args[0], 1 if failure == "nonzero" else 0, stdout, "")

    monkeypatch.setattr("investigator.verification.subprocess.run", fake_run)
    with pytest.raises(VerificationError):
        summarize_spending_verified(example, checker="unused")


def test_verified_wrapper_uses_one_snapshot(example, checker, monkeypatch):
    original_iter = TransactionDeck.__iter__
    calls = 0

    def counted_iter(self):
        nonlocal calls
        calls += 1
        return original_iter(self)

    monkeypatch.setattr(TransactionDeck, "__iter__", counted_iter)
    summary = summarize_spending_verified(example, checker=checker)
    assert summary.net_spending == {EUR: Decimal("80.01")}
    assert calls == 1


@pytest.mark.parametrize(
    "start,end,expected_indexes",
    [
        (None, None, [1, 3, 4, 5]),
        (date(2024, 1, 10), date(2024, 1, 11), [1, 3]),
        (date(2024, 2, 1), None, [4]),
        (None, date(2024, 1, 10), [1]),
        (date(2025, 1, 1), date(2025, 12, 31), []),
    ],
)
def test_selection_dedup_dates_and_bad_records(make_deck, checker, start, end, expected_indexes):
    expense = "e,Shop,food,-10,EUR,acc,expense,2024-01-10,,"
    deck = make_deck(
        expense,
        expense,
        "r,Shop,food,2,EUR,acc,refund,2024-01-11,e,",
        "u,Shop,food,-3,USD,acc,expense,2024-02-10,,",
        "n,Shop,,-4,EUR,acc,expense,,,",
        "i,Employer,salary,100,EUR,acc,income,2024-01-10,,",
        "bad,Shop,food,1,EUR,acc,expense,2024-01-10,,",
        "broken,row",
        "t,Bank,transfer,-10,EUR,acc,transfer_out,2024-01-10,,",
        "v,Bank,transfer,10,EUR,acc,transfer_in,2024-01-10,,",
    )
    summary = summarize_spending_verified(deck, start_date=start, end_date=end, checker=checker)
    assert summary.source_row_ids == [f"{deck.digest}:{i}" for i in expected_indexes]


def test_duplicate_identity_uses_all_raw_fields(make_deck, checker):
    deck = make_deck(
        "same,Shop,food,-10,EUR,acc,expense,2024-01-10,,first",
        "same,Shop,food,-10,EUR,acc,expense,2024-01-10,,different",
    )
    summary = summarize_spending_verified(deck, checker=checker)
    assert summary.expense_count == 2
    assert summary.net_spending == {EUR: Decimal(20)}


def test_three_decimal_currency_and_negative_net(make_deck, checker):
    deck = make_deck(
        "e,Shop,food,-12.345,KWD,acc,expense,2024-01-10,,",
        "r,Shop,food,13.005,KWD,acc,refund,2024-01-11,e,",
        "j,Shop,food,-100,JPY,acc,expense,2024-01-11,,",
    )
    summary = summarize_spending_verified(deck, checker=checker)
    assert summary.net_spending == {("KWD",): Decimal("-0.660"), ("JPY",): Decimal(100)}


def test_empty_deck_passes(make_deck, checker):
    assert summarize_spending_verified(make_deck(), checker=checker).net_spending == {}


@pytest.mark.parametrize("mutation", ["gross", "refunds", "net", "count", "source", "order", "dataset", "query"])
def test_real_lean_rejects_tampered_claims(example, checker, mutation):
    summary = summarize_spending(example)
    if mutation == "gross":
        summary = summary._replace(gross_expenses={EUR: Decimal("101.01")})
    elif mutation == "refunds":
        summary = summary._replace(refunds={EUR: Decimal("21")})
    elif mutation == "net":
        summary = summary._replace(net_spending={EUR: Decimal("80.02")})
    elif mutation == "count":
        summary = summary._replace(expense_count=2)
    elif mutation == "source":
        summary = summary._replace(source_row_ids=[f"{example.digest}:999"])
    elif mutation == "order":
        summary = summary._replace(source_row_ids=list(reversed(summary.source_row_ids)))
    elif mutation == "dataset":
        summary = summary._replace(dataset_id="another-dataset")
    elif mutation == "query":
        summary = summary._replace(start_date=date(2024, 1, 1))
    with pytest.raises(VerificationError, match="does not match"):
        verify_spending_summary(example, summary, checker=checker)


def test_zero_expense_entry_presence_is_checked(make_deck, checker):
    deck = make_deck(
        "e,Shop,food,0,EUR,acc,expense,2024-01-10,,",
        "r,Shop,food,0,EUR,acc,refund,2024-01-11,e,",
    )
    summary = summarize_spending_verified(deck, checker=checker)
    with pytest.raises(VerificationError):
        verify_spending_summary(deck, summary._replace(gross_expenses={}), checker=checker)


def test_decimal_arithmetic_rounding_is_detected(make_deck, checker):
    deck = make_deck(
        "e,Shop,food,-12345.67,EUR,acc,expense,2024-01-10,,",
        "r,Shop,food,0.001,EUR,acc,refund,2024-01-11,e,",
    )
    with localcontext() as context:
        context.prec = 6
        with pytest.raises(VerificationError):
            summarize_spending_verified(deck, checker=checker)


def test_grouped_summary_is_outside_this_checker(example, checker):
    grouped = summarize_spending(example, key=lambda transaction: (transaction.category,))
    with pytest.raises(VerificationError, match="currency-only"):
        verify_spending_summary(example, grouped, checker=checker)


def test_native_wire_rejects_malformed_json_and_unknown_versions(example, checker):
    malformed = subprocess.run([str(checker)], input="{\n", capture_output=True, text=True, check=False)
    assert malformed.returncode == 2
    assert json.loads(malformed.stdout)["accepted"] is False
    request = _request(_snapshot(example), summarize_spending(example), None, None)
    request["protocolVersion"] = 999
    unsupported = subprocess.run([str(checker)], input=json.dumps(request) + "\n", capture_output=True, text=True, check=False)
    assert unsupported.returncode == 1
    assert json.loads(unsupported.stdout)["accepted"] is False


def test_verified_cli_writes_json(example, checker, tmp_path):
    destination = tmp_path / "verified.json"
    result = subprocess.run(
        [sys.executable, "-m", "investigator.verification", str(example.path), "--checker", str(checker), "--output", str(destination)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(destination.read_text())["net_spending"] == [{"key": ["EUR"], "value": "80.01"}]
