"""TODO."""

import datetime as dt
from decimal import Decimal
from enum import Enum, StrEnum, auto
from typing import Annotated, Any, Counter, Mapping, NamedTuple

from pydantic import BeforeValidator, ConfigDict
from pydantic.dataclasses import dataclass
from pydantic_extra_types.currency_code import ISO4217


def _empty_to_none(v: Any) -> Any:
    if isinstance(v, str) and v.strip() == "":
        return None
    return v

EmptyToNone = BeforeValidator(_empty_to_none)

class TransactionType(StrEnum):
    TRANSFER_OUT = "transfer_out"
    TRANSFER_IN = "transfer_in"
    REFUND = "refund"
    INCOME ="income"
    EXPENSE = "expense"

class Outcome(Enum):
    OK = auto()
    INVALID = auto()
    ERROR = auto()

@dataclass(frozen=True, slots=True, config=ConfigDict(str_strip_whitespace=True))
class Transaction:
    """Transaction data class."""
    transaction_id: str
    merchant: str
    category: str
    amount: Decimal
    currency: ISO4217
    account: str
    transaction_type: TransactionType
    date: Annotated[dt.date | None, EmptyToNone]
    related_transaction_id: str | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError(f"amount must be Decimal, got {type(self.amount).__name__}")
        if (
                self.transaction_type is TransactionType.EXPENSE
                and self.amount > 0
        ):
           raise ValueError("Expense amount must not be positive.")

        if (
                self.transaction_type is TransactionType.REFUND
                and self.amount < 0
        ):
           raise ValueError("Refund amount must not be negative.")


class Record(NamedTuple):
    """Represents a record from csv file."""
    dataset_id: str
    record_number: int             # 1-based index of the data record
    line_no: int                   # physical line where the record starts
    outcome: Outcome
    row: dict[str, str]
    raw:str
    transaction: Transaction | None = None
    error: Exception | None = None

    @property
    def source_row_id(self) -> str:
        return f"{self.dataset_id}:{self.record_number}"

    def has_missing_date(self) -> bool:
        return self.transaction is None or self.transaction.date is None

    def has_missing_category(self) -> bool:
        return self.transaction is not None and not self.transaction.category


_MAX_CURRENCIES = 5

def _top_counts(counts: Mapping[object, int], limit: int) -> str:
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    parts = [f"{key}: {n}" for key, n in ranked[:limit]]
    if len(ranked) > limit:
        parts.append(f"+{len(ranked) - limit} more")
    return "{" + ", ".join(parts) + "}"

def _short_id(s: str, width: int = 12) -> str:
    return s if len(s) <= width else s[:width] + "…"

def _date_span(start: dt.date | None, end: dt.date | None) -> str:
    return f"{start}..{end}" if start and end else "None"


class DatasetProfile(NamedTuple):
    """Represents the DatasetProfile result."""
    dataset_id: str
    columns: list[str]
    total_records: int
    outcome_counts: dict[Outcome, int]
    currency_counts: dict[ISO4217, int]
    earliest_date: dt.date|None
    latest_date: dt.date|None
    missing_dates: list[Transaction]
    missing_categories: list[Transaction]

    def __str__(self) -> str:
        outcomes = " · ".join(
            f"{o.name} {self.outcome_counts.get(o, 0):,}" for o in Outcome
        )
        currencies = _top_counts(self.currency_counts, _MAX_CURRENCIES).strip("{}")
        return (
            f"Dataset {_short_id(self.dataset_id)} "
            f"({self.total_records:,} records, {len(self.columns)} columns)\n"
            f"  Outcomes    {outcomes}\n"
            f"  Currencies  {currencies}\n"
            f"  Dates       {_date_span(self.earliest_date, self.latest_date)}\n"
            f"  Missing     dates {len(self.missing_dates):,} · "
            f"categories {len(self.missing_categories):,}"
        )

class QualityIssueType(StrEnum):
    VALIDATION_ERROR = "validation_error"
    RECORD_ERROR = "record_error"
    MISSING_DATE = "missing_date"
    MISSING_CATEGORY = "missing_category"
    EXACT_DUPLICATE = "exact_duplicate"

