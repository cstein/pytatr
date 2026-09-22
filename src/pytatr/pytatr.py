"""Python implementation of the TAsk TRacker (tatr)"""

import random
import sys
import time
from argparse import Action, ArgumentParser, Namespace
from dataclasses import dataclass
from pathlib import Path
from string import Template

import mistune

from pytatr.query import compile_query, query_matches_task, QueryError

CHARS = "0123456789"
NUM_CHARS = 6
MAX_HEADER_PRINT_LEN = 100


CREATE_MARKDOWN = """# $title

 - STATUS: OPEN
 - PRIORITY: $priority
 - TAGS: $tags

[description here]
"""


def unreachable(message: str) -> None:
    raise RuntimeError(message)


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
        }
        f.write(s.substitute(mapping))

    print(f"[INFO] Created task: {task_id:s}")


def parse_task_file(filename: Path) -> dict[str, str | int | list[str]]:
    def parse_header(heading_node: dict) -> str:
        assert heading_node["type"] == "heading", (
            f"could not find heading in expected header entry {value!s:s}"
        )
        assert heading_node["attrs"]["level"] == 1
        assert len(heading_node["children"]) == 1, (
            "unexpected number of children for heading element"
        )
        text_node = heading_node["children"][0]
        assert text_node["type"] == "text"
        return text_node["raw"]

    def next_item_is_blank(node: dict) -> bool:
        return node["type"] == "blank_line"

    def parse_list(node: dict) -> list[dict]:
        assert node["type"] == "list"
        assert len(node["children"]) > 0
        return node["children"]

    def to_list(value: str, key: str = ",") -> list[str]:
        assert isinstance(value, str)
        return [m.strip() for m in value.split(key)]

    def parse_list_item(node: dict) -> tuple[str, str]:
        assert node["type"] == "list_item"
        content = node["children"][0]["children"][0]
        assert "raw" in content
        raw = content["raw"]
        name, seperator, value = raw.partition(":")
        assert seperator, "could not find expected : in string"
        return name.strip(), value.strip()

    with filename.open("r") as f:
        text = "".join(f.readlines())

    md = mistune.markdown(text, renderer="ast")
    header = parse_header(md.pop(0))
    while next_item_is_blank(md[0]):
        md.pop(0)
    children = parse_list(md.pop(0))

    required_keys = ["STATUS", "PRIORITY", "TAGS"]
    out_types = {"STATUS": str, "PRIORITY": int, "TAGS": to_list}
    out_data = {"HEADER": header, "TAGS": [], "PRIORITY": 100, "STATUS": ""}

    assert len(children) >= 3, (
        "specification requires at least 3 elements: TAGS, PRIORITY, STATUS"
    )
    while len(children) > 0:
        name, value = parse_list_item(children.pop(0))
        if name in required_keys:
            try:
                out_data[name] = out_types[name](value)
            except ValueError:
                raise MarkdownParseError(
                    f"while parsing file '{filename!s:s}' the field {name:s} conversion to {out_types[name]!s:s} failed with value {value:s}"
                )
        else:
            out_data[name] = value
    return out_data


@dataclass
class TaskPrintOut:
    task_file: Path
    status: str
    priority: int
    tags: list[str]
    header: str

    def __str__(self):
        return f"{self.task_file!s:s}:1: {self.status:>6s} [PRIORITY: {self.priority:>3d}] [{','.join(self.tags)}] {self.header:s}"


def print_tasks(args: Namespace) -> None:
    task_folder = require_task_folder(args)

    query = compile_query(args.query[:])
    if args.debug:
        print("[QUERY]:", query)
    tasks_to_print = []
    for child in task_folder.iterdir():
        task_file = child / Path("TASK.md")
        try:
            task = parse_task_file(task_file)
        except MarkdownParseError as e:
            print(f"[WARNING]: {e}", file=sys.stderr)
            continue

        if query_matches_task(query, task):
            format_header = task["HEADER"]
            if len(format_header) > args.header_length:
                format_header = format_header[: args.header_length] + "..."
            tasks_to_print.append(
                TaskPrintOut(
                    task_file=task_file,
                    status=task.get("STATUS", "ERROR"),
                    priority=task.get("PRIORITY", -1),
                    tags=task.get("TAGS", []),
                    header=format_header,
                )
            )
    output = tasks_to_print
    if args.sort_priority:
        output = sorted(output, key=lambda item: item.priority)

    if args.sort_reversed:
        output = reversed(output)

    for task in output:
        print(task)


def parse_args() -> Namespace:
    ap = ArgumentParser()
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

    ap_init = subparsers.add_parser("init", help="Creates the task folder.")
    ap_init.add_argument(
        "-v", dest="verbose", default=False, action="store_true", help="verbose output."
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
                    print_tasks(args)
                except QueryError as e:
                    print(f"[ERROR]: {e}", file=sys.stderr)
                    sys.exit(2)
            case "create":
                create_task_id_folder_with_empty_contents(args)
            case _:
                sys.exit(2)
    except (FileExistsError, TasksFolderNotFoundError) as e:
        print(f"[ERROR]: {e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


def cli():
    main(parse_args())


if __name__ == "__main__":
    cli()
