"""Python implementation of the TAsk TRacker (tatr)"""

import random
import sys
import time
from argparse import Action, ArgumentParser, Namespace
from pathlib import Path
from string import Template

CHARS = "0123456789"
NUM_CHARS = 6


CREATE_MARKDOWN = """# $title

 - STATUS: OPEN
 - PRIORITY: $priority
 - TAGS: $tags

[description here]
"""


def unreachable(message: str) -> None:
    raise RuntimeError(message)


class ConcatenateStringsAction(Action):
    """Concatenate inputs into one string"""
    def __call__(self, parser, namespace, values, option_string=None):
        value = " ".join(values)
        setattr(namespace, self.dest, value)


def create_task_id(args: Namespace) -> str:
    """Create a task id"""
    time_dict = time.localtime()
    time_str = time.strftime("%Y%m%d", time_dict)
    chars = "".join([random.choice(CHARS) for _ in range(NUM_CHARS)])
    user_tag = ""
    if args.user_tag is not None:
        user_tag = "-" + args.user_tag
    return f"{time_str:s}-{chars:s}{user_tag:s}"


def create_task_folder_with_empty_contents(args: Namespace) -> Path:
    mapping = {
        "title": args.title,
        "priority": str(args.priority),
        "tags": ", ".join(args.tags),
    }

    task_id = create_task_id(args)
    while task_folder := Path("tasks") / Path(task_id):
        if not task_folder.is_dir():
            break
        task_id = create_task_id(args)
    task_folder.mkdir()
    with (task_folder / Path("TASK.md")).open("w") as f:
        s = Template(CREATE_MARKDOWN)
        f.write(s.substitute(mapping))


def parse_args() -> Namespace:
    ap = ArgumentParser()
    subparsers = ap.add_subparsers(help="Parsers", dest="command")

    ap_create = subparsers.add_parser("create", help="Create a note")
    ap_create.add_argument(
        "title",
        default=None,
        nargs="+",
        type=str,
        help="Title of the task",
        action=ConcatenateStringsAction,
    )
    ap_create.add_argument(
        "-t", "--tags", default=["bug"], nargs="+", help="List of tags. Default is bug."
    )
    ap_create.add_argument(
        "-p",
        "--priority",
        default=100,
        type=int,
        metavar="NUMBER",
        help="Priority of task. Default is %(default)s.",
    )
    ap_create.add_argument(
        "--user-tag",
        type=str,
        help="user tag for tasks. use to avoid clashing with your team. No default.",
    )

    ap_list = subparsers.add_parser("ls", help="List tasks.")
    ap_list.add_argument("query", default="*", nargs="*", help="search query for tasks")

    return ap.parse_args()


def main(args: Namespace):
    print(args)
    match args.command:
        case "ls":
            uncreachable("Not implemented yet.")
        case "create":
            create_task_folder_with_empty_contents(args)
        case _:
            sys.exit(1)
    sys.exit(0)


def cli():
    main(parse_args())


if __name__ == "__main__":
    cli()
