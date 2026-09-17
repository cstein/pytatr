"""Python implementation of the TAsk TRacker (tatr)"""

import random
import sys
import time
from argparse import Action, ArgumentParser, Namespace
from enum import Enum
from pathlib import Path
from string import Template

import mistune

from pytatr.query import compile_query, match

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
    """Create a task folder with empty contents"""
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
    task_folder.mkdir(parents=True)
    with (task_folder / Path("TASK.md")).open("w") as f:
        s = Template(CREATE_MARKDOWN)
        f.write(s.substitute(mapping))


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
            out_data[name] = out_types[name](value)
        else:
            out_data[name] = value
    return out_data




def should_present_task(
        query,
        task: dict[str, str | int | list[str]]
) -> None:
    """Stack based search"""
    #stack: list[bool]  = []
    return match(query, task)


def find_tasks(args: Namespace) -> None:
    task_folder = Path("tasks")
    query = compile_query(args.query)
    print("[QUERY]:", query)
    for child in task_folder.iterdir():
        task_file = child / Path("TASK.md")
        data = parse_task_file(task_file)
        if should_present_task(query, data):
            s = f"{task_file!s:s}:1: {data['STATUS']:>6s} [PRIORITY: {data['PRIORITY']:3>d}] [{','.join(data['TAGS']):s}] {data['HEADER']:s}"
            print(s)


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
    ap_list.add_argument("query", default=["any"], nargs="*", help="search query for tasks")

    return ap.parse_args()


def main(args: Namespace):
    print("ARGS:", args)
    match args.command:
        case "ls":
            # uncreachable("Not implemented yet.")
            find_tasks(args)
        case "create":
            create_task_folder_with_empty_contents(args)
        case _:
            sys.exit(1)
    sys.exit(0)


def cli():
    main(parse_args())


if __name__ == "__main__":
    cli()
