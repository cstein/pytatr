"""ArgumentParser builder"""
from argparse import Action, ArgumentParser
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Parsers:
    main_parser   : ArgumentParser
    create_parser : ArgumentParser | None = None
    set_parser    : ArgumentParser | None = None


class ConcatenateStringsAction(Action):
    """Concatenate inputs into one string"""

    def __call__(self, parser, namespace, values, option_string=None):
        value = " ".join(values)
        setattr(namespace, self.dest, value)


class ToPathType(Action):
    def __call__(self, parser, namespace, value, option_string=None):
        setattr(namespace, self.dest, Path(value))


def build_parsers() -> Parsers:
    ap = ArgumentParser(description="A local task tracker.")
    _add_global_args(ap)

    subparsers = ap.add_subparsers(help="Commands", dest="command", required=True)

    ap_create = _add_create_parser(subparsers)
    _add_list_parser(subparsers)
    _add_init_parser(subparsers)
    _add_deps_parser(subparsers)
    _add_show_parser(subparsers)
    _add_id_parser(subparsers)
    ap_set = _add_set_parser(subparsers)

    return Parsers(main_parser=ap, create_parser=ap_create, set_parser=ap_set)


def _add_global_args(ap: ArgumentParser) -> None:
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


def _add_create_parser(subparsers) -> ArgumentParser:
    p = subparsers.add_parser("create", help="Create a note")
    p.add_argument(
        "title",
        default=None,
        nargs="+",
        type=str,
        help="Title of the task",
        action=ConcatenateStringsAction,
    )
    p.add_argument(
        "-t",
        "--tags",
        default=["bug"],
        nargs="+",
        help="List of tags. Default is bug.",
    )
    p.add_argument(
        "-p",
        "--priority",
        default=100,
        type=int,
        metavar="NUMBER",
        help="Priority of task. 1 is lowest, 100 is highest. Default is %(default)s.",
    )
    p.add_argument(
        "--depends",
        default=[],
        nargs="*",
        metavar="TASKID",
        help="Task IDs this task is dependent on direct. Must be existing tasks.",
    )
    p.add_argument(
        "--blocks",
        default=[],
        nargs="*",
        metavar="TASKID",
        help="Task IDs that this task will block. Must be existing tasks. (updates dependencies of these tasks).",
    )
    p.add_argument(
        "--body-file",
        type=Path,
        metavar="FILE",
        action=ToPathType,
        default=None,
        help="premade content of a task body.",
    )
    return p


def _add_list_parser(subparsers) -> None:
    p = subparsers.add_parser("ls", help="list tasks.")
    p.add_argument(
        "query",
        default=["open"],
        nargs="*",
        help="Search query for tasks. Default is 'open'.",
    )
    p.add_argument(
        "-r",
        dest="sort_reversed",
        default=False,
        action="store_true",
        help="reverse listing.",
    )
    p.add_argument(
        "-p",
        dest="sort_priority",
        default=False,
        action="store_true",
        help="use priority to sort tasks. important first.",
    )
    p.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        default=False,
        help="output json instead of plain text",
    )
    p.add_argument(
        "-i",
        dest="only_show_ids",
        default=False,
        action="store_true",
        help="only show ids of tasks matching the query.",
    )


def _add_init_parser(subparsers) -> None:
    p = subparsers.add_parser("init", help="Creates the task folder.")
    p.add_argument(
        "-v", dest="verbose", default=False, action="store_true", help="verbose output."
    )


def _add_deps_parser(subparsers) -> None:
    ap_deps = subparsers.add_parser("depends", help="lists a dependency tree")
    ap_deps.add_argument(
        "id",
        default=None,
        type=str,
        metavar="TASKID",
        help="id of the task. can be fuzzy",
    )


def _add_show_parser(subparsers) -> None:
    p = subparsers.add_parser("show", help="show a task with details.")
    p.add_argument(
        "id",
        default=None,
        type=str,
        metavar="TASKID",
        help="id of the task. can be fuzzy",
    )
    p.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        default=False,
        help="output json instead of plain text",
    )


def _add_id_parser(subparsers) -> None:
    p = subparsers.add_parser("id", help="resolves task ids (or parts thereof) into valid ids.")
    p.add_argument(
        "id",
        default=None,
        type=str,
        metavar="TASKID",
        help="id of the task(s). can match random part of task id",
    )
    p.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        default=False,
        help="output json instead of plain text",
    )


def _add_set_parser(subparsers) -> ArgumentParser:
    p = subparsers.add_parser("set", help="set various fields from the command line")
    p_subparsers = p.add_subparsers(help="fields to set", dest="field", required=True)

    p_status = p_subparsers.add_parser("status", help="set the status of a task")
    p_status.add_argument(
        "status",
        choices=("open", "closed"),
        type=str,
        metavar="STATUS",
        help="should be one of: [%(choices)s]",
    )
    p_status.add_argument(
        "id",
        type=str,
        metavar="TASKID",
        help="id of the task. must match exactly one task",
    )

    p_tags = p_subparsers.add_parser("tags", help="set the tags of a task")
    p_tags.add_argument(
        "tags",
        default=[],
        nargs="+",
        help="list of tags to set.",
    )
    p_tags.add_argument(
        "id",
        type=str,
        metavar="TASKID",
        help="id of the task. must match exactly one task",
    )

    p_depends = p_subparsers.add_parser("depends", help="set the dependencies of a task")
    p_depends.add_argument(
        "depends",
        default=[],
        nargs="*",
        help="list of dependencies to set. empty means clear",
    )
    p_depends.add_argument(
        "id",
        type=str,
        metavar="TASKID",
        help="id of the task. must match exactly one task",
    )
    return p
