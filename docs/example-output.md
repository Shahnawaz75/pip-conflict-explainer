---
title: Real example output
description: Unedited output of pip-conflict on real pip and uv dependency errors (pandas/numpy, requests/urllib3, boto3/aiobotocore, tensorflow, Requires-Python), plus pip --dry-run checks of the suggested versions.
---

# Real example output

Everything below is unedited output from real runs on 24 November 2026. The setup was Windows 11 with Python 3.10.22 and 3.14.10 in fresh virtual environments, pip 26.3, uv 0.13.9 and pip-conflict 0.1.0. PyPI was queried read-only. Each block shows the command and its full output. Long lines were wrapped by pip-conflict itself at 100 characters.

The raw pip and uv messages for most of these cases are quoted in [common pip and uv dependency errors](common-errors.md).

## pandas 2.2.0 with numpy 1.21.0 (Python 3.10)

pip's own output first, then the same command piped into pip-conflict.

```text
$ pip install --dry-run pandas==2.2.0 numpy==1.21.0
Collecting pandas==2.2.0
  Using cached pandas-2.2.0-cp310-cp310-win_amd64.whl.metadata (19 kB)
Collecting numpy==1.21.0
  Using cached numpy-1.21.0.zip (10.3 MB)
  Installing build dependencies: started
  Installing build dependencies: finished with status 'done'
  Getting requirements to build wheel: started
  Getting requirements to build wheel: finished with status 'done'
  Preparing metadata (pyproject.toml): started
  Preparing metadata (pyproject.toml): finished with status 'done'
ERROR: Cannot install numpy==1.21.0 and pandas==2.2.0 because these package versions have conflicting dependencies.

The conflict is caused by:
    The user requested numpy==1.21.0
    pandas 2.2.0 depends on numpy<2 and >=1.22.4; python_version < "3.11"

Additionally, some packages in these conflicts have no matching distributions available for your environment:
    numpy

To fix this you could try to:
1. loosen the range of package versions you've specified
2. remove package versions to allow pip to attempt to solve the dependency conflict

ERROR: ResolutionImpossible: for help visit https://pip.pypa.io/en/latest/topics/dependency-resolution/#dealing-with-dependency-conflicts
```

Exit code: `1`

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

pip also listed numpy under "no matching distributions available for your environment". Recent pip
versions print that line for every package in a conflict, so on its own it does not mean a package
is missing.
```

Exit code: `0`

## requests 2.31.0 with urllib3 1.20 (Python 3.14)

```text
$ pip install --dry-run requests==2.31.0 urllib3==1.20
Collecting requests==2.31.0
  Using cached requests-2.31.0-py3-none-any.whl.metadata (4.6 kB)
Collecting urllib3==1.20
  Using cached urllib3-1.20-py2.py3-none-any.whl.metadata (29 kB)
Collecting charset-normalizer<4,>=2 (from requests==2.31.0)
  Using cached charset_normalizer-3.5.3-cp314-cp314-win_amd64.whl.metadata (44 kB)
Collecting idna<4,>=2.5 (from requests==2.31.0)
  Using cached idna-3.20-py3-none-any.whl.metadata (7.2 kB)
ERROR: Cannot install requests==2.31.0 and urllib3==1.20 because these package versions have conflicting dependencies.

The conflict is caused by:
    The user requested urllib3==1.20
    requests 2.31.0 depends on urllib3<3 and >=1.21.1

Additionally, some packages in these conflicts have no matching distributions available for your environment:
    urllib3

To fix this you could try to:
1. loosen the range of package versions you've specified
2. remove package versions to allow pip to attempt to solve the dependency conflict

ERROR: ResolutionImpossible: for help visit https://pip.pypa.io/en/latest/topics/dependency-resolution/#dealing-with-dependency-conflicts
```

Exit code: `1`

```text
$ pip install --dry-run requests==2.31.0 urllib3==1.20 2>&1 | pip-conflict explain
Dependency conflict (pip ResolutionImpossible)
Target: Python 3.14.10 on win-amd64 (detected from the pip output)

