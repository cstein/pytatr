# Ignore regular files and folders such as .DS_Store when listing tasks

 - STATUS: CLOSED
 - PRIORITY: 80
 - TAGS: bug
 - DEPENDS: 

## Problem

`tatr ls open -p` crashes if the task directory contains a regular file such as macOS's `.DS_Store`. This was encountered in `comx-d/.tasks/` and independently reproduced in an otherwise empty temporary task directory.

## Reproduction

Run with the current tatr checkout/environment active:

```sh
repro_dir="$(mktemp -d)"
tatr -f "$repro_dir/.tasks" init
touch "$repro_dir/.tasks/.DS_Store"
tatr -f "$repro_dir/.tasks" ls open -p
```

Observed: exit status 1 and an uncaught traceback ending in:

```text
NotADirectoryError: [Errno 20] Not a directory: '.../.tasks/.DS_Store/TASK.md'
```

Expected: ignore the unrelated regular file and return the normal empty listing. With real tasks present, list those tasks normally.

## Location and likely cause

`src/pytatr/pytatr.py::print_query_tasks()` loops over every child of the task folder and unconditionally constructs `child / "TASK.md"`. It then calls `read_task_from_file()` -> `parse_task_file()` in `src/pytatr/task.py`. Opening a path beneath a regular file raises `NotADirectoryError`.

The failing enumeration was at pytatr.py lines 142-144 when reproduced. Inspect the function by name because line numbers may change. A regular-file check at enumeration should prevent treating `.DS_Store` as a task folder; hiding or deleting the specific file does not fix the underlying behavior.

## Acceptance criteria

- `tatr ls` ignores regular files in the task directory, including `.DS_Store` and ordinary text files.
- Listings still return valid tasks when unrelated files coexist with them, including JSON output.
- Preserve intentional validation/error reporting for actual task folders and malformed TASK.md files.
- Add regression coverage for an empty directory plus a regular file and for valid tasks alongside regular files.

Verified on macOS with Python 3.12 using the installed tatr entry point backed by this checkout. Existing `tatr create` and `tatr show ID` continued to work in the affected comx-d task folder.

Original discovery tracking: `/Users/steinmann/Development/comx-d/.tasks/20261112-045137/TASK.md`.

