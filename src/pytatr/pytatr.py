"""Python implementation of the TAsk TRacker (tatr)"""

import random
import sys
import time
from argparse import Action, ArgumentParser, Namespace
from dataclasses import dataclass
from pathlib import Path
from string import Template


from pytatr.task import (
    build_task_dependencies,
    format_task_as_json,
    format_task_as_multiline,
    format_task_as_single_line,
    format_tasks_as_json,
    parse_task_file,
    Task,
)
from pytatr.query import compile_query, query_matches_task, QueryError

CHARS = "0123456789"
NUM_CHARS = 6
MAX_HEADER_PRINT_LEN = 100


CREATE_MARKDOWN = """# $title

 - STATUS: OPEN
 - PRIORITY: $priority
 - TAGS: $tags
 - DEPENDS: $depends

"""


class TasksFolderNotFoundError(Exception):
    pass


class MarkdownParseError(Exception):
    pass


def require_task_folder(args: Namespace) -> Path:
    if not args.task_folder.is_dir():
        raise TasksFolderNotFoundError(
            f"The task folder '{args.task_folder!s:s}' does not exist. Have you run 'tatr init' yet?"
        )

    return args.task_folder


class ConcatenateStringsAction(Action):
    """Concatenate inputs into one string"""

    def __call__(self, parser, namespace, values, option_string=None):
        value = " ".join(values)
        setattr(namespace, self.dest, value)


class ToPathType(Action):
    def __call__(self, parser, namespace, value, option_string=None):
        setattr(namespace, self.dest, Path(value))


def create_task_id(args: Namespace) -> str:
    """Create a task id"""
    time_dict = time.localtime()
    time_str = time.strftime("%Y%m%d", time_dict)
    chars = "".join([random.choice(CHARS) for _ in range(NUM_CHARS)])
    user_tag = ""
    if args.user_tag is not None:
        user_tag = "-" + args.user_tag
    return f"{time_str:s}-{chars:s}{user_tag:s}"


def create_task_id_folder_with_empty_contents(args: Namespace) -> None:
    """Create a folder named from task id with empty contents"""
    task_folder = require_task_folder(args)

    task_id = create_task_id(args)
    while full_task_path := task_folder / Path(task_id):
        if not full_task_path.is_dir():
            break
        task_id = create_task_id(args)

    full_task_path.mkdir(parents=True)
    with (full_task_path / Path("TASK.md")).open("w") as f:
        s = Template(CREATE_MARKDOWN)
        mapping = {
            "title": args.title,
            "priority": str(args.priority),
            "tags": ", ".join(args.tags),
            "depends": ", ".join([]),
        }
        f.write(s.substitute(mapping))

    print(f"[INFO] Created task: {task_id:s}", file=sys.stderr)
    print(f"{task_id:s}", file=sys.stdout)


def get_task_from_file(filename: Path) -> Task:
    try:
        task = parse_task_file(filename)
    except MarkdownParseError as e:
        print(f"[ERROR]: {e}", file=sys.stderr)
        sys.exit(6)
    else:
        return task


def print_query_tasks(args: Namespace) -> None:
    task_folder = require_task_folder(args)

    query = compile_query(args.query[:])
    if args.debug:
        print("[QUERY]:", query)
    tasks_to_print: list[Task] = []
    for child in task_folder.iterdir():
        task_file = child / Path("TASK.md")
        task = get_task_from_file(task_file)

        if query_matches_task(query, task):
            format_header = task.header
            if len(task.header) > args.header_length:
                task.header = format_header[: args.header_length] + "..."
            tasks_to_print.append(task)

    output = tasks_to_print
    if args.sort_priority:
        output = sorted(output, key=lambda item: item.priority)

    if args.sort_reversed:
        output = reversed(output)


    if not args.output_json:
        for task in output:
            print(format_task_as_single_line(task))
    else:
        print(format_tasks_as_json(output, task_folder))


def resolve_task_id(args: Namespace) -> str:
    task_folder = require_task_folder(args)
    found_ids = []
    for child in task_folder.iterdir():
        # full match first
        if child.match(args.id):
            found_ids.append(child.stem)

        if child.match(f"*-{args.id}*"):
            found_ids.append(child.stem)

    unique_ids = set(found_ids)
    if not unique_ids:
        print(f"[ERROR]: no task matches '{args.id}'")
        sys.exit(3)
    elif len(unique_ids) > 1:
        print(
            f"[ERROR]: '{args.id}' is ambiguous: {', '.join([i for i in unique_ids])}"
        )
        sys.exit(3)
    return unique_ids.pop()


def show_single_task(args: Namespace):
    """multiline information for a single task"""
    task_folder = require_task_folder(args)
    task_id = resolve_task_id(args)
    task_file = task_folder / task_id / Path("TASK.md")
    task = get_task_from_file(task_file)
    if not args.output_json:
        print(format_task_as_multiline(task, task_folder))
    else:
        print(format_task_as_json(task, task_folder))


def parse_args() -> Namespace:
    ap = ArgumentParser(description="A local task tracker.")
    ap.add_argument(
        "-f",
        "--task-folder",
        default=Path(".tasks"),
        type=Path,
        metavar="DIR",
        action=ToPathType,
        help="directory for storing tasks. Default is %(default)s",
    )
    ap.add_argument(
        "--debug",
        default=False,
        action="store_true",
        help="enables debug output",
    )
    subparsers = ap.add_subparsers(help="Commands", dest="command", required=True)

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
    ap_list.add_argument(
        "query",
        default=["open"],
        nargs="*",
        help="Search query for tasks. Default is 'open'.",
    )
    ap_list.add_argument(
        "--header-length",
        default=MAX_HEADER_PRINT_LEN,
        type=int,
        help="maximum length of header to display. Default is %(default)s.",
    )
    ap_list.add_argument(
        "-r",
        dest="sort_reversed",
        default=False,
        action="store_true",
        help="reverse listing.",
    )
    ap_list.add_argument(
        "-p",
        dest="sort_priority",
        default=False,
        action="store_true",
        help="use priority to sort tasks",
    )
    ap_list.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        default=False,
        help="output json instead of plain text",
    )

    ap_init = subparsers.add_parser("init", help="Creates the task folder.")
    ap_init.add_argument(
        "-v", dest="verbose", default=False, action="store_true", help="verbose output."
    )

    ap_show = subparsers.add_parser("show", help="show a note")
    ap_show.add_argument(
        "id",
        default=None,
        # nargs="+",
        type=str,
        help="id of the task. can be fuzzy",
    )
    ap_show.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        default=False,
        help="output json instead of plain text",
    )

    return ap.parse_args()


def main(args: Namespace):
    if args.debug:
        print("[ARGS]:", args)

    try:
        match args.command:
            case "init":
                args.task_folder.mkdir(exist_ok=False)
            case "ls":
                try:
                    print_query_tasks(args)
                except QueryError as e:
                    print(f"[ERROR]: {e}", file=sys.stderr)
                    sys.exit(2)
            case "create":
                if args.priority > 100 or args.priority < 1:
                    print(
                        f"[ERROR]: priority {args.priority:d} outside 1-100 (1 = least, 100 = most important)",
                        file=sys.stderr,
                    )
                    sys.exit(4)
                create_task_id_folder_with_empty_contents(args)
            case "show":
                show_single_task(args)
            case _:
                print(
                    f"[ERROR]: command {args.command} does not exist", file=sys.stderr
                )
                sys.exit(3)
    except (FileExistsError, TasksFolderNotFoundError) as e:
        print(f"[ERROR]: {e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


def cli():
    main(parse_args())


if __name__ == "__main__":
    cli()