You pinned urllib3==1.20, but requests 2.31.0 needs urllib3>=1.21.1,<3.
urllib3 1.20 is too old for requests 2.31.0.

Versions that work (checked on PyPI):
  Option 1: relax your pin `urllib3==1.20` -> `urllib3>=1.21.1,<3` (newest that fits: 2.8.0)
  Option 2: keep urllib3 1.20 and use `requests<=2.15.1`
  Option 3: change `urllib3==1.20` -> `urllib3>=1.26,<3` and `requests==2.31.0` ->
            `requests==2.34.2` (newest that fits: urllib3 2.8.0, requests 2.34.2)

Check option 1 without installing anything:
  pip install --dry-run "urllib3>=1.21.1,<3" "requests==2.31.0"

pip also listed urllib3 under "no matching distributions available for your environment". Recent pip
versions print that line for every package in a conflict, so on its own it does not mean a package
is missing.
```

Exit code: `0`

## boto3 with aiobotocore: a transitive conflict (Python 3.14)

Neither pin mentions botocore; both packages pin it to ranges that do not overlap.

```text
$ pip install --dry-run boto3==1.34.0 aiobotocore==2.5.0 2>&1 | pip-conflict explain
Dependency conflict (pip ResolutionImpossible)
Target: Python 3.14.10 on win-amd64 (current interpreter)

boto3 1.34.0 needs botocore>=1.34.0,<1.35.0, but aiobotocore 2.5.0 needs botocore>=1.29.76,<1.29.77.
No version of botocore matches both >=1.34.0,<1.35.0 and >=1.29.76,<1.29.77.

Versions that work (checked on PyPI):
  Option 1: upgrade your pin `aiobotocore==2.5.0` -> `aiobotocore==2.13.3`
  Option 2: keep aiobotocore 2.5.0 and use `boto3<=1.26.76`
  Option 3: change `boto3==1.34.0` -> `boto3==1.43.117` and `aiobotocore==2.5.0` ->
            `aiobotocore==3.10.0` (newest that fits: boto3 1.43.117, aiobotocore 3.10.0)

Check option 1 without installing anything:
  pip install --dry-run "boto3==1.34.0" "aiobotocore==2.13.3"

pip also listed botocore under "no matching distributions available for your environment". Recent
pip versions print that line for every package in a conflict, so on its own it does not mean a
package is missing.
```

Exit code: `0`

## A constraints file clash (Python 3.14)

`requirements.txt` contains `requests==2.31.0`, `constraints.txt` contains `urllib3<1.21`.

```text
$ pip install --dry-run -r requirements.txt -c constraints.txt 2>&1 | pip-conflict explain
Dependency conflict (pip ResolutionImpossible)
Target: Python 3.14.10 on win-amd64 (detected from the pip output)

Your constraints say urllib3<1.21, but requests 2.31.0 needs urllib3>=1.21.1,<3.
No version of urllib3 matches both <1.21 and >=1.21.1,<3.

Versions that work (checked on PyPI):
  Option 1: change your constraint `urllib3<1.21` -> `urllib3>=1.21.1,<3` (newest that fits: 2.8.0)
  Option 2: keep your constraint urllib3<1.21 and use `requests<=2.15.1`
  Option 3: change `urllib3<1.21` -> `urllib3>=1.26,<3` and `requests==2.31.0` -> `requests==2.34.2`
            (newest that fits: urllib3 2.8.0, requests 2.34.2)

Check option 1 without installing anything:
  pip install --dry-run "requests==2.31.0" -c constraints.txt   # after updating the constraint

pip also listed urllib3 under "no matching distributions available for your environment". Recent pip
versions print that line for every package in a conflict, so on its own it does not mean a package
is missing.
```

Exit code: `0`

## tensorflow 2.15.0 on Python 3.14 (no wheel), with and without --pre

```text
$ pip install --dry-run tensorflow==2.15.0 2>&1 | pip-conflict explain
No matching distribution
Target: Python 3.14.10 on win-amd64 (current interpreter)

