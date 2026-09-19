from enum import Enum


class Op_Kind(Enum):
    """Kind of operation supported"""

    OP_ANY = 1
    OP_NOT = 2
    OP_TAGGED = 3
    OP_STATUS_OPEN = 4
    OP_STATUS_CLOSED = 5

    def __repr__(self) -> str:
        return self.name


class Op:
    kind: Op_Kind

    def __init__(self, kind: Op_Kind):
        self.kind = kind

    def __repr__(self):
        return f"Op({self.kind!r:s})"


def chop(tokens: list[str]) -> str:
    return tokens.pop(0)


def peek(tokens: list[str]):
    return tokens[0] if tokens else None


def parse_not(tokens: list[str]) -> list[Op]:
    """unary operation not"""
    if peek(tokens) == "not":
        not_token = chop(tokens)
        return [parse_primary(tokens), Op(Op_Kind.OP_NOT)]
    return [parse_primary(tokens)]


def parse_primary(tokens: list[str]) -> Op:
    token = chop(tokens)
    match token:
        case "any":
            return Op(Op_Kind.OP_ANY)
        case "tagged":
            return Op(Op_Kind.OP_TAGGED)
        case "open":
            return Op(Op_Kind.OP_STATUS_OPEN)
        case "closed":
            return Op(Op_Kind.OP_STATUS_CLOSED)
        case _:
            raise ValueError(f"item '{token}' was not primary expression.")
    raise SyntaxError("Unexpected end of token stream")


def compile_query(tokens: list[str]) -> list[Op]:
    """Compiles an expression query into a series of operations on a stack"""
    query = []
    while peek(tokens) not in [None]:
        query.extend(parse_not(tokens))
    return query


def query_matches_task(
    query: list[Op_Kind], task: dict[str, str | int | list[str]]
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
                stack.append(len(task["TAGS"]) > 0)
            case Op_Kind.OP_STATUS_OPEN:
                stack.append(task["STATUS"].upper() == "OPEN")
            case Op_Kind.OP_STATUS_CLOSED:
                stack.append(task["STATUS"].upper() == "CLOSED")
            case _:
                raise ValueError
    assert len(stack) == 1
    return stack.pop()


if __name__ == "__main__":
    command = [":bug", "and", "priority", "gt", "90"]
    command = ["tagged"]
    query = compile_query(command)
    print("[QUERY]:", query)
    task = {"STATUS": "OPEN", "PRIORITY": 90, "TAGS": []}

    res = match(query, task)
    print(res)
