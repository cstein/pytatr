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
The `tatr ls` command will by default look for tags that has the status `OPEN` because its default query is `open` so the command is actually `tatr ls open` by default.
You can also search for tasks that has the status `CLOSED` either using a query like `closed` or even `not open`.
You can search for tags by using the special `:<TAG>` syntax.
For example, but default, all tasks have `TAGS: bug` which you can search for using the query `:bug`.
In its current installment, you can combine simple queries with a single `and` or `or`.
For example, so search for tasks that are closed but were not bugs, you could write

```sh
tatr ls closed and not :bug
```