No tensorflow release matches `tensorflow==2.15.0`. pip could only see pre-releases: 2.22.0rc0,
2.22.0rc1.
tensorflow 2.15.0 has no wheel for Python 3.14 on win-amd64 (its wheels are for Python 3.9, 3.10 and
3.11).
Only pre-releases of tensorflow support Python 3.14 on win-amd64 so far (newest: 2.22.0rc1); add
--pre to consider them.
To keep tensorflow 2.15.0, use Python 3.9, 3.10 or 3.11.
```

Exit code: `1`

```text
$ pip install --dry-run tensorflow==2.15.0 2>&1 | pip-conflict explain --pre
No matching distribution
Target: Python 3.14.10 on win-amd64 (current interpreter)

No tensorflow release matches `tensorflow==2.15.0`. pip could only see pre-releases: 2.22.0rc0,
2.22.0rc1.
tensorflow 2.15.0 has no wheel for Python 3.14 on win-amd64 (its wheels are for Python 3.9, 3.10 and
3.11).
To keep tensorflow 2.15.0, use Python 3.9, 3.10 or 3.11.

Versions that work (checked on PyPI):
  Option 1: upgrade your pin `tensorflow==2.15.0` -> `tensorflow==2.22.0rc1`

Check option 1 without installing anything:
  pip install --dry-run "tensorflow==2.22.0rc1"
```

Exit code: `0`

## A package that does not exist

```text
$ pip install --dry-run this-package-does-not-exist-pce 2>&1 | pip-conflict explain
No matching distribution
Target: Python 3.14.10 on win-amd64 (current interpreter)

pip found no installable version of this-package-does-not-exist-pce at all: either the name is
misspelled, or this-package-does-not-exist-pce has no files for this Python version and platform.
this-package-does-not-exist-pce does not exist on PyPI. Check the spelling, or whether it comes from
another index.
```

Exit code: `1`

## A version that does not exist

```text
$ pip install --dry-run requests==9.9 2>&1 | pip-conflict explain
No matching distribution
Target: Python 3.14.10 on win-amd64 (current interpreter)

No requests release matches `requests==9.9`. The newest version pip could see is 2.34.2.

Versions that work (checked on PyPI):
  Option 1: use `requests==2.34.2` instead of `requests==9.9`

Check option 1 without installing anything:
  pip install --dry-run "requests==2.34.2"
```

Exit code: `0`

## numpy 2.3.0 on Python 3.10 (Requires-Python)

```text
$ pip install --dry-run numpy==2.3.0 2>&1 | pip-conflict explain
Python version mismatch
Target: Python 3.10.22 on win-amd64 (current interpreter)

numpy 2.3.0 needs Python >=3.11; you have 3.10.
The newest numpy that pip could use on this Python is 2.2.6.

Versions that work (checked on PyPI):
  Option 1: use `numpy<=2.2.6` instead of `numpy==2.3.0`
            note: numpy 2.3.0 needs Python >=3.11; you have 3.10.

Check option 1 without installing anything:
  pip install --dry-run "numpy<=2.2.6"
```

Exit code: `0`

## A local project that requires a newer Python

`demo-app/pyproject.toml` declares `requires-python = ">=3.11"`; pip runs on Python 3.10.

```text
$ pip install --dry-run ./demo-app 2>&1 | pip-conflict explain
Python version mismatch
Target: Python 3.10.22 on win-amd64 (detected from the pip output)

demo-app needs Python >=3.11; you have 3.10.22.
Run pip with a Python that matches >=3.11 (for example Python 3.11), or lower requires-python if you
maintain the package.
```

Exit code: `1`

## uv: pandas 2.2.0 with numpy 1.21.0

```text
$ uv pip compile requirements.txt --python-version 3.10
error: No solution found when resolving dependencies
  cause: Because pandas==2.2.0 depends on numpy{python_full_version < '3.11'}>=1.22.4,<2 and you require pandas==2.2.0, we can conclude that you require numpy>=1.22.4,<2.
         And because you require numpy==1.21.0, we can conclude that your requirements are unsatisfiable.
