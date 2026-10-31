import hashlib
from datetime import date
from pathlib import Path

import pytest

from investigator.processing import profile_dataset
from investigator.schemas import DatasetProfile, Outcome
from investigator.transaction_deck import TransactionDeck

COLUMNS = [
    "transaction_id",
    "merchant",
    "category",
    "amount",
    "currency",
    "account",
    "transaction_type",
    "date",
    "related_transaction_id",
    "description",
]

ROWS = [
    # OK
    "t1,Shop A,groceries,-10.50,EUR,acc1,expense,2024-01-15,,",
    # OK, latest date
    "t2,Shop B,dining,-20.00,USD,acc1,expense,2024-03-01,,",
    # OK, earliest date
    "t3,Shop C,groceries,5.00,EUR,acc2,refund,2023-12-31,t1,",
    # OK, missing date
    "t4,Shop D,travel,-7.00,EUR,acc1,expense,,,",
    # OK, missing category
    "t5,Shop E,,-3.00,GBP,acc1,expense,2024-02-10,,",
    # INVALID: expense with positive amount
    "t6,Shop F,groceries,9.99,EUR,acc1,expense,2024-01-20,,",
    # ERROR: wrong number of fields
    "t7,Shop G,groceries",
]


@pytest.fixture
def csv_path(tmp_path: Path) -> Path:
    path = tmp_path / "transactions.csv"
    path.write_text("\n".join([",".join(COLUMNS), *ROWS]) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def deck(csv_path: Path):
    with TransactionDeck(csv_path) as d:
        yield d


def test_profile_dataset(deck: TransactionDeck, csv_path: Path) -> None:
    profile = profile_dataset(deck)

    assert isinstance(profile, DatasetProfile)
    assert profile.dataset_id == hashlib.sha256(csv_path.read_bytes()).hexdigest()
    assert profile.columns == COLUMNS
    assert profile.total_records == len(ROWS)

    assert profile.outcome_counts == {
        Outcome.OK: 5,
        Outcome.INVALID: 1,
        Outcome.ERROR: 1,
    }
    # Only valid transactions contribute to currency counts.
    assert profile.currency_counts == {"EUR": 3, "USD": 1, "GBP": 1}

    assert profile.earliest_date == date(2023, 12, 31)
    assert profile.latest_date == date(2024, 3, 1)

    assert [tx.transaction_id for tx in profile.missing_dates] == ["t4"]
    assert [tx.transaction_id for tx in profile.missing_categories] == ["t5"]


def test_profile_dataset_empty(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    path.write_text(",".join(COLUMNS) + "\n", encoding="utf-8")

    with TransactionDeck(path) as deck:
        profile = profile_dataset(deck)

    assert profile.columns == COLUMNS
    assert profile.total_records == 0
    assert profile.outcome_counts == {}
    assert profile.currency_counts == {}
    assert profile.earliest_date is None
    assert profile.latest_date is None
    assert profile.missing_dates == []
    assert profile.missing_categories == []
