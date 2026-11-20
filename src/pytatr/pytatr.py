"""Python implementation of the TAsk TRacker (tatr)"""

import random
import sys
import time
from argparse import Action, ArgumentParser, Namespace
from pathlib import Path

import json

from pytatr.config import load_config
from pytatr.query import QueryError, QuerySyntaxError, compile_query, query_matches_task
from pytatr.taskid import (
    TaskID,
    resolve_task_ids,
    resolve_unique_task_id,
    NoTaskIDMatchError,
    InvalidTaskIDError,
    AmbiguousTaskIDMatchError,
)
from pytatr.task import (
    Task,
    TaskStatus,
    build_task_dependencies,
    format_task_as_json,
    format_task_as_multiline,
    format_task_as_single_line,
    format_tasks_as_json,
    read_task_from_file,
    write_task_to_file,
)

CHARS = "0123456789"
NUM_CHARS = 6
MAX_HEADER_PRINT_LEN = 100

# Exit codes
ERROR_OK = 0
ERROR_FOLDER = 1
ERROR_QUERY = 8
ERROR_QUERY_SYNTAX = 9
ERROR_TASK_NOT_FOUND = 3
ERROR_TASK_DUPLICATE = 4
ERROR_TASK_PARSE = 5
ERROR_TASK_CYCLIC_DEPENDENCY = 6
ERROR_TASK_ID_ERROR = 11
ERROR_CREATE = 7
ERROR_USAGE = 2
ERROR_FILE_NOT_FOUND = 10


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


def read_body_content_from_file(filename: Path | None) -> str:
    if filename is None:
        return ""
    with filename.open() as f:
        return f.read()


def create_new_task_with_content(args: Namespace) -> None:
    """Create a folder named from task id with empty contents"""
    task_folder = require_task_folder(args)

    task_id = TaskID.generate() # create_task_id(args)
    while full_task_path := task_folder / Path(task_id):
        if not full_task_path.is_dir():
            break
        task_id = TaskID.generate() # create_task_id(args)

    file_content = read_body_content_from_file(args.body_file)


    # we have now succesfully written our new TASK.md file and
    # now iterate through the blocks list and update the depen-
    # dencies of *OTHER* tasks to be dependent on *THIS* task id
    blocked_ids: list[TaskID] = [resolve_unique_task_id(task_folder, i) for i in args.blocks]
    for blocked_id in blocked_ids:
        blocked_task_file = task_folder / blocked_id / Path("TASK.md");
        success , blocked_task = read_task_from_file(blocked_task_file, blocked_id);
        if success:
            blocked_task.depends.append(task_id)
            write_task_to_file(blocked_task)
            print(f"[INFO]: updated {blocked_id!s:s}: DEPENDS += {task_id!s:s}", file=sys.stderr)

    depends = [resolve_unique_task_id(task_folder, depend_id) for depend_id in args.depends]

    full_task_path.mkdir(parents=True)
    task = Task(
        task_file = full_task_path / Path("TASK.md"),
        task_id   = task_id,
        status    = TaskStatus.OPEN,
        priority  = args.priority,
        tags      = args.tags,
        depends   = depends,
        header    = args.title,
        body      = file_content,
    )
    write_task_to_file(task)

    print(f"{task_id!s:s}", file=sys.stdout)


def print_query_tasks(args: Namespace) -> bool:
    success = True

    task_folder = require_task_folder(args)

    query = compile_query(args.query[:])
    if args.debug:
        print("[QUERY]:", query, file=sys.stderr)

    tasks_to_print: list[Task] = []
    for child in task_folder.iterdir():
        task_file = child / Path("TASK.md")
        successfully_loaded_task, task = read_task_from_file(task_file, str(child))
        if successfully_loaded_task and query_matches_task(query, task):
            tasks_to_print.append(task)
        success = success & successfully_loaded_task

    output = tasks_to_print
    if args.sort_priority:
        output = sorted(output, key=lambda item: item.priority, reverse=True)

    if args.sort_reversed:
        output = reversed(output)

    if not args.output_json:
        for task in output:
            if args.only_show_ids:
                print(task.task_id.to_string())
            else:
                print(format_task_as_single_line(task))
    else:
        if args.only_show_ids:
            print(json.dumps([task.task_id.to_string() for task in output]))
        else:
            print(format_tasks_as_json(output))

    return success


def show_single_task(args: Namespace) -> bool:
    """multiline information for a single task"""
    task_folder = require_task_folder(args)
    task_id = resolve_unique_task_id(task_folder, args.id)
    task_file = task_folder / task_id / Path("TASK.md")
    success, task = read_task_from_file(task_file, task_id)

    if success:
        if not args.output_json:
            print(format_task_as_multiline(task))
        else:
            print(format_task_as_json(task))

    return success


def show_matching_ids(args: Namespace) -> None:
    task_folder = require_task_folder(args)
    task_ids = resolve_task_ids(task_folder, args.id)

    if not task_ids:
        raise NoTaskIDMatchError(f"query '{args.id:s}' found no matching tasks")
    else:
        if not args.output_json:
            print("\n".join([s for s in task_ids]))
        else:
            print(json.dumps([{"id": s} for s in task_ids]))


def build_dependency_tree(task: Task, visited: tuple = (), indent: int = 0) -> bool:
    def print_indent_task(task: Task, indent: int = 0):
        padding = " " * indent
        print(f"{padding:s}{task.task_id!s:s} ({task.status.name:s})")

    def build_cyclic_map(task_id: TaskID, visited: tuple) -> str:
        first = visited.index(task_id)
        s = f"{visited[first]:s} -> "
        items = visited[first+1:] + (task_id, )
        s += " -> ".join(items)
        return s

    print_indent_task(task, indent)

    found_cyclic = False
    depends = build_task_dependencies(task)
    for depend_task in depends:
        if depend_task.task_id in visited:
            print(f"[ERROR]: cycle {build_cyclic_map(depend_task.task_id, visited):s}", file=sys.stderr)
            depend_task.status = TaskStatus.CYCLIC
            found_cyclic = True

        next_set = visited + (depend_task.task_id,)

        if depend_task.is_valid():
            found_cyclic = build_dependency_tree(depend_task, next_set, indent + 2)
        else:
            print_indent_task(depend_task, indent + 2)

    return found_cyclic


def update_task_from_command_line(args: Namespace) -> bool:
    task_folder = require_task_folder(args)
    task_id = resolve_unique_task_id(task_folder, args.id)
    task_file = task_folder / task_id / Path("TASK.md")
    success, task = read_task_from_file(task_file, task_id)

    if hasattr(args, "status"):
        task.status = TaskStatus[args.status.upper()]

    if hasattr(args, "tags"):
        task.tags = args.tags

    if hasattr(args, "depends"):
        task.depends = [TaskID.from_string(dependency) for dependency in args.depends]

    write_task_to_file(task)

    return True