```

Exit code: `1`

```text
$ uv pip compile requirements.txt --python-version 3.10 2>&1 | pip-conflict explain --python 3.10
Dependency conflict (uv: no solution found)
Target: Python 3.10.22 on win-amd64 (--python)

You pinned numpy==1.21.0, but pandas 2.2.0 needs numpy>=1.22.4,<2 (for python_full_version <
"3.11").
numpy 1.21.0 is too old for pandas 2.2.0.
numpy 1.21.0 has no wheel for Python 3.10 on win-amd64, so pip has to build it from source.

Versions that work (checked on PyPI):
  Option 1: relax your pin `numpy==1.21.0` -> `numpy>=1.22.4,<2` (newest that fits: 1.26.4)
  Option 2: keep numpy 1.21.0 and use `pandas<=2.0.3`
            note: no wheel for Python 3.10 on win-amd64: numpy 1.21.0 (pip would build from source)
  Option 3: change `pandas==2.2.0` -> `pandas==2.3.3` and `numpy==1.21.0` -> `numpy>=1.22.4` (newest
            that fits: pandas 2.3.3, numpy 2.2.6)

Check option 1 without installing anything:
  pip install --dry-run "pandas==2.2.0" "numpy>=1.22.4,<2"
```

Exit code: `0`

## uv: tensorflow 2.15.0 on Python 3.14

```text
$ uv pip install --dry-run tensorflow==2.15.0
Using Python 3.14.10 environment at: .venv314
error: No solution found when resolving dependencies
  cause: Because tensorflow==2.15.0 has no wheels with a matching Python ABI tag (e.g., `cp314`) and you require tensorflow==2.15.0, we can conclude that your requirements are unsatisfiable.

hint: You require CPython 3.14 (`cp314`), but we only found wheels for `tensorflow` (v2.15.0) with the following Python ABI tags: `cp39`, `cp310`, `cp311`
```

Exit code: `1`

```text
$ uv pip install --dry-run tensorflow==2.15.0 2>&1 | pip-conflict explain
No matching distribution
Target: Python 3.14.10 on win-amd64 (detected from the uv output)

tensorflow==2.15.0 has no wheel for this Python version or platform; its wheels are for Python 3.9,
3.10 and 3.11.
Only pre-releases of tensorflow support Python 3.14 on win-amd64 so far (newest: 2.22.0rc1); add
--pre to consider them.
To keep tensorflow 2.15.0, use Python 3.9, 3.10 or 3.11.
```

Exit code: `1`

## check: a requirements.txt with a conflict, and the fixed file

`requirements.txt` contains `pandas==2.2.0`, `numpy==1.21.0` and `requests>=2.31`; `requirements-fixed.txt` uses option 1 (`numpy>=1.22.4,<2`). Both run `pip install --dry-run`, which installs nothing.

```text
$ pip-conflict check requirements.txt
Dependency conflict (pip ResolutionImpossible)
Checked: requirements.txt with Python 3.10.22 (pip --dry-run, nothing installed)
Target: Python 3.10.22 on win-amd64 (interpreter used for the check)

You pinned numpy==1.21.0, but pandas 2.2.0 needs numpy>=1.22.4,<2 (for python_version < "3.11").
numpy 1.21.0 is too old for pandas 2.2.0.
numpy 1.21.0 has no wheel for Python 3.10 on win-amd64, so pip has to build it from source.

