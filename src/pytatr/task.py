import json
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from string import Template

from pytatr.taskid import TaskID

"""The TASK format is fixed to four mandatory fields
as outlined below:
    STATUS = (OPEN|CLOSED)
    PRIORITY = 1..100
    TAGS = [str, str, ..., str]
    DEPENDS [ID, ID, ..., ID]

where ID is any valid task id (YYYYMMDD-123456).
"""
TASK_MARKDOWN = """# $title

 - STATUS: $status
 - PRIORITY:$priority
 - TAGS:$tags
 - DEPENDS:$depends

$body"""


class TaskStatus(Enum):
    CLOSED = 0
    OPEN = 1
    INVALID = 2
    MISSING = 3
    CYCLIC = 4

    @classmethod
    def from_string(cls, value):
        return cls[value]


class TaskHeaderNotFoundError(ValueError):
    pass


class TaskBlankLineMissing(ValueError):
    pass


class ExpectedTaskListItemNotFoundError(ValueError):
    pass


class TaskMalformedListItem(ValueError):
    pass


class RequiredElementNotFoundError(ValueError):
    pass


class MarkdownConvertValueError(Exception):
    pass


@dataclass
class Task:
    """Represents a task"""

    task_file: Path
    task_id: TaskID
    status: TaskStatus
    priority: int
    tags: list[str]
    depends: list[TaskID]
    header: str
    body: str = ""

    def is_valid(self):
        return self.status in [TaskStatus.OPEN, TaskStatus.CLOSED]

    def to_dict(self) -> dict[str, str | int | list | dict]:
        task_folder: Path = self.task_file.parent.parent
        """formats output as json"""
        depends = [
            {
                "id": depend_task.task_id.to_string(),
                "path": str(depend_task.task_file),
                "status": depend_task.status.name,
            }
            for depend_task in build_task_dependencies(self)
        ]
        files = [child.name for child in (task_folder / self.task_id).iterdir()]
        return {
            "id"       : self.task_id.to_string(),
            "title"    : self.header,
            "status"   : self.status.name,
            "priority" : self.priority,
            "tags"     : self.tags,
            "depends"  : depends,
            "files"    : files,
            "path"     : str(self.task_file),
            "body"     : self.body,
        }


def parse_task_file(filename: Path) -> Task:
    def is_blank(value: str) -> bool:
        line, _ = value.split("\n")
        return len(line) == 0

    def expect_blank_line(value: str) -> None:
        if not is_blank(value):
            raise TaskBlankLineMissing(f"Expected blank line after header but got '{value:s}'")

    def trim_whitespace_dash_and_hash(value: str) -> str:
        """trims whitespace, '-' and '#' from the left"""
        index = 0
        while value[index] in [" ", "-", "#"]:
            index += 1
        return value[index:]

    def parse_list_items(value: str) -> tuple[str, str]:
        line, _ = value.split("\n")
        if not "-" in line:
            raise ExpectedTaskListItemNotFoundError(f"Expected list item (-) but found '{line:s}'")

        try:
            left, right = line.split(":")
        except ValueError:
            raise TaskMalformedListItem(f"Expected format '- KEY: VALUE' but got '{line:s}'")

        return trim_whitespace_dash_and_hash(left), right.strip()

    def to_list(value: str, key: str = ",") -> list[str]:
        assert isinstance(value, str)
        if len(value) == 0:
            return []
        return [m.strip() for m in value.split(key)]

    def to_taskid_list(value: str, key: str = ",") -> list[TaskID]:
        return [TaskID.from_string(v) for v in to_list(value, key)]

    def check_required_field_consistency(data: dict[str, list[str] | list[TaskID]], key: str, task_id: TaskID) -> None:
        data_without_empty_items = [item for item in data[key] if item]
        if data[key] != data_without_empty_items:
            print(f"[WARNING]: {task_id!s:s}: field {key:s} has empty items which are ignored", file=sys.stderr)
        data[key] = data_without_empty_items

    def parse_header(line: str) -> str:
        if "#" not in line:
            raise TaskHeaderNotFoundError("missing header")
        elif "##" in line:
            raise TaskHeaderNotFoundError("header is not top level. # Task title required.")
        else:
            header, _ = line.split("\n")
            return trim_whitespace_dash_and_hash(header)

    required_keys = ["STATUS", "PRIORITY", "TAGS", "DEPENDS"]
    out_types = {"STATUS": TaskStatus.from_string, "PRIORITY": int, "TAGS": to_list, "DEPENDS": to_taskid_list}
    out_data =  {"STATUS": TaskStatus.INVALID    , "PRIORITY": 100, "TAGS": [],      "DEPENDS": []}

    with filename.open("r") as f:
        line = f.readline()
        header = parse_header(line)

        line = f.readline(); expect_blank_line(line)

        # parse list items
        found_required_keys = []
        for i in range(len(required_keys)):
            line = f.readline()
            name, value = parse_list_items(line)
            found_required_keys.append(name)
            try:
                out_data[name] = out_types[name](value)
            except KeyError:
                raise MarkdownConvertValueError(
                    f"field {name:s} has wrong value of '{value:s}' which is not OPEN or CLOSED"
                )
            except ValueError:
                raise MarkdownConvertValueError(
                    f"field {name:s} conversion to {out_types[name]!s:s} failed to convert value {value:s} of type {type(value)!s:s}"
                )

        line = f.readline(); expect_blank_line(line)

        # parse remaining as body
        body = "".join(f.readlines())

        # now we check for consistency
        for required_key in required_keys:
            if required_key not in found_required_keys:
                raise RequiredElementNotFoundError(required_key)

        task_id = TaskID.from_string(filename.parent.stem)
        check_required_field_consistency(out_data, "TAGS",    task_id)
        check_required_field_consistency(out_data, "DEPENDS", task_id)

        return Task(
            task_file=filename,
            task_id=task_id,
            status=out_data.get("STATUS", TaskStatus.INVALID),
            priority=out_data.get("PRIORITY"),
            tags=out_data.get("TAGS"),
            depends=out_data.get("DEPENDS"),
            header=header,
            body=body,
        )


