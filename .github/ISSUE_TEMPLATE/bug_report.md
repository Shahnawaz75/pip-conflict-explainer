---
name: Bug report
about: pip-conflict misread an error, crashed, or suggested versions that do not work
title: "[bug] "
labels: bug
---

**What happened**
A short description of what pip-conflict printed and what you expected instead.

**The pip or uv output**
Attach the complete output as a file (for example `pip install ... > error.txt 2>&1`), or paste it here:

```text

```

Please remove anything private first (internal package names, index URLs, tokens, user names in paths).

**The pip-conflict command and its output**

```text
$ pip-conflict explain error.txt

```

`--json` output is even more useful.

**Environment**
- pip-conflict version (`pip-conflict --version`):
- Python version that produced the error:
- pip / uv version:
- OS:
