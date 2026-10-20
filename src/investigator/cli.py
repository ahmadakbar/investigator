import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)


def cmd_analyze(args):
    pass


def cmd_evaluate(args):
    pass


def cmd_improve(args):
    pass


def cmd_compare(args):
    pass


def cmd_promote(args):
    pass


def cmd_rollback(args):
    pass


def cmd_resume(args):
    pass


def positive_int(value: str) -> int:
    n = int(value)
    if n <= 0:
        raise argparse.ArgumentTypeError(f"{n} must be > 0")
    return n


def existing_file(value: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"file not found: {value}")
    return path


def run() -> None:
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


if __name__ == "__main__":
    run()
