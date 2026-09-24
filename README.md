# pytatr
python implementation of the TAsk TRacker idea.

## Goal
The goal is to have some feature parity (to my own needs at least) with the OG [tatr by tsoding](https://github.com/tsoding/tatr).

For me, it is a purely recreational programming project, but I also see the idea and value of the original project.

## Installation
```sh
git clone XX
pip install -e .[dev]
```
and now you have the `tatr` command available to you.

## Usage
tatr supports the following commands:
- `tatr init` which creates a folder `.tasks` in the current folder to store tasks
- `tatr create <TITLE>` which creates a new task with a title. By default, a task is tagged as a bug with priority 100 (out of 100).
- `tatr ls <QUERY>` which allows you to write a `<QUERY>` using a simple language (tql - the tatr query language). It is extremely simple and not fully implemented yet.

## Searching for Tasks
The default `<QUERY>` is `open` and `tatr ls` will by default return the tasks that have the status `OPEN`.

You can also search for tasks that has the status `CLOSED` either using a query like `closed` or even `not open`.

You can search for tags by using the special `:<TAG>` syntax.
For example, but default, all tasks have `TAGS: bug` which you can search for using the query `:bug`.

In its current installment, you can combine simple queries with a single `and` or `or`.
For example, so search for tasks that are closed but were not bugs, you could write

```sh
$ tatr ls closed and not :bug
.tasks/20260917-944384/TASK.md:1: CLOSED [PRIORITY:  50] [feature] print tas...
.tasks/20260917-701743/TASK.md:1: CLOSED [PRIORITY:  60] [feature] cap print...
.tasks/20260915-583503/TASK.md:1: CLOSED [PRIORITY: 100] [feature] Implement...
.tasks/20260917-594907/TASK.md:1: CLOSED [PRIORITY: 100] [feature] sorting o...
.tasks/20260917-647548/TASK.md:1: CLOSED [PRIORITY: 100] [feature] create ke...
.tasks/20260917-757207/TASK.md:1: CLOSED [PRIORITY: 100] [feature] search sh...
.tasks/20260917-774055/TASK.md:1: CLOSED [PRIORITY: 100] [feature] create se...
```

### Keywords
The search only supports a subset of the original [tatr](https://github.com/tsoding/tatr) and will maybe be expanded in the future depending on my needs.

The supported keywords are
| keyword | meaning |
|---------|---------|
| `open`  | has a STATUS: OPEN |
| `closed`| has a STATUS: CLOSED |
| `tagged`| has any `<TAG>` in the TAGS field |
| `any`   | return all tasks |
| `:<TAG>` | has a tag `<TAG`> in the TAGS field. case sensitive. |
|---------|------------------|

### Unary Operators
The search language in pytatr supports a single unary operator

| keyword | meaning |
|---------|---------|
| `not`   | negates a keyword |
|---------|------------------|

### Binary Operators
The search language in pytatr supports two binary operators

| keyword | meaning |
|---------|---------|
| `and`   | evaluates to true of both `<A> and <B>` are fulfilled. |
| `or`   | evaluates to true of either `<A> or <B>` are fulfilled. |
|---------|------------------|

**NB:** be aware that in pytatr you cannot chain long expressions of binary operators.
