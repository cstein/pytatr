from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import time
import random
import re
import sys

DATE_FORMAT = "%Y%m%d"
REGEX_PATTERN = r"^\d{4}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])-[A-Za-z0-9]{6}$"
CHARS = "0123456789"
NUM_CHARS = 6


class InvalidTaskIDError(ValueError):
    pass

class InvalidTaskIDDateValueError(ValueError):
    pass

class NoTaskIDMatchError(ValueError):
    pass

class AmbiguousTaskIDMatchError(ValueError):
    pass


@dataclass(eq=True, frozen=True)
class TaskID:
    first: str
    last: str

    @classmethod
    def generate(cls):
        time_dict  = time.localtime()
        first = time.strftime(DATE_FORMAT, time_dict)
        last  = "".join([random.choice(CHARS) for _ in range(NUM_CHARS)])
        return cls(first=first, last=last)

    @classmethod
    def from_string(cls, value: str):
        if re.fullmatch(REGEX_PATTERN, value) is None:
            raise InvalidTaskIDError(f"The supplied id {value:s} is not valid. Format is YYYYMMDD-XXXXXX with X any valid alphanumerical character.")
        first, last = value.split("-")
        try:
            datetime.strptime(first, DATE_FORMAT)
        except ValueError as e:
            raise InvalidTaskIDDateValueError(e)
        return cls(first=first, last=last)

    def to_string(self):
        return f"{self.first:s}-{self.last:s}"

    def __fspath__(self):
        return self.to_string()

    def __str__(self):
        return self.to_string()

    def to_dict(self) -> dict:
        return {"first": self.first, "last": self.last}


def resolve_task_ids(task_folder: Path, unresolved_id: TaskID) -> set[None | TaskID]:
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


def resolve_unique_task_id(task_folder: Path, unresolved_id: TaskID) -> TaskID:
    """Resolves a unique task id based on a (potentially) unresolved id"""
    unique_ids = resolve_task_ids(task_folder, unresolved_id)
    if not unique_ids:
        raise NoTaskIDMatchError(f"query '{unresolved_id}' found no matching tasks")
    elif len(unique_ids) > 1:
        raise AmbiguousTaskIDMatchError(f"query '{unresolved_id}' is ambiguous: {', '.join([i for i in unique_ids])}")
    return unique_ids.pop()
