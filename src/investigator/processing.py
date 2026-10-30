import logging
from collections import defaultdict
from collections.abc import Hashable
from datetime import date
from decimal import Decimal
from typing import Callable, Counter, Iterator, NoReturn, Sequence

from pydantic_extra_types.currency_code import ISO4217

from investigator.schemas import (
    DatasetProfile,
    Outcome,
    QualityIssue,
    QualityIssueType,
    Record,
    SpendingSummary,
    Transaction,
    TransactionType,
)
from investigator.transaction_deck import TransactionDeck

logger = logging.getLogger(__name__)
def profile_dataset(deck: TransactionDeck) -> DatasetProfile:
    """Profile the transaction dataset."""
    earliest_date, lastest_date, missing_dates = _get_date_coverage(deck)
    missing_categories = _find_uncategorized_transactions(deck)

    return DatasetProfile(
        deck.digest,
        deck.fieldnames,
        len(deck),
        dict(Counter(r.outcome for r in deck)),
        dict(Counter(
            tx.currency
            for r in deck
            if (tx := r.transaction) is not None
            if  tx.currency is not None)
        ),
        earliest_date,
        lastest_date,
        list(missing_dates),
        list(missing_categories)
    )


def _find_uncategorized_transactions(deck: TransactionDeck) -> Iterator[Transaction]:
    missing_categories = (
        tx
        for r in deck
        if (tx := r.transaction) is not None
        if not tx.category)
    return missing_categories


def _get_date_coverage(deck: TransactionDeck) -> tuple[date | None, date | None, Iterator[Transaction]]:
    valid_dates = list(
        d
        for r in deck
        if (tx := r.transaction) is not None
        if (d := tx.date) is not None)
    earliest_date = min(valid_dates, default=None)
    lastest_date = max(valid_dates, default=None)
    missing_dates: Iterator[Transaction] = (
        tx
        for r in deck
        if (tx := r.transaction) is not None
        if tx.date is None)
    return earliest_date, lastest_date, missing_dates


def _assert_never(value: NoReturn) -> NoReturn:
    raise AssertionError(f"Unhandled enum member: {value}")


def check_quality(deck: TransactionDeck) -> list[QualityIssue]:
    """Quality check for the transaction dataset."""
    issues:list[QualityIssue] =[]
    for t in deck:
        match t.outcome:
            case Outcome.OK:
                 is_category_missing = t.has_missing_category()
                 is_date_missing = t.has_missing_date()
                 if is_category_missing:
                    issues.append(QualityIssue(QualityIssueType.MISSING_CATEGORY, [t.source_row_id], "Transaction category is missing."))
                 if is_date_missing:
                     issues.append(QualityIssue(QualityIssueType.MISSING_DATE, [t.source_row_id], "Transaction date is missing."))
            case Outcome.ERROR:
                issues.append(QualityIssue(QualityIssueType.RECORD_ERROR, [t.source_row_id], str(t.error)))
            case Outcome.INVALID:
                 issues.append(QualityIssue(QualityIssueType.VALIDATION_ERROR, [t.source_row_id], str(t.error)))
            case unhandled:
                # If you add an Outcome.BLAH tomorrow,
                # type checkers will throw a compile error right here.
                _assert_never(unhandled)
    grp,_ =_partition_valid_records(deck)
    for g in grp:
        if len(g)>1:
            issues.append(QualityIssue(QualityIssueType.EXACT_DUPLICATE, [ s.source_row_id for s in g], "Duplicate Entry."))
    return issues


def _partition_valid_records(
        records: Sequence[Record]
) -> tuple[list[list[Record]], list[Record]]:

    # Step 1: Separate records into OK and Bad buckets
    valid_records: list[Record] = []
    bad_records: list[Record] = []

    for r in records:
        # Assuming Outcome is an Enum or String where "Invalid"/"Error" are bad states
        if r.outcome in ("Invalid", "Error") or r.outcome.name in ("INVALID", "ERROR"):
            bad_records.append(r)
        else:
            valid_records.append(r)

    # Step 2: Partition the remaining valid records by the target column value
    partitions_map = defaultdict(list)

    for r in valid_records:
        if not r.row:
            # Handle empty dict or None edge cases as a standalone partition
            partitions_map[None].append(r)
            continue

        # Convert the dictionary into a frozenset of key-value pairs.
        # This acts as an immutable snapshot of all columns and values,
        # allowing it to be securely hashed and compared in O(1) time.
        row_fingerprint = frozenset(r.row.items())

        partitions_map[row_fingerprint].append(r)


    # Convert our grouped dictionary values back into a clean list of lists
    valid_partitions = list(partitions_map.values())

    return valid_partitions, bad_records


def summarize_spending[K:Hashable](
        deck: TransactionDeck,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        key: Callable[[Transaction], K]|None = None,) -> SpendingSummary:
    """Summarize spending from the transaction dataset."""
    records = _records_from_a_period(deck, end_date, start_date)

    valid_records, _ = _partition_valid_records(records)

    return _get_spending(valid_records, key)



def _get_spending[K:Hashable](valid_records: list[list[Record]], key: Callable[[Transaction], K] | None, ) -> SpendingSummary:
    gross_by_keys: defaultdict[tuple[str, ...], Decimal] = defaultdict(Decimal)
    refunds_by_keys: defaultdict[tuple[str, ...], Decimal] = defaultdict(Decimal)
    expense_count = 0
    refunds_count = 0
    source_row_ids = []

    for r in valid_records:
        trans = r[0].transaction
        if trans is not None:
            match trans.transaction_type:
                case TransactionType.EXPENSE:
                    if key is None:
                         m = (trans.currency,)
                    else:
                        m = (key(trans), trans.currency)
                    gross_by_keys[m] -= trans.amount
                    expense_count += 1
                    source_row_ids.append(r[0].source_row_id)
                case TransactionType.REFUND:
                    if key is None:
                        m = (trans.currency,)
                    else:
                        m = (key(trans), trans.currency)
                    refunds_by_keys[m] += trans.amount
                    refunds_count += 1
                    source_row_ids.append(r[0].source_row_id)
                case _:
                    logger.debug("skipping other transactions")
    keys = gross_by_keys.keys() | refunds_by_keys.keys()

    net_by_keys: dict[tuple[str, ...], Decimal] = {
        k: gross_by_keys.get(k, Decimal(0)) - refunds_by_keys.get(k, Decimal(0))
        for k in keys
    }
    return SpendingSummary(
        gross_by_keys, refunds_by_keys, net_by_keys, expense_count, refunds_count, source_row_ids)


def _records_from_a_period(deck: TransactionDeck, end_date: date | None, start_date: date | None) -> Sequence[Record]:
    if start_date is None and end_date is not None:
        records = [
            r for r in deck
            if (t := r.transaction) is not None
               and (d := t.date) is not None
               and d <= end_date
        ]
    elif start_date is not None and end_date is None:
        records = [
            r for r in deck
            if (t := r.transaction) is not None
               and (d := t.date) is not None
               and start_date <= d
        ]
    elif start_date is not None and end_date is not None:
        records = [
            r for r in deck
            if (t := r.transaction) is not None
               and (d := t.date) is not None
               and start_date <= d <= end_date
        ]
    else:
        records = deck
    return records
