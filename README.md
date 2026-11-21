# pytatr
A python implementation of the TAsk TRacker ([tatr](https://github.com/tsoding/tatr)) idea to keep tasks anchored in the repo and not through some 3rd party broker.

## Goal
The goal is to have some feature parity (to my own needs at least) with the OG [tatr](https://github.com/tsoding/tatr) and to learn about stack based searches which was my original interest.

For me, it is a purely recreational programming project, but I also see the idea and value of the original project so it was an interesting quest.

## Installation

pytatr requires Python 3.12 or later. Clone the repository, create a virtual environment, and install the package:

```sh
git clone https://github.com/cstein/pytatr.git
cd pytatr
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

This installs pytatr and its runtime dependencies and makes the `tatr` command available. To install the development tools as well, use `python -m pip install -e ".[dev]"` instead.

## Usage
### Manipulating Tasks
`tatr` supports the following commands to manipulate tasks:
- `tatr init` which creates a folder `.tasks` in the current folder to store tasks.
- `tatr create <TITLE>` which creates a new task with a title. By default, a task is tagged as a bug with priority 100 (out of 100).
- `tatr set <FLAG> <VALUE> <TASK ID>` which sets a flag (`tags`, `depends`) of a task with task id `<TASK ID>` to `<VALUE>`. All supported flags and values are shown in the table below. Must match a single valid task id, but supports fuzzy matching.

| flag | value |
|------|------|
| `status` | `open` or `closed` |
| `priority` | any value between 1 and 100 |
| `tags` | any value allowed by the configuration (see below) |
| `depends` | any valid task id in the current project |

The `tatr set` command additonally allows you to specify valid `tags` and `depends` values with `+` or `-` to add or remove the values from the current ones instead of overwriting them.
For example, the following output for some tasks with id `6734` has a tag `bug`.
```sh
$ tatr show 6734
id:         20261116-673496
title:      demo ticket
status:     OPEN
priority:   50
tags:       bug
depends:    20261116-540397 (OPEN), 20261108-883218 (CLOSED)
files:      TASK.md
path:       .tasks/20261116-673496/TASK.md
```

One could override the tags completely with a `feature` tag using

```sh
$ tatr set tags feature 20261116-673496
$ tatr show 6734
id:         20261116-673496
title:      demo ticket
status:     OPEN
priority:   50
tags:       feature
depends:    20261116-540397 (OPEN), 20261108-883218 (CLOSED)
files:      TASK.md
path:       .tasks/20261116-673496/TASK.md
```

or simply add the `wontfix` tag in addition to the new `feature` tag using

```sh
$ tatr set tags +wontfix 20261116-673496
$ tatr show 6734
id:         20261116-673496
title:      demo ticket
status:     OPEN
priority:   50
tags:       feature, wontfix
depends:    20261116-540397 (OPEN), 20261108-883218 (CLOSED)
files:      TASK.md
path:       .tasks/20261116-673496/TASK.md
```

> [!CAUTION]
> The argparse module is picky with literal `-` (as in `-bug`) on the command line.
> Because of this, you have to escape any negation by a double dash: `--` *before*
> any negative values to signify that the next dash is interpreted as `-` and not
> some option

```sh
$ tatr set tags -- -wontfix 20261116-673496
```

> [!IMPORTANT]
> A ticket is in an invalid state if it has no tags.


### Viewing Tasks
`tatr` supports the following commands to view tasks:
- `tatr ls <QUERY>` which allows you to write a `<QUERY>` using a simple language (tql - the tatr query language). It is extremely simple and not fully implemented yet.
- `tatr show <TASK ID>` which allows you to show task information in more detail for a specific task id. Can optionally dump as json with `--json` flag.
- `tatr depends <TASK ID>` which allows you to show a dependency graph for a specific task id. Supports fuzzy matching.
- `tatr id <TASK ID>` which allows you to query for multiple ids matching the supplied task id. Supports fuzzy matching.

## Configuration
A `config.toml` file can be placed in the tasks folder (typically `.tasks`).
Currently, it supports a restriction on tags that are allowed be used in a project.
By default all tags are allowed.
A missing `config.toml` file corresponds to the following content:

```toml
[tags]
allowed = []
```

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
| `@ID` | matches a tag ID. Supports fuzzy matching. |

### Unary Operators
The search language in pytatr supports a single unary operator

| keyword | meaning |
|---------|---------|
| `not`   | negates a keyword |

### Binary Operators
The search language in pytatr supports two binary operators

| keyword | meaning |
|---------|---------|
| `and`   | evaluates to true of both `<A> and <B>` are fulfilled. |
| `or`   | evaluates to true of either `<A> or <B>` are fulfilled. |

> [!IMPORTANT]
> Be aware that in pytatr you cannot chain long expressions of binary operators.
