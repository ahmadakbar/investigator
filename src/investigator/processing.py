from collections import defaultdict
from datetime import date
from typing import Counter, Iterator, NoReturn

from investigator.schemas import (
    DatasetProfile,
    Outcome,
    QualityIssue,
    QualityIssueType,
    Record,
    Transaction,
)
from investigator.transaction_deck import TransactionDeck


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
        records: TransactionDeck
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

