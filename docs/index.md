---
title: pip-conflict-explainer
description: Understand pip and uv dependency conflicts (ResolutionImpossible, "Cannot install ... because these package versions have conflicting dependencies") in plain English and get versions that actually install.
---

# pip-conflict-explainer

**Understand pip dependency conflicts (ResolutionImpossible) and get versions that work.**

`pip-conflict` reads the error pip or uv printed, explains in plain English who requires what and where the clash is, and checks PyPI for versions that work with your Python version and platform. It is a small, MIT-licensed command line tool and Python library with one dependency (`packaging`).

```text
$ pip install --dry-run pandas==2.2.0 numpy==1.21.0 2>&1 | pip-conflict explain
Dependency conflict (pip ResolutionImpossible)
Target: Python 3.10.22 on win-amd64 (detected from the pip output)

You pinned numpy==1.21.0, but pandas 2.2.0 needs numpy>=1.22.4,<2 (for python_version < "3.11").
numpy 1.21.0 is too old for pandas 2.2.0.
numpy 1.21.0 has no wheel for Python 3.10 on win-amd64, so pip has to build it from source.

Versions that work (checked on PyPI):
  Option 1: relax your pin `numpy==1.21.0` -> `numpy>=1.22.4,<2` (newest that fits: 1.26.4)
  Option 2: keep numpy 1.21.0 and use `pandas<=2.0.3`
            note: no wheel for Python 3.10 on win-amd64: numpy 1.21.0 (pip would build from source)
  Option 3: change `numpy==1.21.0` -> `numpy>=1.22.4` and `pandas==2.2.0` -> `pandas==2.3.3` (newest
            that fits: numpy 2.2.6, pandas 2.3.3)

Check option 1 without installing anything:
  pip install --dry-run "numpy>=1.22.4,<2" "pandas==2.2.0"
```

## Install

```bash
pip install git+https://github.com/Shahnawaz75/pip-conflict-explainer
```

Python 3.10 or newer. A PyPI release is coming soon.

## Use it

| You have | Run |
| --- | --- |
| A pip error on screen | `pip install ... 2>&1 \| pip-conflict explain` |
| A saved log | `pip-conflict explain error.txt` |
| A uv error | `uv pip compile requirements.txt 2>&1 \| pip-conflict explain --python 3.12` |
| A requirements file you have not installed yet | `pip-conflict check requirements.txt` (runs `pip install --dry-run`, installs nothing) |
| A `pyproject.toml` | `pip-conflict check pyproject.toml` |
| Broken installed packages | `pip check \| pip-conflict explain` |
| A CI job | `pip-conflict check requirements.txt --strict` |

Add `--json` for machine-readable output, `--offline` to skip PyPI, and `--python 3.12` / `--platform linux` to target another environment.

## Read more

- [Common pip and uv dependency errors](common-errors.md): the literal messages, what causes them, and how to fix them.
- [Real example output](example-output.md): unedited runs on real conflicts, and `pip install --dry-run` checks of the suggested versions.
- [README on GitHub](https://github.com/Shahnawaz75/pip-conflict-explainer#readme): all options, the Python API, how it works, limitations and FAQ.
- [Report a problem](https://github.com/Shahnawaz75/pip-conflict-explainer/issues): please attach the complete pip or uv output.