Versions that work (checked on PyPI):
  Option 1: relax your pin `numpy==1.21.0` -> `numpy>=1.22.4,<2` (newest that fits: 1.26.4)
  Option 2: keep numpy 1.21.0 and use `pandas<=2.0.3`
            note: no wheel for Python 3.10 on win-amd64: numpy 1.21.0 (pip would build from source)
  Option 3: change `pandas==2.2.0` -> `pandas==2.3.3` and `numpy==1.21.0` -> `numpy>=1.22.4` (newest
            that fits: pandas 2.3.3, numpy 2.2.6)

Check option 1 without installing anything:
  pip install --dry-run "pandas==2.2.0" "numpy>=1.22.4,<2" "requests>=2.31"

pip also listed numpy under "no matching distributions available for your environment". Recent pip
versions print that line for every package in a conflict, so on its own it does not mean a package
is missing.
```

Exit code: `0`

```text
$ pip-conflict check requirements-fixed.txt
No dependency conflict found
Checked: requirements-fixed.txt with Python 3.10.22 (pip --dry-run, nothing installed)

No conflict: pip can resolve everything in requirements-fixed.txt for Python 3.10.22 (it would
install 11 packages). Nothing was installed.
```

Exit code: `0`

## check: pyproject.toml

`svc/pyproject.toml` lists `boto3==1.34.0` and `aiobotocore==2.5.0` in `[project].dependencies`.

```text
$ pip-conflict check svc/pyproject.toml
Dependency conflict (pip ResolutionImpossible)
Checked: svc\pyproject.toml with Python 3.14.10 (pip --dry-run, nothing installed)
Target: Python 3.14.10 on win-amd64 (interpreter used for the check)

boto3 1.34.0 needs botocore>=1.34.0,<1.35.0, but aiobotocore 2.5.0 needs botocore>=1.29.76,<1.29.77.
No version of botocore matches both >=1.34.0,<1.35.0 and >=1.29.76,<1.29.77.

Versions that work (checked on PyPI):
  Option 1: upgrade your pin `aiobotocore==2.5.0` -> `aiobotocore==2.13.3`
  Option 2: keep aiobotocore 2.5.0 and use `boto3<=1.26.76`
  Option 3: change `boto3==1.34.0` -> `boto3==1.43.117` and `aiobotocore==2.5.0` ->
            `aiobotocore==3.10.0` (newest that fits: boto3 1.43.117, aiobotocore 3.10.0)

Check option 1 without installing anything:
  pip install --dry-run "boto3==1.34.0" "aiobotocore==2.13.3"

pip also listed botocore under "no matching distributions available for your environment". Recent
pip versions print that line for every package in a conflict, so on its own it does not mean a
package is missing.
```

Exit code: `0`

## pip check: a conflict between installed packages

A throwaway environment with `requests==2.31.0` installed, after `pip install urllib3==1.20`.

```text
$ pip check | pip-conflict explain
Dependency conflict between installed packages (pip)
Target: Python 3.14.10 on win-amd64 (current interpreter)

You have urllib3 1.20 installed, but requests 2.31.0 needs urllib3>=1.21.1,<3.
urllib3 1.20 is too old for requests 2.31.0.

Versions that work (checked on PyPI):
  Option 1: use `urllib3>=1.21.1,<3` instead of urllib3 1.20 (newest that fits: 2.8.0)
  Option 2: use `requests<=2.15.1` instead of requests 2.31.0
  Option 3: change `urllib3==1.20` -> `urllib3>=1.26,<3` and `requests==2.31.0` ->
            `requests==2.34.2` (newest that fits: urllib3 2.8.0, requests 2.34.2)

Check option 1 without installing anything:
  pip install --dry-run "urllib3>=1.21.1,<3" "requests==2.31.0"
