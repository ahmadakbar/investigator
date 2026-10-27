"""TODO."""

import datetime as dt
from decimal import Decimal, InvalidOperation
from enum import Enum, StrEnum, auto
from typing import Annotated, Any, Mapping, NamedTuple

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



class Record(NamedTuple):
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
    issue_type: QualityIssueType
    source_row_ids: list[str]
    message: str
    def __str__(self) -> str:
        return f"[{self.issue_type}] source_row_id [{self.source_row_ids}] Message: [{self.message}]"