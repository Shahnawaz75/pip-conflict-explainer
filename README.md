# pip-conflict-explainer: understand pip dependency conflicts (ResolutionImpossible) and get versions that work

[![CI](https://github.com/Shahnawaz75/pip-conflict-explainer/actions/workflows/ci.yml/badge.svg)](https://github.com/Shahnawaz75/pip-conflict-explainer/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

`pip-conflict` reads pip's `ResolutionImpossible` error ("Cannot install ... because these package versions have conflicting dependencies") or uv's "No solution found" message, explains the dependency conflict in plain English, and checks PyPI for versions that actually work with your Python, so you know exactly what to change in your requirements.txt.

## Before and after

What pip 26.3 printed on Python 3.10:

```text
$ pip install --dry-run pandas==2.2.0 numpy==1.21.0
...
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

What pip-conflict printed for the same run:

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

All three options were then confirmed with `pip install --dry-run` on the same Python 3.10. Pip would install numpy 1.26.4, pandas 2.0.3 and numpy 2.2.6 + pandas 2.3.3 respectively (see [docs/example-output.md](docs/example-output.md)).

## Why

- pip tells you *that* requirements clash, not *which one to change* or *which versions would work*.
- uv's explanation ("Because pandas==2.2.0 depends on ... we can conclude that ...") is precise, but you still have to work out the fix yourself.
- Finding a working combination by hand means reading `Requires-Dist`, `Requires-Python` and the wheel list of many releases on PyPI.
- `pipdeptree` shows what is installed; it does not solve a conflict.

pip-conflict parses the error, looks up only the packages in the conflict on PyPI (read-only, cached), and runs a small, bounded search for versions that fit together on your Python version and platform.

## Install

```bash
pip install git+https://github.com/Shahnawaz75/pip-conflict-explainer
```

Or as an isolated tool: `pipx install git+https://github.com/Shahnawaz75/pip-conflict-explainer`. A PyPI release is coming soon.

Requires Python 3.10 or newer. The only dependency is [`packaging`](https://pypi.org/project/packaging/); HTTP uses the standard library.

## Quick start

```bash
# Explain an error as it happens (2>&1 matters: pip prints parts of the message on stderr)
pip install -r requirements.txt 2>&1 | pip-conflict explain

# Or save the output and explain it later
pip install -r requirements.txt > error.txt 2>&1
pip-conflict explain error.txt

# Check a requirements file (or pyproject.toml) before installing anything
pip-conflict check requirements.txt
```

The same `2>&1 |` works in PowerShell and cmd. Files saved with `>` in Windows PowerShell are UTF-16; pip-conflict reads them anyway.

Exit codes: `0` = no conflict, or a conflict for which a fix was found; `1` = conflict without an automatic fix (or any conflict with `--strict`); `2` = error (unreadable input, not a dependency error, pip could not run).

## Explain a pip error

`pip-conflict explain [FILE]` reads pip output from a file or stdin. It understands:

- `Cannot install A and B because these package versions have conflicting dependencies` and the `The conflict is caused by:` lines: `The user requested X`, `A 1.2 depends on X>=2`, `The user requested (constraint) X<2`;
- `Additionally, some packages in these conflicts have no matching distributions available for your environment`;
- `Package 'x' requires a different Python: 3.10.22 not in '>=3.11'` and `Ignored the following versions that require a different python version: ...`;
- `Could not find a version that satisfies the requirement X (from versions: ...)` and `No matching distribution found for X==9.9`;
- `requests 2.31.0 requires urllib3<3,>=1.21.1, but you have urllib3 1.20 which is incompatible.` (after `pip install`) and the same conflict in `pip check` output.

A constraints file that blocks a dependency (real run, Python 3.14):

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
...
```

The target Python version and platform are taken from the log when possible (wheel names such as `cp310-cp310-win_amd64`, `requires a different Python: X`, uv's `Using Python X`); otherwise the interpreter running pip-conflict is used. Override them with `--python 3.12` and `--platform windows|linux|linux-aarch64|macos|macos-x86_64`.

## Find versions that work

Unless you pass `--offline`, pip-conflict fetches the packages named in the conflict from the PyPI JSON API (read-only). It then searches for versions that satisfy everything, newest first. It tries relaxing one of your pins, then two, then three, and ranks the results by fewest changes, then fewest source-only builds, then newest versions. Environment markers (`; python_version < "3.11"`), extras, `Requires-Python`, wheel tags for your platform, yanked releases and pre-releases are all taken into account.

A transitive conflict, where neither pin is wrong on its own (real run, Python 3.14):

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
...
```

When the Python version is the real blocker, it says so (real run, Python 3.10):

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

And when a release has no wheel for your Python at all (real run, Python 3.14):

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

Search options: `--pre` (consider pre-releases), `--max-options N` (default 3), `--max-requests N` (default 150), `--timeout SECONDS` (default 30, for the whole PyPI search), `--offline` (explain only), `--cache-dir DIR`, `--no-cache`. PyPI responses are cached for 24 hours in your user cache folder (`%LOCALAPPDATA%\pip-conflict-explainer\Cache`, `~/Library/Caches/pip-conflict-explainer` or `~/.cache/pip-conflict-explainer`; set `PIP_CONFLICT_CACHE_DIR` to change it). If PyPI cannot be reached, you still get the explanation.

## Check requirements.txt before installing

`pip-conflict check requirements.txt` runs

```text
python -m pip install --dry-run --ignore-installed --report <tmp>/report.json -r requirements.txt
```

with the chosen interpreter. `--dry-run` resolves the requirements and downloads package metadata (pip may even build a source distribution to read its metadata). It installs nothing and does not change any environment. `--ignore-installed` makes pip resolve from scratch instead of from what is already installed. If pip reports a conflict, it is explained and fixes are searched exactly as with `explain`, using your file as the list of pins.

```text
$ pip-conflict check requirements.txt
Dependency conflict (pip ResolutionImpossible)
Checked: requirements.txt with Python 3.10.22 (pip --dry-run, nothing installed)
Target: Python 3.10.22 on win-amd64 (interpreter used for the check)

You pinned numpy==1.21.0, but pandas 2.2.0 needs numpy>=1.22.4,<2 (for python_version < "3.11").
numpy 1.21.0 is too old for pandas 2.2.0.
...
Check option 1 without installing anything:
  pip install --dry-run "pandas==2.2.0" "numpy>=1.22.4,<2" "requests>=2.31"
```

```text
$ pip-conflict check requirements-fixed.txt
No dependency conflict found
Checked: requirements-fixed.txt with Python 3.10.22 (pip --dry-run, nothing installed)

No conflict: pip can resolve everything in requirements-fixed.txt for Python 3.10.22 (it would
install 11 packages). Nothing was installed.
```

It also accepts `pyproject.toml` (reads `[project].dependencies`), `-c constraints.txt`, and `--python 3.12` or the path to a Python executable or virtual environment folder. The chosen interpreter needs pip 22.2 or newer.

## Works with uv too

pip-conflict reads uv's "No solution found when resolving dependencies" report, in colour or plain text (real run, uv 0.13.9):

```text
$ uv pip compile requirements.txt --python-version 3.10
error: No solution found when resolving dependencies
  cause: Because pandas==2.2.0 depends on numpy{python_full_version < '3.11'}>=1.22.4,<2 and you require pandas==2.2.0, we can conclude that you require numpy>=1.22.4,<2.
         And because you require numpy==1.21.0, we can conclude that your requirements are unsatisfiable.

$ uv pip compile requirements.txt --python-version 3.10 2>&1 | pip-conflict explain --python 3.10
Dependency conflict (uv: no solution found)
Target: Python 3.10.22 on win-amd64 (--python)

You pinned numpy==1.21.0, but pandas 2.2.0 needs numpy>=1.22.4,<2 (for python_full_version <
"3.11").
numpy 1.21.0 is too old for pandas 2.2.0.
...
  Option 1: relax your pin `numpy==1.21.0` -> `numpy>=1.22.4,<2` (newest that fits: 1.26.4)
  Option 2: keep numpy 1.21.0 and use `pandas<=2.0.3`
...
```

It recognises `X depends on Y`, `you require X` (also `you require A and B`), constraints, `there is no version of X`, `X was not found in the package registry`, `only X is available`, `has no wheels with a matching Python ABI tag` (plus uv's hint listing the tags that exist), and `the requested/current Python version (...) does not satisfy Python>=...`. uv's report does not always say which Python it resolved for, so pass `--python` when it matters.

## Use in CI

```yaml
- name: Check for dependency conflicts
  run: |
    pip install git+https://github.com/Shahnawaz75/pip-conflict-explainer
    pip-conflict check requirements.txt --strict
```

`--strict` makes the step fail (exit 1) on any conflict, even when a fix was found, and the log shows the explanation and the change to make. Add `--json` for machine-readable output (the report also contains the exit code). The check needs network access: pip downloads metadata, and the fix search uses the PyPI JSON API.

## Python API

```python
from pip_conflict_explainer import check, explain, render_text

report = explain(open("error.txt", encoding="utf-8").read(), python="3.10")
print(report.explanation)               # plain-English sentences
for fix in report.fixes:                # ranked, best first
    print(fix.summary, fix.requirements, fix.pins)

report = check("requirements.txt")      # runs pip install --dry-run
print(report.exit_code)                 # 0, 1 or 2 as on the command line
print(render_text(report))              # the CLI text
data = report.to_dict()                 # the --json document
```

`explain()` and `check()` take the same options as the CLI (`python`, `platform` for `explain`, `offline`, `pre`, `max_options`, `max_requests`, `timeout`, `cache_dir`, `use_cache`). Use `parse_error(text)` if you only want the structured parse.

## How it works

1. **Parse.** Regular expressions read pip's resolver messages and the facts in uv's "Because ..., we can conclude that ..." sentences. The result is a list of who requires what.
2. **Pick the target.** The Python version and platform come from the log, or from the running interpreter. Markers are evaluated with `packaging.markers` for that target, and wheel compatibility is checked with `packaging.tags`.
3. **Limit the scope.** Only packages named in the error are expanded. Their other dependencies are assumed to resolve.
4. **Look up.** It fetches `https://pypi.org/pypi/<name>/json` (versions, files, `Requires-Python`, yanked) and `https://pypi.org/pypi/<name>/<version>/json` (`Requires-Dist`), trims them and caches them on disk. Requests are capped (150 and 30 seconds by default) and run a few at a time in parallel.
5. **Search.** A small backtracking search tries the newest versions first, and releases with a matching wheel before source-only ones. It skips yanked releases (unless pinned with `==`) and pre-releases (unless `--pre` or the specifier names one). For long version lists, such as boto3 with over two thousand releases, it probes and bisects instead of reading every release.
6. **Suggest.** It relaxes one, two, then three of your pins, keeps the combinations that work, and writes each as a requirement change you can paste, plus a `pip install --dry-run` command to confirm it.

## Limitations

- It is a helper, not a full resolver. Only the packages in the conflict are checked, and their other dependencies are assumed to work out. Always confirm a fix with the printed `pip install --dry-run` command.
- Fixes need network access to PyPI; `--offline` explains only. Private indexes are not supported: it uses the PyPI JSON API (`--pypi-url` can point at a compatible mirror).
- It trusts the dependency metadata PyPI shows for each release. Some old releases have none recorded and are treated as having no dependencies.
- Markers it cannot evaluate count as true. `--platform` knows five targets: windows (win_amd64), linux (manylinux x86_64), linux-aarch64, macos (arm64) and macos-x86_64. musllinux, 32-bit Windows, PyPy and free-threaded builds are not modelled.
- Source-only releases are allowed but flagged ("pip would build from source"); whether such a build succeeds cannot be predicted. A build failure such as `Failed to build 'numpy'` is recognised as "not a dependency conflict", but not solved.
- The search is bounded and can stop early on very large problems (raise `--max-requests` and `--timeout`). It explains the conflict pip reports, which is the last set of causes after pip's own backtracking.
- Detecting the Python version from a log is a best guess; pass `--python` when the log came from another machine.
- Parsing was tested against real output of pip 26.3 and uv 0.13.9. Other versions print the same core messages, but unusual variants may only be partly parsed.
- `check` runs pip, so it takes as long as `pip install --dry-run` and needs pip in the chosen interpreter.

## FAQ

### How do I fix ResolutionImpossible in pip?

`ResolutionImpossible` means pip could not find one version of every package that satisfies all requirements at once. The lines under "The conflict is caused by:" are requirements on the same package whose version ranges do not overlap. To fix it, change one side. Either loosen your own pin (`numpy==1.21.0` -> `numpy>=1.22.4,<2`), or choose a version of the other package that accepts your pin (`pandas<=2.0.3`). `pip-conflict explain` reads the error and finds such versions on PyPI for you; confirm the result with `pip install --dry-run`.

### What does 'The conflict is caused by' mean?

Each line is one requirement that pip could not satisfy together with the others:

- `The user requested numpy==1.21.0` comes from your command line or requirements file.
- `pandas 2.2.0 depends on numpy<2 and >=1.22.4; python_version < "3.11"` comes from the metadata of pandas 2.2.0. The part after `;` is the environment marker that made it apply. `numpy<2 and >=1.22.4` is pip's way of writing `numpy>=1.22.4,<2`.
- `The user requested (constraint) urllib3<1.21` comes from a constraints file (`-c` or `PIP_CONSTRAINT`).

### How do I find compatible versions of Python packages?

Look at each candidate release's `Requires-Dist` (for example `https://pypi.org/pypi/pandas/2.0.3/json`), compare the ranges, and test with `pip install --dry-run "a==X" "b==Y"`. pip-conflict automates this. It reads the error, fetches the metadata of the packages involved, and searches for the newest combination that fits your Python and platform. For a whole requirements file, run `pip-conflict check requirements.txt`.

### Why does pip say 'requires a different Python'?

The package's metadata has a `Requires-Python` range (for example `>=3.11`) that your interpreter does not match. For a local or direct-URL package pip prints `ERROR: Package 'demo-app' requires a different Python: 3.10.22 not in '>=3.11'`. For packages from an index, pip skips such releases, lists them under "Ignored the following versions that require a different python version: ...", and then reports `No matching distribution found`. Either run pip with a Python that matches, or use an older release that still supports your Python. pip-conflict names it, for example `numpy<=2.2.6` on Python 3.10.

### Should I use --use-deprecated=legacy-resolver?

No. The legacy resolver does not backtrack: it takes the first versions it finds and does not stop on a conflict. With the example above, `pip install --dry-run --use-deprecated=legacy-resolver pandas==2.2.0 numpy==1.21.0` on pip 26.3 reported `Would install numpy-1.21.0 pandas-2.2.0` without a single warning, although pandas 2.2.0 requires numpy>=1.22.4. That hides the conflict and can leave you with an environment that breaks at import time. Fix the requirements instead.

## Contributing

Bug reports with the complete pip or uv output are the most useful contribution: new message formats become test fixtures. See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup. More documentation lives at [shahnawaz75.github.io/pip-conflict-explainer](https://shahnawaz75.github.io/pip-conflict-explainer/), including [common pip and uv dependency errors](docs/common-errors.md) and [real example output](docs/example-output.md).

## License

MIT, see [LICENSE](LICENSE).

See also: [pyinstaller-doctor](https://github.com/Shahnawaz75/pyinstaller-doctor).

If pip-conflict saved you some time, a star on GitHub helps other people find it.