```

Exit code: `0`

## JSON output

`error.txt` holds the pip output of the requests/urllib3 case above.

```text
$ pip-conflict explain error.txt --json
{
  "parsed": {
    "tool": "pip",
    "kind": "conflict",
    "requested": [
      "requests==2.31.0",
      "urllib3==1.20"
    ],
    "causes": [
      {
        "requirement": "urllib3==1.20",
        "parent": null,
        "parent_version": null,
        "parent_spec": null,
        "constraint": false,
        "installed": false
      },
      {
        "requirement": "urllib3<3,>=1.21.1",
        "parent": "requests",
        "parent_version": "2.31.0",
        "parent_spec": null,
        "constraint": false,
        "installed": false
      }
    ],
    "python_mismatches": [],
    "unavailable": [],
    "no_candidates": [
      "urllib3"
    ],
    "yanked": [],
    "python_version": "3.14",
    "platform_tag": "win_amd64",
    "error_lines": [
      "ERROR: Cannot install requests==2.31.0 and urllib3==1.20 because these package versions have conflicting dependencies.",
      "ERROR: ResolutionImpossible: for help visit https://pip.pypa.io/en/latest/topics/dependency-resolution/#dealing-with-dependency-conflicts"
    ]
  },
  "explanation": [
    "You pinned urllib3==1.20, but requests 2.31.0 needs urllib3>=1.21.1,<3.",
    "urllib3 1.20 is too old for requests 2.31.0."
  ],
  "target": {
    "python": "3.14",
    "python_full_version": "3.14.10",
    "platform": "win-amd64",
    "source": "detected from the pip output"
  },
  "fixes": [
    {
      "summary": "relax your pin `urllib3==1.20` -> `urllib3>=1.21.1,<3` (newest that fits: 2.8.0)",
      "changes": [
        {
          "name": "urllib3",
          "old": "urllib3==1.20",
          "new": "urllib3>=1.21.1,<3",
          "version": "2.8.0",
          "constraint": false
        }
      ],
      "pins": {
        "requests": "2.31.0",
        "urllib3": "2.8.0"
      },
      "requirements": [
        "urllib3>=1.21.1,<3",
        "requests==2.31.0"
      ],
      "notes": []
    },
    {
      "summary": "keep urllib3 1.20 and use `requests<=2.15.1`",
      "changes": [
        {
          "name": "requests",
          "old": "requests==2.31.0",
          "new": "requests<=2.15.1",
          "version": "2.15.1",
          "constraint": false
        }
      ],
      "pins": {
        "requests": "2.15.1",
        "urllib3": "1.20"
      },
      "requirements": [
        "urllib3==1.20",
        "requests<=2.15.1"
      ],
      "notes": []
    },
    {
      "summary": "change `urllib3==1.20` -> `urllib3>=1.26,<3` and `requests==2.31.0` -> `requests==2.34.2` (newest that fits: urllib3 2.8.0, requests 2.34.2)",
      "changes": [
        {
          "name": "urllib3",
          "old": "urllib3==1.20",
          "new": "urllib3>=1.26,<3",
          "version": "2.8.0",
          "constraint": false
        },
        {
          "name": "requests",
          "old": "requests==2.31.0",
          "new": "requests==2.34.2",
          "version": "2.34.2",
          "constraint": false
        }
      ],
      "pins": {
        "requests": "2.34.2",
        "urllib3": "2.8.0"
      },
      "requirements": [
        "urllib3>=1.26,<3",
        "requests==2.34.2"
      ],
      "notes": []
    }
  ],
  "notes": [
    "pip also listed urllib3 under \"no matching distributions available for your environment\". Recent pip versions print that line for every package in a conflict, so on its own it does not mean a package is missing."
  ],
  "search": {
    "reproduced": true,
    "complete": true,
    "attempts": 4,
    "requests": 0,
    "cache_hits": 37
  },
  "check": null,
  "error": null,
  "exit_code": 0
}
```

Exit code: `0`

## Were the suggestions installable?

Each suggestion above was checked with `pip install --dry-run --ignore-installed` in the same environment. The `Would install` line is pip's own output:

| Python | Suggested requirements | pip --dry-run result |
| --- | --- | --- |
| 3.10.22 | `numpy>=1.22.4,<2` `pandas==2.2.0` | Would install numpy-1.26.4 pandas-2.2.0 python-dateutil-3.0.0 pytz-2026.6 six-1.17.0 tzdata-2026.6 |
| 3.10.22 | `pandas<=2.0.3` `numpy==1.21.0` | Would install numpy-1.21.0 pandas-2.0.3 python-dateutil-3.0.0 pytz-2026.6 six-1.17.0 tzdata-2026.6 |
| 3.10.22 | `pandas==2.3.3` `numpy>=1.22.4` | Would install numpy-2.2.6 pandas-2.3.3 python-dateutil-3.0.0 pytz-2026.6 six-1.17.0 tzdata-2026.6 |
| 3.10.22 | `numpy<=2.2.6` | Would install numpy-2.2.6 |
| 3.14.10 | `urllib3>=1.21.1,<3` `requests==2.31.0` | Would install certifi-2026.11.20 charset-normalizer-3.5.3 idna-3.20 requests-2.31.0 urllib3-2.8.0 |
| 3.14.10 | `urllib3==1.20` `requests<=2.15.1` | Would install requests-2.15.1 urllib3-1.20 |
| 3.14.10 | `-r requirements.txt -c constraints.txt` with the constraint changed to `urllib3>=1.21.1,<3` | Would install certifi-2026.11.20 charset-normalizer-3.5.3 idna-3.20 requests-2.31.0 urllib3-2.8.0 |
| 3.14.10 | `boto3==1.34.0` `aiobotocore==2.13.3` | Would install aiobotocore-2.13.3 ... boto3-1.34.0 botocore-1.34.162 ... |
| 3.14.10 | `boto3<=1.26.76` `aiobotocore==2.5.0` | Would install aiobotocore-2.5.0 ... boto3-1.26.76 botocore-1.29.76 ... |
| 3.14.10 | `boto3==1.43.117` `aiobotocore==3.10.0` | Would install aiobotocore-3.10.0 ... boto3-1.43.117 botocore-1.43.117 ... |
| 3.14.10 | `requests==2.34.2` | Would install certifi-2026.11.20 charset-normalizer-3.5.3 idna-3.20 requests-2.34.2 urllib3-2.8.0 |
| 3.14.10 | `tensorflow==2.22.0rc1` | Would install ... tensorflow-2.22.0rc1 ... (resolves; it is a pre-release) |

A dry run only proves that the versions resolve. Option 2 of the pandas case keeps numpy 1.21.0, which has no wheel for Python 3.10, so a real install would compile numpy from source. pip-conflict prints that as a note under the option. Similarly, `requests<=2.15.1` resolves on Python 3.14, but a requests release from 2017 may not work on a modern Python; that is why it ranks below the option that keeps your requests pin.

## Why not --use-deprecated=legacy-resolver?

The same pandas/numpy pins with pip's old resolver, Python 3.10.22, pip 26.3 (download lines omitted):

```text
$ pip install --dry-run --use-deprecated=legacy-resolver pandas==2.2.0 numpy==1.21.0
Collecting pandas==2.2.0
Collecting numpy==1.21.0
Collecting python-dateutil>=2.8.2 (from pandas==2.2.0)
Collecting pytz>=2020.1 (from pandas==2.2.0)
Collecting tzdata>=2022.7 (from pandas==2.2.0)
Collecting six>=1.6 (from python-dateutil>=2.8.2->pandas==2.2.0)
Would install numpy-1.21.0 pandas-2.2.0 python-dateutil-3.0.0 pytz-2026.6 six-1.17.0 tzdata-2026.6
```

No error and no warning, although pandas 2.2.0 requires `numpy>=1.22.4,<2` on this Python.

## Windows PowerShell

In Windows PowerShell 5.1, `pip ... 2>&1 | pip-conflict explain` passes pip's stderr as error records wrapped at the console width. pip-conflict re-joins those lines. The same requests/urllib3 conflict, run from PowerShell 5.1, gives the same explanation and options as above. The piped text is kept as the test fixture `tests/fixtures/pip_powershell.txt`.