def read_task_from_file(task_file: Path, task_id: TaskID) -> tuple[bool, Task | None]:
    try:
        task = parse_task_file(task_file)
    except ExpectedTaskListItemNotFoundError as e:
        print(f"[ERROR]: {task_id:s}: while parsing task fields the following error occured: {e}")
        return False, None
    except TaskHeaderNotFoundError as e:
        print(f"[ERROR]: {task_id:s}: while parsing the task file header the following error occured: {e}", file=sys.stderr)
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
    except NotADirectoryError:
        return False, None
    else:
        return True, task


def write_task_to_file(task: Task):
    """Writes a task to file with filename stored in task"""
    with open(task.task_file, "w") as f:
        s = Template(TASK_MARKDOWN)
        depends_string = ""
        if task.depends:
            depends_string = " " + ", ".join(map(str, task.depends))
        mapping = {
            "title"     : task.header,
            "status"    : task.status.name,
            "priority"  : " " + str(task.priority),
            "tags"      : " " + ", ".join(task.tags),
            "depends"   : depends_string,
            "body"      : task.body,
        }
        f.write(s.substitute(mapping))


def build_task_dependencies(task: Task) -> list[Task]:
    task_folder: Path = task.task_file.parent.parent
    depends = []
    # requires full task ID
    # TODO (CS) cleanup code for dummy dependency. see 20261030-834808
    # we use a set to ignore duplicates
    for depend_task_id in set(task.depends):
        if depend_task_id == task.task_id:
            print(f"[WARNING]: {task.task_id!s:s}: Task depends recursively on itself. Ignored.", file=sys.stderr)
            continue

        depend_task_file = task_folder / Path(depend_task_id) / Path("TASK.md")
        try:
            depends.append(parse_task_file(depend_task_file))
        except (
            RequiredElementNotFoundError,
            TaskHeaderNotFoundError,
            MarkdownConvertValueError,
        ):
            depends.append(
                Task(
                    task_id=depend_task_id,
                    task_file=depend_task_file,
                    status=TaskStatus.INVALID,
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
                    status=TaskStatus.MISSING,
                    priority=1,
                    header="ERROR",
                    tags=[],
                    depends=[],
                )
            )
    return depends


def format_task_as_single_line(task: Task) -> str:
    return f"{task.task_file!s:s} {task.status.name:>6s} [PRIORITY: {task.priority:>3d}] [{','.join(task.tags)}] {task.header:s}"


def format_task_as_multiline(task: Task) -> str:
    task_folder: Path = task.task_file.parent.parent
    format_str = "{0:<12s}{1:s}\n"
    s = format_str.format("id:", task.task_id.to_string())
    s += format_str.format("title:", task.header)
    s += format_str.format("status:", task.status.name)
    s += format_str.format("priority:", str(task.priority))
    s += format_str.format("tags:", ", ".join(task.tags))

    # we need the status of any dependencies
    depends = [
        f"{depend_task.task_id!s:s} ({depend_task.status.name})"
        for depend_task in build_task_dependencies(task)
    ]
    s += format_str.format("depends:", ", ".join(depends))
    files = ", ".join([child.name for child in (task_folder / task.task_id).iterdir()])
    s += format_str.format("files:", files)
    s += format_str.format("path:", str(task.task_file))
    return s


def format_task_as_json(task: Task) -> str:
    return json.dumps(task.to_dict())


def format_tasks_as_json(tasks: list[Task]) -> str:
    return json.dumps([task.to_dict() for task in tasks])