def show_dependency_tree(args: Namespace) -> bool:
    task_folder = require_task_folder(args)
    task_id = resolve_unique_task_id(task_folder, args.id)
    task_file = task_folder / task_id / Path("TASK.md")
    success, task = read_task_from_file(task_file, task_id)

    found_cyclic_dependency = False
    if success:
        found_cyclic_dependency = build_dependency_tree(task, (task.task_id,), 0)

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
        "-t",
        "--tags",
        default=["bug"],
        nargs="+",
        help="List of tags. Default is bug.",
    )
    ap_create.add_argument(
        "-p",
        "--priority",
        default=100,
        type=int,
        metavar="NUMBER",
        help="Priority of task. 1 is lowest, 100 is highest. Default is %(default)s.",
    )
    ap_create.add_argument(
        "--depends",
        default=[],
        nargs="*",
        metavar="TASKID",
        help="Task IDs this task is dependent on direct. Must be existing tasks.",
    )
    ap_create.add_argument(
        "--blocks",
        default=[],
        nargs="*",
        metavar="TASKID",
        help="Task IDs that this task will block. Must be existing tasks. (updates dependencies of these tasks).",
    )
    ap_create.add_argument(
        "--body-file",
        type=Path,
        metavar="FILE",
        action=ToPathType,
        default=None,
        help="premade content of a task body.",
    )

    ap_list = subparsers.add_parser("ls", help="list tasks.")
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
    ap_list.add_argument(
        "-i",
        dest="only_show_ids",
        default=False,
        action="store_true",
        help="only show ids of tasks matching the query.",
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

    ap_show = subparsers.add_parser("show", help="show a task with details.")
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

    ap_set = subparsers.add_parser("set", help="set various fields from the command line")
    ap_set_subparsers = ap_set.add_subparsers(help="fields to set", dest="field", required=True)

    ap_set_status = ap_set_subparsers.add_parser("status", help="set the status of a task")
    ap_set_status.add_argument(
        "status",
        choices=("open", "closed"),
        type=str,
        metavar="STATUS",
        help="should be one of: [%(choices)s]",
    )
    ap_set_status.add_argument(
        "id",
        type=str,
        metavar="TASKID",
        help="id of the task. must match exactly one task",
    )

    ap_set_tags = ap_set_subparsers.add_parser("tags", help="set the tags of a task")
    ap_set_tags.add_argument(
        "tags",
        default=[],
        nargs="+",
        help="list of tags to set.",
    )
    ap_set_tags.add_argument(
        "id",
        type=str,
        metavar="TASKID",
        help="id of the task. must match exactly one task",
    )

    ap_set_depends = ap_set_subparsers.add_parser("depends", help="set the dependencies of a task")
    ap_set_depends.add_argument(
        "depends",
        default=[],
        nargs="+",
        help="list of dependencies to set.",
    )
    ap_set_depends.add_argument(
        "id",
        type=str,
        metavar="TASKID",
        help="id of the task. must match exactly one task",
    )

    args = ap.parse_args()

    # check for bad arguments according to config file
    config = load_config(args)
    error_dispatcher = {"create": ap_create, "set": ap_set_tags}
    if hasattr(args, "tags"):
        if config.allowed_tags:
            bad_tags = [t for t in args.tags if t not in config.allowed_tags]
            if bad_tags:
                parser = error_dispatcher.get(args.command, None)
                parser.error(f"The supplied tags are not allowed: {", ".join(bad_tags):s}. Allowed tags from config are: {", ".join(config.allowed_tags):s}")

    return args


def main(args: Namespace) -> int:
    if args.debug:
        print("[ARGS]:", args)

    try:
        match args.command:
            case "init":
                args.task_folder.mkdir(exist_ok=False)
            case "ls":
                success = print_query_tasks(args)
                if not success:
                    return ERROR_TASK_PARSE
            case "create":
                if args.priority > 100 or args.priority < 1:
                    raise ValueError(f"priority {args.priority:d} outside 1-100 (1 = least, 100 = most important)")
                create_new_task_with_content(args)
            case "show":
                success = show_single_task(args)
                if not success:
                    return ERROR_TASK_PARSE
            case "id":
                show_matching_ids(args)
            case "depends":
                found_cyclic = show_dependency_tree(args)
                if found_cyclic:
                    return ERROR_TASK_CYCLIC_DEPENDENCY
            case "set":
                success = update_task_from_command_line(args)
            case _:
                print(f"[ERROR]: command {args.command} does not exist", file=sys.stderr)
                return ERROR_USAGE

    except QueryError as e:
        print(f"[ERROR]: {e}", file=sys.stderr)
        return ERROR_QUERY

    except QuerySyntaxError as e:
        print(f"[SYNTAX ERROR]: {e}", file=sys.stderr)
        return ERROR_QUERY_SYNTAX

    except NoTaskIDMatchError as e:
        print(f"[ERROR]: {e}", file=sys.stderr)
        return ERROR_TASK_NOT_FOUND

    except InvalidTaskIDError as e:
        print(f"[ERROR]: {e}", file=sys.stderr)
        return ERROR_TASK_NOT_FOUND

    except AmbiguousTaskIDMatchError as e:
        print(f"[ERROR]: {e}", file=sys.stderr)
        return ERROR_TASK_DUPLICATE

    except (FileExistsError, TasksFolderNotFoundError) as e:
        print(f"[ERROR]: {e}", file=sys.stderr)
        return ERROR_FOLDER

    except FileNotFoundError as e:
        print(f"[ERROR]: {e}", file=sys.stderr)
        return ERROR_FILE_NOT_FOUND

    return ERROR_OK


def cli() -> int:
    return main(parse_args())


if __name__ == "__main__":
    sys.exit(cli())
