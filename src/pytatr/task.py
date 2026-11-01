import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import mistune


class TaskHeaderNotFoundError(ValueError):
    pass


class RequiredElementNotFoundError(ValueError):
    pass


class MarkdownConvertValueError(Exception):
    pass


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

    def is_valid(self):
        return self.status.upper() in ["OPEN", "CLOSED"]


def parse_task_file(filename: Path) -> Task:
    def parse_header(heading_node: dict) -> str:
        if heading_node["type"] != "heading":
            raise TaskHeaderNotFoundError("missing")
        if heading_node["attrs"]["level"] != 1:
            raise TaskHeaderNotFoundError("not top level")
        if len(heading_node["children"]) != 1:
            raise TaskHeaderNotFoundError("Unexpected syntax error")
        text_node = heading_node["children"][0]
        if text_node["type"] != "text":
            raise TaskHeaderNotFoundError("unexpected type")
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

    found_required_keys = []
    while len(children) > 0:
        name, value = parse_list_item(children.pop(0))
        if name in required_keys:
            found_required_keys.append(name)
            try:
                out_data[name] = out_types[name](value)
            except ValueError:
                raise MarkdownConvertValueError(
                    f"field {name:s} conversion to {out_types[name]!s:s} failed to convert value {value:s} of type {type(value)!s:s}"
                )
        else:
            out_data[name] = value

    for required_key in required_keys:
        if required_key not in found_required_keys:
            raise RequiredElementNotFoundError(required_key)

    task_id = filename.parent.stem
    return Task(
        task_file=filename,
        task_id=task_id,
        status=out_data.get("STATUS"),
        priority=out_data.get("PRIORITY"),
        tags=out_data.get("TAGS"),
        depends=out_data.get("DEPENDS"),
        header=out_data.get("HEADER"),
    )


def get_task_from_file(task_file: Path, task_id: str) -> tuple[bool, Task | None]:
    try:
        task = parse_task_file(task_file)
    except TaskHeaderNotFoundError as e:
        print(f"[ERROR]: {task_id:s}: {e} header", file=sys.stderr)
        return False, None
    except RequiredElementNotFoundError as e:
        print(
            f"[ERROR]: {task_id:s}: required element '{e}' not found", file=sys.stderr
        )
        return False, None
    except MarkdownConvertValueError as e:
        print(f"[ERROR]: {task_id:s}: {e}", file=sys.stderr)
        return False, None
    except FileNotFoundError:
        print(f"[ERROR]: {task_id:s}: TASK.md file missing", file=sys.stderr)
        return False, None
    else:
        return True, task


def build_task_dependencies(task: Task, task_folder: Path) -> list[Task]:
    depends = []
    # requires full task ID
    # TODO (CS) cleanup code for dummy dependency. see 20261030-834808
    # we use a set to ignore duplicates
    for depend_task_id in set(task.depends):
        if depend_task_id == task.task_id:
            print(
                f"[WARNING]: {task.task_id:s}: Task depends recursively on itself. Ignored.",
                file=sys.stderr,
            )
            continue

        depend_task_file = task_folder / depend_task_id / Path("TASK.md")
        try:
            depends.append(parse_task_file(depend_task_file))
        except (
            RequiredElementNotFoundError,
            TaskHeaderNotFoundError,
            MarkdownConvertValueError,
        ) as e:
            depends.append(
                Task(
                    task_id=depend_task_id,
                    task_file=depend_task_file,
                    status="UNREADABLE",
                    priority=1,
                    header="ERROR",
                    tags=[],
                    depends=[],
                )
            )
        except FileNotFoundError:
            depends.append(
                Task(
                    task_id=depend_task_id,
                    task_file=depend_task_file,
                    status="MISSING",
                    priority=1,
                    header="ERROR",
                    tags=[],
                    depends=[],
                )
            )
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


def task_to_dict(task: Task, task_folder: Path) -> dict[str, str | int | list]:
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
    return {
        "id": task.task_id,
        "title": task.header,
        "status": task.status,
        "priority": task.priority,
        "tags": task.tags,
        "depends": depends,
        "files": files,
        "path": str(task.task_file),
    }


def format_task_as_json(task: Task, task_folder: Path) -> str:
    return json.dumps(task_to_dict(task, task_folder))


def format_tasks_as_json(tasks: list[Task], task_folder: Path) -> str:
    return json.dumps([task_to_dict(task, task_folder) for task in tasks])
