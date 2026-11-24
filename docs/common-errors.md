---
title: Common pip and uv dependency errors
description: The exact text of common pip and uv dependency errors (ResolutionImpossible, conflicting dependencies, requires a different Python, no matching distribution), what causes each one and how to fix it.
---

# Common pip and uv dependency errors

Every message below was copied from a real run of pip 26.3 or uv 0.13.9. For each one you'll find what it means and how to fix it. You can paste or pipe any of them into `pip-conflict explain` to get the explanation and working versions for your own case.

## ERROR: Cannot install A and B because these package versions have conflicting dependencies.

```text
ERROR: Cannot install numpy==1.21.0 and pandas==2.2.0 because these package versions have conflicting dependencies.

The conflict is caused by:
    The user requested numpy==1.21.0
    pandas 2.2.0 depends on numpy<2 and >=1.22.4; python_version < "3.11"
```

**Cause.** Two or more requirements on the same package (here `numpy`) have version ranges that do not overlap. A line starting with "The user requested" is yours, from the command line or a requirements file. A line like "pandas 2.2.0 depends on" comes from that package's metadata; the text after `;` is the environment marker that made it apply. When the headline says `-r requirements.txt (line 1)`, the clashing requirement came from that line of the file.

**Fix.** Change one side so the ranges overlap. Either loosen your pin (`numpy>=1.22.4,<2`) or pick a version of the other package that accepts it (`pandas<=2.0.3`). `pip install ... 2>&1 | pip-conflict explain` finds both kinds of fix on PyPI and checks them against your Python version.

## ERROR: ResolutionImpossible: for help visit https://pip.pypa.io/en/latest/topics/dependency-resolution/#dealing-with-dependency-conflicts

**Cause.** This is the last line of the conflict above; pip's resolver gave up because no combination of versions satisfies everything. The explanation is always in the "The conflict is caused by:" block printed before it.

**Fix.** As above. Do not switch to `--use-deprecated=legacy-resolver`: in a dry run with the same pins, pip 26.3 said `Would install numpy-1.21.0 pandas-2.2.0` without any warning, which is a broken combination.

## The user requested (constraint) urllib3<1.21

```text
ERROR: Cannot install -r req-constraint.txt (line 1) because these package versions have conflicting dependencies.

The conflict is caused by:
    requests 2.31.0 depends on urllib3<3 and >=1.21.1
    The user requested (constraint) urllib3<1.21
```

**Cause.** A constraints file (`-c constraints.txt` or the `PIP_CONSTRAINT` environment variable) limits a package to versions that a requirement cannot use. Constraints never add packages, they only narrow them, so the conflict can mention a package you never asked for.

**Fix.** Update the constraint (`urllib3>=1.21.1,<3`), or choose a version of the requiring package that fits it. pip-conflict reports this as "change your constraint `urllib3<1.21` -> `urllib3>=1.21.1,<3`".

## Additionally, some packages in these conflicts have no matching distributions available for your environment

```text
Additionally, some packages in these conflicts have no matching distributions available for your environment:
    numpy
```

**Cause.** pip 26.x prints this under the conflict list. In pip 26.3 the check behind it looks a package up without any requirement attached, so it finds nothing every time. In every conflict reproduced for these docs, the line named every package in the conflict, including ones that clearly have files for the Python in use (urllib3 1.20, a pure-Python wheel, for example).

**Fix.** Do not treat this line as the cause on its own; fix the conflict listed above it. If a package really has no files for your Python, `pip-conflict explain` says so explicitly ("has no wheel for Python 3.14 on win-amd64").

## ERROR: Could not find a version that satisfies the requirement X (from versions: none)

```text
ERROR: Could not find a version that satisfies the requirement this-package-does-not-exist-pce (from versions: none)
ERROR: No matching distribution found for this-package-does-not-exist-pce
```

**Cause.** pip found no usable release at all. Either the name is wrong, or the package has no files for your Python version and platform. Packages with only compiled wheels for older Pythons hit this on a new Python. On Python 3.14, `tensorflow==2.15.0` printed `(from versions: 2.22.0rc0, 2.22.0rc1)` because only those pre-releases had Python 3.14 wheels.

