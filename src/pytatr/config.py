import tomllib
from argparse import Namespace
from dataclasses import dataclass, field
from pathlib import Path


@dataclass()
class Config:
    allowed_tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict):
        tags_section: dict = value.get("tags", {})
        allowed_tags: list[str] = tags_section.get("allowed", [])
        return cls(allowed_tags=allowed_tags)


def load_config(args: Namespace) -> Config | None:
    """There is no mandatory config file, so we should just return an empty Config"""
    config_file = args.task_folder / Path("config.toml")
    if config_file.exists():
        with config_file.open("rb") as f:
            return Config.from_dict(tomllib.load(f))
    return Config()


