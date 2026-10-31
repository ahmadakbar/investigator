from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from investigator.processing import summarize_spending
from investigator.schemas import ExclusionReason
from investigator.transaction_deck import TransactionDeck

COLUMNS = (
    "transaction_id,merchant,category,amount,currency,account,"
    "transaction_type,date,related_transaction_id,description"
)
EUR = ("EUR",)


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


def _reasons(summary):
    return sorted(e.reason for e in summary.excluded_record)


def test_expense_and_refund_give_gross_refunds_and_net(make_deck) -> None:
    deck = make_deck(
        "t1,Shop,groceries,-100,EUR,acc,expense,2024-01-10,,",
        "t2,Shop,groceries,20,EUR,acc,refund,2024-01-11,t1,",
    )

    s = summarize_spending(deck)

    assert s.gross_expenses == {EUR: Decimal(100)}
    assert s.refunds == {EUR: Decimal(20)}
    assert s.net_spending == {EUR: Decimal(80)}
    assert s.expense_count == 1
    assert s.refund_count == 1
    assert s.excluded_record == []


def test_identical_expenses_counted_once_and_copy_excluded(make_deck) -> None:
    row = "t1,Shop,groceries,-100,EUR,acc,expense,2024-01-10,,"
    deck = make_deck(row, row)

    s = summarize_spending(deck)

    assert s.gross_expenses == {EUR: Decimal(100)}
    assert s.expense_count == 1
    assert s.source_row_ids == [f"{deck.digest}:1"]
    assert [(e.source_row_id, e.reason) for e in s.excluded_record] == [
        (f"{deck.digest}:2", ExclusionReason.DUPLICATE_COPY),
    ]


def test_currencies_are_totalled_separately(make_deck) -> None:
    deck = make_deck(
        "t1,Shop,groceries,-100,EUR,acc,expense,2024-01-10,,",
        "t2,Shop,groceries,-20,USD,acc,expense,2024-01-11,,",
    )

    s = summarize_spending(deck)

    assert s.gross_expenses == {("EUR",): Decimal(100), ("USD",): Decimal(20)}
    assert s.net_spending == {("EUR",): Decimal(100), ("USD",): Decimal(20)}


def test_income_and_transfers_are_excluded(make_deck) -> None:
    deck = make_deck(
        "t1,Employer,salary,1000,EUR,acc,income,2024-01-01,,",
        "t2,Bank,transfer,-200,EUR,acc,transfer_out,2024-01-02,,",
        "t3,Bank,transfer,200,EUR,acc2,transfer_in,2024-01-02,t2,",
    )

    s = summarize_spending(deck)

    assert s.gross_expenses == {}
    assert s.refunds == {}
    assert s.net_spending == {}
    assert s.expense_count == s.refund_count == 0
    assert s.source_row_ids == []
    assert _reasons(s) == sorted(
        [ExclusionReason.INCOME, ExclusionReason.TRANSFER, ExclusionReason.TRANSFER]
    )


@pytest.fixture
def dated_deck(make_deck) -> TransactionDeck:
    return make_deck(
        "t1,Shop,groceries,-10,EUR,acc,expense,2024-01-10,,",
        "t2,Shop,groceries,-20,EUR,acc,expense,2024-02-10,,",
        "t3,Shop,groceries,-30,EUR,acc,expense,,,",
    )


def test_unfiltered_includes_undated(dated_deck) -> None:
    s = summarize_spending(dated_deck)

    assert s.gross_expenses == {EUR: Decimal(60)}
    assert s.excluded_record == []


def test_february_start_keeps_only_february(dated_deck) -> None:
    s = summarize_spending(dated_deck, start_date=date(2024, 2, 1))

    assert s.gross_expenses == {EUR: Decimal(20)}
    assert _reasons(s) == sorted(
        [ExclusionReason.OUTSIDE_PERIOD, ExclusionReason.MISSING_DATE]
    )


def test_january_end_keeps_only_january(dated_deck) -> None:
    s = summarize_spending(dated_deck, end_date=date(2024, 1, 31))

    assert s.gross_expenses == {EUR: Decimal(10)}
    assert _reasons(s) == sorted(
        [ExclusionReason.OUTSIDE_PERIOD, ExclusionReason.MISSING_DATE]
    )


@pytest.mark.parametrize(
    "row",
    [
        "t1,Shop,groceries,100,EUR,acc,expense,2024-01-10,,",   # positive expense
        "t1,Shop,groceries,-20,EUR,acc,refund,2024-01-10,,",    # negative refund
    ],
    ids=["positive_expense", "negative_refund"],
)
def test_sign_violations_excluded_as_validation_error(make_deck, row: str) -> None:
    deck = make_deck(row)

    s = summarize_spending(deck)

    assert s.gross_expenses == {}
    assert s.refunds == {}
    assert [(e.source_row_id, e.reason) for e in s.excluded_record] == [
        (f"{deck.digest}:1", ExclusionReason.VALIDATION_ERROR),
    ]


@pytest.mark.parametrize("header", [False, True], ids=["empty", "header_only"])
def test_empty_inputs_give_empty_summary(make_deck, header: bool) -> None:
    deck = make_deck(header=header)

    s = summarize_spending(deck)

    assert s.gross_expenses == s.refunds == s.net_spending == {}
    assert s.expense_count == s.refund_count == 0
    assert s.source_row_ids == []
    assert s.excluded_record == []
