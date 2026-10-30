from dataclasses import dataclass
import json
from pathlib import Path

import mistune


@dataclass
class Task:
    """Represents a task"""

    task_file: Path
    task_id: str
    status: str
    priority: int
    tags: list[str]
    depends: list[str]
    header: str


def parse_task_file(filename: Path) -> Task:
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
        if len(value) == 0:
            return []
        return [m.strip() for m in value.split(key)]

    def parse_list_item(node: dict) -> tuple[str, str]:
        assert node["type"] == "list_item"
        content = node["children"][0]["children"][0]
        assert "raw" in content
        raw = content["raw"]
        name, seperator, value = raw.partition(":")
        assert seperator, "could not find expected : in string"
        return name.strip(), value.strip()

    task_id = filename.parent.stem
    with filename.open("r") as f:
        text = "".join(f.readlines())

    md = mistune.markdown(text, renderer="ast")
    header = parse_header(md.pop(0))
    while next_item_is_blank(md[0]):
        md.pop(0)
    children = parse_list(md.pop(0))

    required_keys = ["STATUS", "PRIORITY", "TAGS", "DEPENDS"]
    out_types = {"STATUS": str, "PRIORITY": int, "TAGS": to_list, "DEPENDS": to_list}
    out_data = {
        "HEADER": header,
        "TAGS": [],
        "PRIORITY": 100,
        "STATUS": "",
        "DEPENDS": [],
    }

    assert len(children) >= 4, (
        "specification requires at least 4 elements: TAGS, PRIORITY, STATUS, DEPENDS"
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

    return Task(
        task_file=filename,
        task_id=task_id,
        status=out_data.get("STATUS", "ERROR"),
        priority=out_data.get("PRIORITY", -1),
        tags=out_data.get("TAGS", []),
        depends=out_data.get("DEPENDS", []),
        header=out_data.get("HEADER"),
    )


def build_task_dependencies(task: Task, task_folder: Path) -> list[Task]:
    depends = []
    for depend_task_id in task.depends:
        depend_task_file = task_folder / depend_task_id / Path("TASK.md")
        depends.append(parse_task_file(depend_task_file))
        # depends.append(f"{depend_task_id:s} ({depend_task.status.upper()})")
    return depends


def format_task_as_single_line(task: Task) -> str:
    return f"{task.task_file!s:s}:1: {task.status:>6s} [PRIORITY: {task.priority:>3d}] [{','.join(task.tags)}] {task.header:s}"


def format_task_as_multiline(task: Task, task_folder: Path) -> str:
    format_str = "{0:<12s}{1:s}\n"
    s = format_str.format("id:", task.task_id)
    s += format_str.format("title:", task.header)
    s += format_str.format("status:", task.status)
    s += format_str.format("priority:", str(task.priority))
    s += format_str.format("tags:", ", ".join(task.tags))

    # we need the status of any dependencies
    depends = [
        f"{depend_task.task_id:s} ({depend_task.status.upper()})"
        for depend_task in build_task_dependencies(task, task_folder)
    ]
    s += format_str.format("depends:", ", ".join(depends))
    files = ", ".join([child.name for child in (task_folder / task.task_id).iterdir()])
    s += format_str.format("files:", files)
    s += format_str.format("path:", str(task.task_file))
    return s


def format_task_as_json(task: Task, task_folder: Path):
    """formats output as json"""
    depends = [
        {
            "id": depend_task.task_id,
            "path": str(depend_task.task_file),
            "status": depend_task.status,
        }
        for depend_task in build_task_dependencies(task, task_folder)
    ]
    files = [child.name for child in (task_folder / task.task_id).iterdir()]
    return json.dumps(
        {
            "id": task.task_id,
            "title": task.header,
            "status": task.status,
            "priority": task.priority,
            "tags": task.tags,
            "depends": depends,
            "files": files,
            "path": str(task.task_file),
        }
    )
