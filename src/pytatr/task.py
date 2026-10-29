from dataclasses import dataclass
from pathlib import Path


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

    def __str__(self):
        return f"{self.task_file!s:s}:1: {self.status:>6s} [PRIORITY: {self.priority:>3d}] [{','.join(self.tags)}] {self.header:s}"
