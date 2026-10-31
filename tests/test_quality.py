from pathlib import Path

import pytest

from investigator.processing import check_quality
from investigator.schemas import QualityIssueType
from investigator.transaction_deck import TransactionDeck

COLUMNS = (
    "transaction_id,merchant,category,amount,currency,account,"
    "transaction_type,date,related_transaction_id,description"
)


@pytest.fixture
def make_deck(tmp_path: Path):
    decks: list[TransactionDeck] = []

    def _make(*rows: str, header: bool = True) -> TransactionDeck:
        path = tmp_path / f"tx{len(decks)}.csv"
        lines = ([COLUMNS] if header else []) + list(rows)
        path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
        deck = TransactionDeck(path)
        decks.append(deck)
        return deck

    yield _make
    for d in decks:
        d.close()


def _issues_by_type(issues):
    return {(i.issue_type, tuple(i.source_row_ids)) for i in issues}


def test_clean_records_have_no_issues(make_deck) -> None:
    deck = make_deck(
        "t1,Shop,groceries,-100,EUR,acc,expense,2024-01-10,,",
        "t2,Shop,groceries,20,EUR,acc,refund,2024-01-11,t1,",
    )
    assert check_quality(deck) == []


def test_identical_records_reported_as_one_duplicate_issue(make_deck) -> None:
    row = "t1,Shop,groceries,-100,EUR,acc,expense,2024-01-10,,"
    deck = make_deck(row, row)
    rid = deck.digest

    issues = check_quality(deck)

    assert len(issues) == 1
    assert issues[0].issue_type is QualityIssueType.EXACT_DUPLICATE
    assert issues[0].source_row_ids == [f"{rid}:1", f"{rid}:2"]


@pytest.mark.parametrize(
    "row",
    [
        "t1,Shop,groceries,100,EUR,acc,expense,2024-01-10,,",   # positive expense
        "t1,Shop,groceries,-20,EUR,acc,refund,2024-01-10,,",    # negative refund
    ],
    ids=["positive_expense", "negative_refund"],
)
def test_sign_violations_are_validation_errors(make_deck, row: str) -> None:
    deck = make_deck(row)

    issues = check_quality(deck)

    assert _issues_by_type(issues) == {
        (QualityIssueType.VALIDATION_ERROR, (f"{deck.digest}:1",)),
    }


def test_malformed_row_is_record_error(make_deck) -> None:
    deck = make_deck("t1,Shop,groceries")

    issues = check_quality(deck)

    assert _issues_by_type(issues) == {
        (QualityIssueType.RECORD_ERROR, (f"{deck.digest}:1",)),
    }


def test_missing_category_and_date_give_two_issues_for_same_record(make_deck) -> None:
    deck = make_deck("t1,Shop,,-100,EUR,acc,expense,,,")
    rid = (f"{deck.digest}:1",)

    issues = check_quality(deck)

    assert len(issues) == 2
    assert _issues_by_type(issues) == {
        (QualityIssueType.MISSING_CATEGORY, rid),
        (QualityIssueType.MISSING_DATE, rid),
    }


@pytest.mark.parametrize("header", [False, True], ids=["empty", "header_only"])
def test_empty_inputs_have_no_issues(make_deck, header: bool) -> None:
    deck = make_deck(header=header)
    assert len(deck) == 0
    assert check_quality(deck) == []
