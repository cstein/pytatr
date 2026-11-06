# TAGS or DEPENDS with empty list items are carried on in TASK.md

 - STATUS: CLOSED
 - PRIORITY: 100
 - TAGS: bug, list
 - DEPENDS:

It was previously listed like so:
 - TAGS: bug, , list

which resulted in output for tatr ls like:

... [bug,,list]

