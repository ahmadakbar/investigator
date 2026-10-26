"""TODO."""

import datetime as dt
from decimal import Decimal, InvalidOperation
from enum import Enum, StrEnum, auto
from typing import Annotated, Any, NamedTuple

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
        return f"{self.dataset_id}:{self.num}"


