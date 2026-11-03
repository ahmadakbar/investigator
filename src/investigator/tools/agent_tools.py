"""Tooling for agents."""
import threading
from datetime import date
from typing import Literal, assert_never

from langchain.tools import tool

from investigator.processing import check_quality, profile_dataset, summarize_spending
from investigator.reporting import to_jsonable


def make_tools(deck):
    """Investigator tooling for agents. They summarize spending, profile the dataset and check quality."""
    lock = threading.Lock()

    @tool
    def summarize_spending_tool(
            group_by: Literal["currency", "category", "month"],
            start_date: str | None = None,
            end_date: str | None = None,
    ) -> dict:
        """Summarize spending by "currency" or "category" or "month", with optional inclusive ISO dates."""
        match group_by:
            case "currency":
               k = None
            case "category":
               def k(t):
                   return (
                                  t.category,
                              )
            case "month":
               def k(t):
                   return (
                                   t.date.strftime("%Y-%m") if t.date is not None else "Undated",
                               )
            case _:
                assert_never(group_by)
        with lock:
            summary = summarize_spending(
                deck,
                start_date=date.fromisoformat(start_date) if start_date else None,
                end_date=date.fromisoformat(end_date) if end_date else None,
                key= k
            )
        return to_jsonable(summary)


    def profile_dataset_tool() -> dict:
        """Profile the transaction dataset."""
        with lock:
            df =  profile_dataset(deck)
        return to_jsonable(df)


    def check_quality_tool() -> list[dict]:
        """Quality check for the transaction dataset."""
        with lock:
            cq = check_quality(deck)
        return to_jsonable(cq)

    return [
        summarize_spending_tool,
        profile_dataset_tool,
        check_quality_tool,
    ]