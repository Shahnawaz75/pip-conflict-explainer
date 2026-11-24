# Changelog

All notable changes to this project are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-24

### Added

- `pip-conflict explain`: reads pip or uv output from a file or stdin and explains it in plain English.
  - pip: `Cannot install ... because these package versions have conflicting dependencies` with the `The conflict is caused by:` lines (including `(constraint)`), `Additionally, some packages in these conflicts have no matching distributions available for your environment`, `requires a different Python`, `Ignored the following versions that require a different python version`, `Could not find a version that satisfies the requirement` / `No matching distribution found`, and yanked versions.
  - Conflicts between installed packages, from `pip install` (`... but you have ... which is incompatible`) and from `pip check`.
  - uv: `No solution found when resolving dependencies` derivations, in plain and coloured output.
  - Windows specifics: UTF-16 logs saved by PowerShell and stderr lines wrapped by Windows PowerShell 5.1.
- Fix search: read-only PyPI JSON API lookups with a disk cache (24 h), offline mode and a request/time budget. A bounded backtracking search over the conflicting packages takes into account environment markers, extras, `Requires-Python`, wheel tags, yanked releases and pre-releases. Fixes are ranked by fewest changes and newest versions, and the tool says when the Python version is the real blocker.
- `pip-conflict check` for `requirements.txt` (with `-r` and `-c` includes) and `pyproject.toml`, using `pip install --dry-run --ignore-installed --report`.
- `--json`, `--strict`, `--python`, `--platform` and `--pre`; exit codes 0/1/2.
- Python API: `explain()`, `check()`, `parse_error()`, `render_text()`.

[0.1.0]: https://github.com/Shahnawaz75/pip-conflict-explainer/releases/tag/v0.1.0