class QualityIssue(NamedTuple):
    """Represents QualityIssue result type"""
    issue_type: QualityIssueType
    source_row_ids: list[str]
    message: str
    def __str__(self) -> str:
        return f"[{self.issue_type}] source_row_id [{self.source_row_ids}] Message: [{self.message}]"

class ExclusionReason(StrEnum):
    VALIDATION_ERROR="validation_error"
    RECORD_ERROR="record_error"
    DUPLICATE_COPY="duplicate_copy"
    INCOME="income"
    TRANSFER="transfer"
    MISSING_DATE="missing_date"
    OUTSIDE_PERIOD="outside_period"

class ExcludedRecord(NamedTuple):
    source_row_id: str
    reason: ExclusionReason
    message: str

class SpendingSummary(NamedTuple):
    """Represents SpendingSummary result."""
    dataset_id:str
    start_date: dt.date | None
    end_date: dt.date | None
    gross_expenses: dict[tuple[str, ...], Decimal]
    refunds: dict[tuple[str, ...], Decimal]
    net_spending: dict[tuple[str, ...], Decimal]
    expense_count: int
    refund_count: int
    source_row_ids: list[str]
    excluded_record: list[ExcludedRecord]

    def __str__(self) -> str:
        zero = Decimal(0)
        columns = (self.gross_expenses, self.refunds, self.net_spending)
        keys = sorted(
            self.gross_expenses.keys() | self.refunds.keys() | self.net_spending.keys(),
            key=lambda k: (k[-1], *k[:-1]) if k else ("",),
            )
    
        def currency(key: tuple[str, ...]) -> str:
            return key[-1] if key else ""
    
        def group(key: tuple[str, ...]) -> str:
            return " / ".join(key[:-1]).strip() or "(uncategorized)"
    
        def money(value: Decimal) -> str:
            return f"{value:,.2f}"
    
        currencies = sorted({currency(k) for k in keys})
        header = ("Currency", "Group", "Gross", "Refunds", "Net")
        rows = [
            (currency(k), group(k), *(money(col.get(k, zero)) for col in columns))
            for k in keys
        ]
        totals = [
            (cur, "Total", *(money(sum((v for k, v in col.items() if currency(k) == cur), zero))
                             for col in columns))
            for cur in currencies
        ]
    
        widths = [max(len(row[i]) for row in (header, *rows, *totals)) for i in range(5)]
    
        def fmt(row: tuple[str, ...]) -> str:
            cur, grp, *nums = row
            return "  ".join([
                cur.ljust(widths[0]),
                grp.ljust(widths[1]),
                *(n.rjust(w) for n, w in zip(nums, widths[2:])),
            ])
    
        rule = "  ".join("-" * w for w in widths)
        lines = [
            "\n",
            fmt(header), rule, *map(fmt, rows), rule, *map(fmt, totals), "",
            f"{self.expense_count} expenses, {self.refund_count} refunds "
            f"from {len(self.source_row_ids)} source rows",
        ]
    
        if self.excluded_record:
            lines.extend(["", *self._format_excluded()])
    
        return "\n".join(lines)

    def _format_excluded(self) -> list[str]:
        excluded = self.excluded_record
        counts = Counter(e.reason for e in excluded)

        # Per-reason counts, in enum declaration order
        summary = ", ".join(
            f"{counts[reason]} {reason.value}"
            for reason in ExclusionReason
            if counts[reason]
        )

        header = ("Row ID", "Reason", "Message")
        rows = [
            (e.source_row_id, e.reason.value, e.message)
            for e in sorted(
                excluded,
                key=lambda e: (list(ExclusionReason).index(e.reason), e.source_row_id),
            )
        ]
        # Message is the last column, so it isn't padded
        widths = [max(len(row[i]) for row in (header, *rows)) for i in range(2)]

        def fmt(row: tuple[str, str, str]) -> str:
            rid, reason, msg = row
            return f"{rid.ljust(widths[0])}  {reason.ljust(widths[1])}  {msg}".rstrip()

        rule = f"{'-' * widths[0]}  {'-' * widths[1]}  {'-' * len(header[2])}"
        return [
            f"Excluded {len(excluded)} records: {summary}",
            "",
            fmt(header), rule, *map(fmt, rows),
        ]