**Fix.** Check the spelling. Otherwise use a Python version the package supports, or a release that has wheels for yours. pip-conflict checks PyPI and tells you which case it is, for example "tensorflow 2.15.0 has no wheel for Python 3.14 on win-amd64 (its wheels are for Python 3.9, 3.10 and 3.11)".

## ERROR: No matching distribution found for requests==9.9

```text
ERROR: Ignored the following yanked versions: 2.32.0, 2.32.1
ERROR: Could not find a version that satisfies the requirement requests==9.9 (from versions: 0.2.0, ..., 2.34.1, 2.34.2)
ERROR: No matching distribution found for requests==9.9
```

**Cause.** The package exists, but no release matches the requirement: the version does not exist, was yanked, or is excluded by your Python version.

**Fix.** Pick one of the versions pip lists in "from versions" (they already fit your Python and platform). pip-conflict suggests the newest one: "use `requests==2.34.2` instead of `requests==9.9`".

## ERROR: Ignored the following versions that require a different python version

```text
ERROR: Ignored the following versions that require a different python version: 2.3.0 Requires-Python >=3.11; 2.3.1 Requires-Python >=3.11; ...
ERROR: Could not find a version that satisfies the requirement numpy==2.3.0 (from versions: 1.3.0, ..., 2.2.5, 2.2.6)
ERROR: No matching distribution found for numpy==2.3.0
```

**Cause.** The release you asked for declares `Requires-Python` (here `>=3.11`) and pip is running on an older Python (3.10 here), so pip skipped it.

**Fix.** Run pip with a Python that matches, or use the newest release that supports your Python (the last one in "from versions"). pip-conflict prints "numpy 2.3.0 needs Python >=3.11; you have 3.10" and suggests `numpy<=2.2.6`.

## ERROR: Package 'demo-app' requires a different Python: 3.10.22 not in '>=3.11'

```text
Processing .\demo-app
...
ERROR: Package 'demo-app' requires a different Python: 3.10.22 not in '>=3.11'
```

**Cause.** You installed a local project (or a direct URL) whose `requires-python` excludes the running interpreter. For a local project, pip learns about the requirement only after reading its metadata, so it cannot fall back to another version.

**Fix.** Create the virtual environment with a matching Python (`py -3.11 -m venv .venv` on Windows, `python3.11 -m venv .venv` elsewhere), or lower `requires-python` in the project's `pyproject.toml` if you maintain it and it really works on the older Python.

## INFO: pip is looking at multiple versions of aiobotocore to determine which version is compatible with other requirements. This could take a while.

**Cause.** This is not an error. pip is backtracking: the newest version of that package did not fit, so it is trying older ones. With loose requirements on packages that release often (boto3, botocore and aiobotocore each have hundreds or thousands of releases) this can take a long time and may still end in `ResolutionImpossible`.

**Fix.** Give pip tighter bounds for the packages it names, for example with a lower bound or a constraints file. When the run ends in a conflict, pip-conflict suggests concrete versions, for example `aiobotocore==2.13.3` together with `boto3==1.34.0`.

## ERROR: pip's dependency resolver does not currently take into account all the packages that are installed.

```text
ERROR: pip's dependency resolver does not currently take into account all the packages that are installed. This behaviour is the source of the following dependency conflicts.
requests 2.31.0 requires urllib3<3,>=1.21.1, but you have urllib3 1.20 which is incompatible.
Successfully installed urllib3-1.20
```

**Cause.** The install succeeded, but it changed a package that something already installed depends on. pip only resolves the packages you asked for in this command, not everything in the environment.

**Fix.** Install the packages together in one command, or move the installed package back into the range it needs (`urllib3>=1.21.1,<3` here). `pip check` lists every such conflict in the environment.

## requests 2.31.0 has requirement urllib3<3,>=1.21.1, but you have urllib3 1.20.

**Cause.** This is `pip check` output: the environment already contains incompatible versions, usually after installs in separate commands or a `--no-deps` install.

**Fix.** Same as above. `pip check | pip-conflict explain` explains it and suggests versions ("use `urllib3>=1.21.1,<3` instead of urllib3 1.20").

