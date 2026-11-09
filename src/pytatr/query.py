from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import sys

from pytatr.task import Task, build_task_dependencies, TaskStatus


class Op_Kind(Enum):
    """Kind of operation supported"""

    OP_ANY = 1
    OP_NOT = 2
    OP_AND = 3
    OP_OR = 4
    OP_TAGGED = 5
    OP_STATUS_IS_OPEN = 6
    OP_STATUS_IS_CLOSED = 7
    OP_HAS_TAG = 8
    OP_DEPENDENCIES_ARE_BLOCKERS = 9
    OP_DEPENDENCIES_ARE_NOT_BLOCKERS = 10
    OP_HAS_TASKID = 11

    def __repr__(self) -> str:
        return self.name


@dataclass
class Op:
    """Operations allowed by the stack based search engine

    Holds an optional tag
    """

    kind: Op_Kind
    tag: str | None = None
    task_id: str | None = None

    def __repr__(self):
        return f"Op({self.kind!r:s})"


class QueryError(Exception):
    pass

class QueryKeywordError(Exception):
    pass

class QuerySyntaxError(Exception):
    pass


def chop(tokens: list[str]) -> str:
    try:
        token = tokens.pop(0)
    except IndexError:
        raise QueryError("unexpected end of query")
    else:
        if len(token) == 0:
            raise QueryError("unexpected empty query")
        return token


def peek(tokens: list[str]) -> str | None:
    return tokens[0] if tokens else None


def parse_or(tokens: list[str]) -> list[Op]:
    a = parse_and(tokens)
    if peek(tokens) == "or":
        and_token = chop(tokens)
        return a + parse_and(tokens) + [Op(Op_Kind.OP_OR)]
    return a


def parse_and(tokens: list[str]) -> list[Op]:
    """binary operation and"""
    a = parse_not(tokens)
    if peek(tokens) == "and":
        and_token = chop(tokens)
        return a + parse_not(tokens) + [Op(Op_Kind.OP_AND)]
    return a


def parse_not(tokens: list[str]) -> list[Op]:
    """unary operation not"""
    if peek(tokens) == "not":
        not_token = chop(tokens)  # disregarded and inserted as Op below
        return parse_primary(tokens) + [Op(Op_Kind.OP_NOT)]
    return parse_primary(tokens)


def parse_primary(tokens: list[str]) -> list[Op]:
    """Parse a primary expression

    A primary expression is the simplest kind og expression.

    :param tokens: the token stream
    """
    token = chop(tokens)
    if token[0] == ":":
        if not token[1:]:
            raise QuerySyntaxError("got ':' but expected :<TAG>")
        return [Op(Op_Kind.OP_HAS_TAG, tag=token[1:])]

    if token[0] == "@":
        if not token[1:]:
            raise QuerySyntaxError("got '@' but expted :<TASKID>")
        return [Op(Op_Kind.OP_HAS_TASKID, task_id=token[1:])]

    match token:
        case "any":
            return [Op(Op_Kind.OP_ANY)]
        case "tagged":
            return [Op(Op_Kind.OP_TAGGED)]
        case "open":
            return [Op(Op_Kind.OP_STATUS_IS_OPEN)]
        case "closed":
            return [Op(Op_Kind.OP_STATUS_IS_CLOSED)]
        case "blocked":
            return [Op(Op_Kind.OP_DEPENDENCIES_ARE_BLOCKERS)]
        case "unblocked":
            return [Op(Op_Kind.OP_DEPENDENCIES_ARE_NOT_BLOCKERS)]
        case _:
            raise QueryKeywordError(f"'{token}' is not a valid keyword.")


def compile_query(tokens: list[str]) -> list[Op]:
    """Compiles an expression query into a series of operations on a stack"""
    org_query = " ".join(tokens)
    query = parse_or(tokens)
    # for more complicated queries we need to parse more using the while loop below
    # while peek(tokens) not in [None]:
    #     query.extend(parse_or(tokens))
    if tokens:
        raise QueryError(f"unexpected token '{tokens[0]:s}' in query")
    return query


def query_matches_task(
    query: list[Op],
    task: Task,
    task_folder: Path,
) -> bool:
    """Matches a compiled query with a specific task"""

    stack = []
    for op in query:
        match op.kind:
            case Op_Kind.OP_ANY:
                stack.append(True)
            case Op_Kind.OP_NOT:
                value = stack.pop()
                stack.append(not value)
            case Op_Kind.OP_TAGGED:
                stack.append(len(task.tags) > 0)
            case Op_Kind.OP_STATUS_IS_OPEN:
                stack.append(task.status == TaskStatus.OPEN)
            case Op_Kind.OP_STATUS_IS_CLOSED:
                stack.append(task.status == TaskStatus.CLOSED)
            case Op_Kind.OP_HAS_TAG:
                stack.append(op.tag in task.tags)
            case Op_Kind.OP_DEPENDENCIES_ARE_BLOCKERS:
                stack.append(TaskStatus.OPEN     in [t.status for t in build_task_dependencies(task, task_folder)])
            case Op_Kind.OP_DEPENDENCIES_ARE_NOT_BLOCKERS:
                stack.append(TaskStatus.OPEN not in [t.status for t in build_task_dependencies(task, task_folder)])
            case Op_Kind.OP_HAS_TASKID:
                stack.append(op.task_id == task.task_id)
            case Op_Kind.OP_AND:
                a = stack.pop()
                b = stack.pop()
                stack.append(a and b)
            case Op_Kind.OP_OR:
                a = stack.pop()
                b = stack.pop()
                stack.append(a or b)
            case _:
                raise RuntimeError(f"Operation {op!s:s} not supported.")
    assert len(stack) == 1
    return stack.pop()
