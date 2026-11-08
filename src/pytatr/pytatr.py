"""Python implementation of the TAsk TRacker (tatr)"""

import random
import sys
import time
from argparse import Action, ArgumentParser, Namespace
from pathlib import Path
from string import Template

import json

from pytatr.query import QueryError, QuerySyntaxError, compile_query, query_matches_task
from pytatr.task import (
    Task,
    build_task_dependencies,
    format_task_as_json,
    format_task_as_multiline,
    format_task_as_single_line,
    format_tasks_as_json,
    get_task_from_file,
)

CHARS = "0123456789"
NUM_CHARS = 6
MAX_HEADER_PRINT_LEN = 100

# Exit codes
ERROR_OK = 0
ERROR_FOLDER = 1
ERROR_QUERY = 2
ERROR_QUERY_SYNTAX = 10
ERROR_TASK_NOT_FOUND = 3
ERROR_TASK_DUPLICATE = 4
ERROR_TASK_PARSE = 5
ERROR_TASK_CYCLIC_DEPENDENCY = 6
ERROR_CREATE = 7
ERROR_USAGE = 8
ERROR_FILE_NOT_FOUND = 9


CREATE_MARKDOWN = """# $title

 - STATUS: OPEN
 - PRIORITY:$priority
 - TAGS:$tags
 - DEPENDS:$depends

$body
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


def read_body_content_from_file(filename: Path | None) -> str:
    if filename is None:
        return ""
    with filename.open() as f:
        return f.read()


def create_task_id_folder_with_empty_contents(args: Namespace) -> None:
    """Create a folder named from task id with empty contents"""
    task_folder = require_task_folder(args)

    task_id = create_task_id(args)
    while full_task_path := task_folder / Path(task_id):
        if not full_task_path.is_dir():
            break
        task_id = create_task_id(args)

    try:
        file_content = read_body_content_from_file(args.body_file)
    except FileNotFoundError as e:
        print(f"[ERROR]: could not read file '{args.body_file!s:s}'")
        sys.exit(ERROR_FILE_NOT_FOUND)

    depends = [resolve_unique_task_id(task_folder, i) for i in args.depends]

    full_task_path.mkdir(parents=True)
    with (full_task_path / Path("TASK.md")).open("w") as f:
        s = Template(CREATE_MARKDOWN)
        mapping = {
            "title"     : args.title,
            "priority"  : " " + str(args.priority),
            "tags"      : " " + ", ".join(args.tags),
            "depends"   : " " + ", ".join(depends),
            "body"      : file_content,
        }
        f.write(s.substitute(mapping))

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
        if successfully_loaded_task and query_matches_task(query, task, task_folder):
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


def resolve_task_ids(task_folder: Path, unresolved_id: str) -> set[None | str]:
    """Resolves task ids based on a (potentially) unresolved id"""
    found_ids = []
    for child in task_folder.iterdir():
        # full match first
        if child.match(unresolved_id):
            found_ids.append(child.stem)

        # semi-fuzzy match on the random part only
        if child.match(f"*-{unresolved_id}*"):
            found_ids.append(child.stem)

    return set(found_ids)


def resolve_unique_task_id(task_folder: Path, unresolved_id: str) -> str:
    """Resolves a unique task id based on a (potentially) unresolved id"""
    unique_ids = resolve_task_ids(task_folder, unresolved_id)
    if not unique_ids:
        print(f"[ERROR]: query '{unresolved_id}' found no matching tasks", file=sys.stderr)
        sys.exit(ERROR_TASK_NOT_FOUND)
    elif len(unique_ids) > 1:
        print(
            f"[ERROR]: query '{unresolved_ud}' is ambiguous: {', '.join([i for i in unique_ids])}",
            file=sys.stderr,
        )
        sys.exit(ERROR_TASK_DUPLICATE)
    return unique_ids.pop()


def show_single_task(args: Namespace) -> bool:
    """multiline information for a single task"""
    task_folder = require_task_folder(args)
    task_id = resolve_unique_task_id(task_folder, args.id)
    task_file = task_folder / task_id / Path("TASK.md")

    success, task = get_task_from_file(task_file, task_id)

    if success:
        if not args.output_json:
            print(format_task_as_multiline(task, task_folder))
        else:
            print(format_task_as_json(task, task_folder))

    return success


def show_matching_ids(args: Namespace) -> None:
    task_folder = require_task_folder(args)
    task_ids = resolve_task_ids(task_folder, args.id)

    if not task_ids:
        print(f"[ERROR]: query '{args.id}' found no matching tasks", file=sys.stderr)
        sys.exit(ERROR_TASK_NOT_FOUND)
    else:
        if not args.output_json:
            print("\n".join([s for s in task_ids]))
        else:
            print(json.dumps([{"id": s} for s in task_ids]))


def build_dependency_tree(task: Task, task_folder: Path, visited: tuple = (), indent: int = 0) -> bool:
    def print_indent_task(task: Task, indent: int = 0):
        padding = " " * indent
        print(f"{padding:s}{task.task_id} ({task.status:s})")

    def build_cyclic_map(task_id: str, visited: tuple) -> str:
        first = visited.index(task_id)
        s = f"{visited[first]:s} -> "
        items = visited[first+1:] + (task_id, )
        s += " -> ".join(items)
        return s

    print_indent_task(task, indent)

    found_cyclic = False
    depends = build_task_dependencies(task, task_folder)
    # print(f"[DEBUG]: {task.task_id:s}:", depends)
    for depend_task in depends:
        if depend_task.task_id in visited:
            print(f"[ERROR]: cycle {build_cyclic_map(depend_task.task_id, visited):s}", file=sys.stderr)
            depend_task.status = "CYCLE"
            found_cyclic = True

        next_set = visited + (depend_task.task_id,)

        if depend_task.is_valid():
            found_cyclic = build_dependency_tree(depend_task, task_folder, next_set, indent + 2)
        else:
            print_indent_task(depend_task, indent + 2)

    return found_cyclic


def show_dependency_tree(args: Namespace) -> bool:
    task_folder = require_task_folder(args)
    task_id = resolve_unique_task_id(task_folder, args.id)
    task_file = task_folder / task_id / Path("TASK.md")

    success, task = get_task_from_file(task_file, task_id)
    found_cyclic_dependency = False
    if success:
        found_cyclic_dependency = build_dependency_tree(task, task_folder, (task.task_id,), 0)

    return found_cyclic_dependency


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
        "-d",
        "--depends",
        default=[],
        nargs="*",
        metavar="TASKID",
        help="Task IDs for direct dependencies. Must be existing tasks.",
    )
    ap_create.add_argument(
        "--user-tag",
        type=str,
        help="user tag for tasks. use to avoid clashing with your team. No default.",
    )
    ap_create.add_argument(
        "--body-file",
        type=Path,
        metavar="FILE",
        action=ToPathType,
        default=None,
        help="premade content of a task body.",
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

    ap_deps = subparsers.add_parser("depends", help="lists a dependency tree")
    ap_deps.add_argument(
        "id",
        default=None,
        type=str,
        metavar="TASKID",
        help="id of the task. can be fuzzy",
    )

    ap_show = subparsers.add_parser("show", help="show a note")
    ap_show.add_argument(
        "id",
        default=None,
        type=str,
        metavar="TASKID",
        help="id of the task. can be fuzzy",
    )
    ap_show.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        default=False,
        help="output json instead of plain text",
    )

    ap_id = subparsers.add_parser("id", help="resolves task ids (or parts thereof) into valid ids.")
    ap_id.add_argument(
        "id",
        default=None,
        type=str,
        metavar="TASKID",
        help="id of the task(s). can match random part of task id",
    )
    ap_id.add_argument(
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
                except QuerySyntaxError as e:
                    print(f"[SYNTAX ERROR]: {e}", file=sys.stderr)
                    sys.exit(ERROR_QUERY_SYNTAX)
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
            case "id":
                show_matching_ids(args)
            case "depends":
                found_cyclic = show_dependency_tree(args)
                if found_cyclic:
                    sys.exit(ERROR_TASK_CYCLIC_DEPENDENCY)
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
