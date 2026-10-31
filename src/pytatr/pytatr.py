"""Python implementation of the TAsk TRacker (tatr)"""

import random
import sys
import time
from argparse import Action, ArgumentParser, Namespace
from dataclasses import dataclass
from enum import Enum
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
    TaskHeaderNotFoundError,
    RequiredElementNotFoundError,
    MarkdownConvertValueError,
)
from pytatr.query import compile_query, query_matches_task, QueryError

CHARS = "0123456789"
NUM_CHARS = 6
MAX_HEADER_PRINT_LEN = 100

# Exit codes
ERROR_OK = 0
ERROR_FOLDER = 1
ERROR_QUERY = 2
ERROR_TASK_NOT_FOUND = 3
ERROR_TASK_DUPLICATE = 4
ERROR_TASK_PARSE = 5
ERROR_CREATE = 6
ERROR_USAGE = 7


CREATE_MARKDOWN = """# $title

 - STATUS: OPEN
 - PRIORITY: $priority
 - TAGS: $tags
 - DEPENDS: $depends

"""



class TasksFolderNotFoundError(Exception):
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


def print_query_tasks(args: Namespace) -> bool:
    # we set success flag to false if we experience error
    # so we can set the exit flag to ERROR_TASK_PARSE
    success = True

    task_folder = require_task_folder(args)

    query = compile_query(args.query[:])
    if args.debug:
        print("[QUERY]:", query, file=sys.stderr)
    tasks_to_print: list[Task] = []
    for child in task_folder.iterdir():
        task_file = child / Path("TASK.md")
        successfully_loaded_task, task = get_task_from_file(task_file, str(child))
        if successfully_loaded_task:
            if query_matches_task(query, task):
                tasks_to_print.append(task)
        success = success & successfully_loaded_task

    output = tasks_to_print
    if args.sort_priority:
        output = sorted(output, key=lambda item: item.priority, reverse=True)

    if args.sort_reversed:
        output = reversed(output)

    if not args.output_json:
        for task in output:
            print(format_task_as_single_line(task))
    else:
        print(format_tasks_as_json(output, task_folder))

    return success


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
        print(f"[ERROR]: query '{args.id}' found no matching tasks", file=sys.stderr)
        sys.exit(ERROR_TASK_NOT_FOUND)
    elif len(unique_ids) > 1:
        print(
            f"[ERROR]: query '{args.id}' is ambiguous: {', '.join([i for i in unique_ids])}",
            file=sys.stderr,
        )
        sys.exit(ERROR_TASK_DUPLICATE)
    return unique_ids.pop()

def get_task_from_file(task_file: Path, task_id: str) -> tuple[bool, Task | None]:
    try:
        task = parse_task_file(task_file)
    except TaskHeaderNotFoundError as e:
        print(f"[ERROR]: {task_id:s}: {e} header", file=sys.stderr)
        return False, None
    except RequiredElementNotFoundError as e:
        print(f"[ERROR]: {task_id:s}: required element '{e}' not found", file=sys.stderr)
        return False, None
    except MarkdownConvertValueError as e:
        print(f"[ERROR]: {task_id:s}: {e}", file=sys.stderr)
        return False, None
    except FileNotFoundError:
        print(f"[ERROR]: {task_id:s}: TASK.md file missing", file=sys.stderr)
        return False, None
    else:
        return True, task


def show_single_task(args: Namespace) -> bool:
    """multiline information for a single task"""
    success = True

    task_folder = require_task_folder(args)
    task_id = resolve_task_id(args)
    task_file = task_folder / task_id / Path("TASK.md")

    success, task = get_task_from_file(task_file, task_id)

    if success:
        if not args.output_json:
            print(format_task_as_multiline(task, task_folder))
        else:
            print(format_task_as_json(task, task_folder))

    return success


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
        help="use priority to sort tasks. important first.",
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
                    success = print_query_tasks(args)
                except QueryError as e:
                    print(f"[ERROR]: {e}", file=sys.stderr)
                    sys.exit(ERROR_QUERY)
                if not success:
                    sys.exit(ERROR_TASK_PARSE)
            case "create":
                if args.priority > 100 or args.priority < 1:
                    print(
                        f"[ERROR]: priority {args.priority:d} outside 1-100 (1 = least, 100 = most important)",
                        file=sys.stderr,
                    )
                    sys.exit(ERROR_CREATE)
                create_task_id_folder_with_empty_contents(args)
            case "show":
                success = show_single_task(args)
                if not success:
                    sys.exit(ERROR_TASK_PARSE)
            case _:
                print(
                    f"[ERROR]: command {args.command} does not exist", file=sys.stderr
                )
                sys.exit(ERROR_USAGE)
    except (FileExistsError, TasksFolderNotFoundError) as e:
        print(f"[ERROR]: {e}", file=sys.stderr)
        sys.exit(ERROR_FOLDER)
    sys.exit(ERROR_OK)


def cli():
    main(parse_args())


if __name__ == "__main__":
    cli()
