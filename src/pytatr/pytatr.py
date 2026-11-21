"""Python implementation of the TAsk TRacker (tatr)"""

import json
import sys
from argparse import Namespace
from collections.abc import Callable
from pathlib import Path

from pytatr.config import load_config
from pytatr.parser import Parsers, build_parsers
from pytatr.query import (
    QueryError,
    QueryKeywordError,
    QuerySyntaxError,
    compile_query,
    query_matches_task,
)
from pytatr.task import (
    EmptyTagsError,
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
from pytatr.taskid import (
    AmbiguousTaskIDMatchError,
    InvalidTaskIDError,
    NoTaskIDMatchError,
    TaskID,
    resolve_task_ids,
    resolve_unique_task_id,
)

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
ERROR_TASK_EMPTY_TAGS = 12
ERROR_TASK_PRIORITY_OUT_OF_BOUNDS = 13
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


def print_query_tasks(args: Namespace) -> None:

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
        s = f"{visited[first]!s:s} -> "
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

    def identity(value):
        return value

    def resolve(value):
        return resolve_unique_task_id(task_folder, value)

    def clean(existing: list, potential: list, clean_function: Callable[[str], str]):
        """Using sets to clean up existing values with potential values
           using a clean_function to potentially clean values before comparison"""
        append  = set([clean_function(value[1:]) for value in potential if value[0] == "+"])
        remove  = set([clean_function(value[1:]) for value in potential if value[0] == "-"])
        replace = set([clean_function(value)     for value in potential if value[0] not in ["+", "-"]])
        new = (set(existing) | append) - remove
        if replace:
            new = (replace | append) - remove
        return new

    task_id = resolve_unique_task_id(task_folder, args.id)
    task_file = task_folder / task_id / Path("TASK.md")
    _ , task = read_task_from_file(task_file, task_id)

    if hasattr(args, "status"):
        task.status = TaskStatus[args.status.upper()]

    if hasattr(args, "priority"):
        if args.priority > 100 or args.priority < 1:
            raise ValueError(f"priority {args.priority:d} outside 1-100 (1 = least, 100 = most important)")
        task.priority = args.priority

    if hasattr(args, "tags"):
        new_tags = clean(task.tags, args.tags, identity)
        if new_tags:
            task.tags = list(new_tags)
        else:
            raise EmptyTagsError(f"{task_id!s}: supplied tags {', '.join(args.tags)} removes all tags.")

    if hasattr(args, "depends"):
        new_depends = clean(task.depends, args.depends, resolve)
        if task_id in new_depends:
            print(f"[WARNING]: {task.task_id!s:s}: Task would depend recursively on itself. Ignored.", file=sys.stderr)
            new_depends.remove(task_id)

        task.depends = list(new_depends)

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

    parsers: Parsers = build_parsers()
    args = parsers.main_parser.parse_args()

    # check for bad arguments according to config file
    config = load_config(args)
    error_dispatcher = {"create": parsers.create_parser, "set": parsers.set_parser}
    if hasattr(args, "tags") and config.allowed_tags:
        # tags can have + or - in them, so strip those values first
        corrected_tags = []
        for tag in args.tags:
            if tag[0] in ["+", "-"]:
                corrected_tags.append(tag[1:])
            else:
                corrected_tags.append(tag)

        bad_tags = [t for t in corrected_tags if t not in config.allowed_tags]
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
                print_query_tasks(args)
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
        print(f"[QUERY ERROR]: {e}", file=sys.stderr)
        return ERROR_QUERY

    except QueryKeywordError as e:
        print(f"[ERROR]: {e}", file=sys.stderr)
        return ERROR_QUERY_SYNTAX

    except QuerySyntaxError as e:
        print(f"[SYNTAX ERROR]: {e}", file=sys.stderr)
        return ERROR_QUERY_SYNTAX

    except NoTaskIDMatchError as e:
        print(f"[TASK ID ERROR]: {e}", file=sys.stderr)
        return ERROR_TASK_NOT_FOUND

    except InvalidTaskIDError as e:
        print(f"[TASK ID ERROR]: {e}", file=sys.stderr)
        return ERROR_TASK_NOT_FOUND

    except AmbiguousTaskIDMatchError as e:
        print(f"[TASK ID ERROR]: {e}", file=sys.stderr)
        return ERROR_TASK_DUPLICATE

    except EmptyTagsError as e:
        print(f"[ERROR]: {e}", file=sys.stderr)
        return ERROR_TASK_EMPTY_TAGS

    except (FileExistsError, TasksFolderNotFoundError) as e:
        print(f"[ERROR]: {e}", file=sys.stderr)
        return ERROR_FOLDER

    except FileNotFoundError as e:
        print(f"[ERROR]: {e}", file=sys.stderr)
        return ERROR_FILE_NOT_FOUND

    except ValueError as e:
        print(f"[ERROR]: {e}", file=sys.stderr)
        return ERROR_TASK_PRIORITY_OUT_OF_BOUNDS

    return ERROR_OK


def cli() -> int:
    return main(parse_args())


if __name__ == "__main__":
    sys.exit(cli())
