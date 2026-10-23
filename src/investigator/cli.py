"""TODO."""
import argparse
import csv
import logging
import sys
from enum import Enum, auto
from pathlib import Path
from typing import Iterator

from pydantic import ValidationError

from investigator.schemas import Transaction

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)


def cmd_analyze(args):
    """:param args:"""
    logger.info(f"analyze {args.csv} question={args.question!r}")
    ts = load_transactions(args.csv)
    for rec in ts:
       logger.info(rec)


class Outcome(Enum):
    OK = auto()
    INVALID = auto()
    ERROR = auto()

def load_transactions(path: str | Path) -> Iterator[tuple[Outcome, object]] :
    """Load and convert a transaction from a file.

    :param path: str | Path
    :return: Iterator[Transaction]

    """
    with open(path, newline="", encoding="utf-8") as f:
        for line_no, row in enumerate(csv.DictReader(f), start=2):
            try:
                 tx = Transaction(**row)
            except ValidationError as e:
                yield Outcome.INVALID, (row, e)
                logger.error(f"line {line_no}: {e}")
            except Exception as e:
                logger.error(f"line {line_no}: {e}")
                yield Outcome.ERROR, (row, e)
            else:
                yield Outcome.OK, tx
def cmd_evaluate(args):
    """:param args:"""
    pass


def cmd_improve(args):
    """:param args:"""
    pass


def cmd_compare(args):
    """:param args:"""
    pass


def cmd_promote(args):
    """:param args:"""
    pass


def cmd_rollback(args):
    """:param args:"""
    pass


def cmd_resume(args):
    """:param args:"""
    pass


def positive_int(value: str) -> int:
    """:param value:
    :return:
    """  # noqa: D205
    n = int(value)
    if n <= 0:
        raise argparse.ArgumentTypeError(f"{n} must be > 0")
    return n


def existing_file(value: str) -> Path:
    """:param value:
    :return:
    """  # noqa: D205
    path = Path(value)
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"file not found: {value}")
    return path


def build_parser() -> argparse.ArgumentParser:
    """:return:"""
    parser = argparse.ArgumentParser(
        prog="investigator",
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sub = parser.add_subparsers(
        title="commands", dest="command", metavar="COMMAND", required=True
    )

    ## python investigator analyze transactions.csv --question "Explain the spending changes"
    p = sub.add_parser("analyze", help="analyze a transactions CSV")
    p.add_argument("csv", type=existing_file, help="path to the transactions CSV")
    p.add_argument(
        "-q", "--question", required=True, help="question to answer about the data"
    )
    p.set_defaults(func=cmd_analyze)

    # python investigator evaluate --split development
    p = sub.add_parser(
        "evaluate", help="evaluate the current version on a dataset split"
    )
    p.add_argument(
        "--split", default="development", help="dataset split to evaluate on"
    )
    p.set_defaults(func=cmd_evaluate)

    # python investigator improve --artifact instructions --candidates 3 --rounds 1
    p = sub.add_parser("improve", help="generate and score candidate improvements")
    p.add_argument(
        "--artifact",
        required=True,
        help="which artifact to improve (e.g. instructions)",
    )
    p.add_argument(
        "--candidates", type=positive_int, default=3, help="candidates per round"
    )
    p.add_argument(
        "--rounds", type=positive_int, default=1, help="number of improvement rounds"
    )
    p.set_defaults(func=cmd_improve)

    # python investigator compare baseline candidate-001
    p = sub.add_parser("compare", help="compare two versions")
    p.add_argument("left", metavar="VERSION_A", help="first version (e.g. baseline)")
    p.add_argument(
        "right", metavar="VERSION_B", help="second version (e.g. candidate-001)"
    )
    p.set_defaults(func=cmd_compare)

    # python investigator promote candidate-001
    p = sub.add_parser("promote", help="make a candidate the active version")
    p.add_argument("version", metavar="CANDIDATE", help="candidate to promote")
    p.set_defaults(func=cmd_promote)

    # python investigator rollback baseline
    p = sub.add_parser("rollback", help="revert to an earlier version")
    p.add_argument("version", metavar="VERSION", help="version to roll back to")
    p.set_defaults(func=cmd_rollback)

    # python investigator resume RUN_ID
    p = sub.add_parser("resume", help="resume an interrupted run")
    p.add_argument("run_id", metavar="RUN_ID", help="ID of the run to resume")
    p.set_defaults(func=cmd_resume)

    return parser

def run(argv: list[str] | None = None):
    parser = build_parser()
    args = parser.parse_args(argv)

    # REMAINDER may keep a leading '--' separator; drop it.
    if getattr(args, "cmd_args", None) and args.cmd_args[0] == "--":
        args.cmd_args = args.cmd_args[1:]

    args.parser = parser  # handlers can call args.parser.error(...)
    args.func(args)

if __name__ == "__main__":
    #'analyze /Users/akbarahmad2/work/My/harness/Investigator/investigator/data/demo/synthetic_personal_spending.csv --question "Explain"'.split(' ')
    sys.exit(run('analyze /Users/akbarahmad2/work/My/harness/Investigator/investigator/data/demo/synthetic_personal_spending.csv --question "Explain"'.split(' ')))
