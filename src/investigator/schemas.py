"""TODO."""

import datetime as dt
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Annotated, Any

import pycountry
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