## ERROR: Failed to build 'numpy' when calling build backend hook get_requires_for_build_wheel

```text
Collecting numpy==1.21.0
  Using cached numpy-1.21.0.zip (10.3 MB)
...
  error: backend-unavailable

  × Cannot import build backend 'setuptools.build_meta:__legacy__'.
  ╰─> ModuleNotFoundError: No module named 'distutils'
...
ERROR: Failed to build 'numpy' when calling build backend hook get_requires_for_build_wheel
```

**Cause.** This is a build failure, not a dependency conflict. numpy 1.21.0 has no wheel for Python 3.14, so pip downloaded the source archive and tried to build it. The build needs `distutils`, which was removed from Python in 3.12.

**Fix.** Use a version that has a wheel for your Python (for numpy on Python 3.14, a current 2.x release), or use an older Python that the pinned version supports. pip-conflict recognises this as a build error and says so, but it does not search for a fix.

## error: No solution found when resolving dependencies (uv)

```text
error: No solution found when resolving dependencies
  cause: Because pandas==2.2.0 depends on numpy{python_full_version < '3.11'}>=1.22.4,<2 and you require pandas==2.2.0, we can conclude that you require numpy>=1.22.4,<2.
         And because you require numpy==1.21.0, we can conclude that your requirements are unsatisfiable.
```

**Cause.** uv's version of `ResolutionImpossible`. Each "Because ..." sentence states facts and a conclusion: `X depends on Y` comes from package metadata, `you require Y` from your requirements, and `{python_full_version < '3.11'}` is the marker under which the dependency applies. A bare range in the middle of a sentence, as in `depends on urllib3>=1.21.1,<3 and urllib3<1.21`, is a constraint.

**Fix.** The same as for pip. `uv pip compile requirements.txt 2>&1 | pip-conflict explain --python 3.10` produces the same fixes as for the pip error. uv does not always say which Python it resolved for, so pass `--python`.

## Because tensorflow==2.15.0 has no wheels with a matching Python ABI tag (uv)

```text
  cause: Because tensorflow==2.15.0 has no wheels with a matching Python ABI tag (e.g., `cp314`) and you require tensorflow==2.15.0, we can conclude that your requirements are unsatisfiable.

hint: You require CPython 3.14 (`cp314`), but we only found wheels for `tensorflow` (v2.15.0) with the following Python ABI tags: `cp39`, `cp310`, `cp311`
```

**Cause.** The release exists, but only has wheels for other Python versions and no source archive.

**Fix.** Use one of the Python versions in the hint (3.9 to 3.11 here) or a release that supports yours. pip-conflict adds which releases do, for example "Only pre-releases of tensorflow support Python 3.14 on win-amd64 so far (newest: 2.22.0rc1); add --pre to consider them."

## Because there is no version of requests==9.9 (uv)

```text
  cause: Because there is no version of requests==9.9 and you require requests==9.9, we can conclude that your requirements are unsatisfiable.
  cause: Because only requests<=2.34.2 is available and you require requests>=9, we can conclude that your requirements are unsatisfiable.
  cause: Because this-package-does-not-exist-pce was not found in the package registry and you require this-package-does-not-exist-pce, we can conclude that your requirements are unsatisfiable.
```

**Cause.** These are three separate runs. In the first two the version does not exist; in the third the whole project does not exist on the index.

**Fix.** Use an existing version (uv tells you the highest one in "only ... is available"), or check the package name.

## Because the requested Python version (>=3.10) does not satisfy Python>=3.11 (uv)

```text
  cause: Because the requested Python version (>=3.10) does not satisfy Python>=3.11 and numpy==2.3.0 depends on Python>=3.11, we can conclude that numpy==2.3.0 cannot be used.
         And because you require numpy==2.3.0, we can conclude that your requirements are unsatisfiable.
```

**Cause.** With `uv pip compile --python-version 3.10` (or a project with `requires-python = ">=3.10"`), uv must find versions that work on every Python in that range, and numpy 2.3.0 needs 3.11 or newer.

**Fix.** Raise the minimum Python version (`--python-version 3.11`, or `requires-python` in `pyproject.toml`), or pin a release that supports 3.10 (`numpy<=2.2.6`).
