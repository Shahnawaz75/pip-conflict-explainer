# Contributing to pip-conflict-explainer

Thanks for helping! The most valuable contribution is a pip or uv message that pip-conflict does not understand yet. Please open an issue with the **complete** output (attach it as a file), the command you ran, your Python version and your OS.

## Development setup

```bash
git clone https://github.com/Shahnawaz75/pip-conflict-explainer
cd pip-conflict-explainer
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
python -m pip install -e . pytest
python -m pytest
```

The tests never use the network: PyPI responses come from `tests/fixtures/pypi`, and `tests/conftest.py` makes any real HTTP request fail. CI runs them on Linux, Windows and macOS with Python 3.10 to 3.14.

## Layout

| File | What it does |
| --- | --- |
| `src/pip_conflict_explainer/parser.py` | Reads pip and uv messages into a `ParsedError` |
| `src/pip_conflict_explainer/core.py` | Plain-English explanation, PyPI diagnosis, fix search and ranking |
| `src/pip_conflict_explainer/solver.py` | The bounded backtracking search |
| `src/pip_conflict_explainer/pypi.py` | Read-only PyPI JSON client with cache and budget |
| `src/pip_conflict_explainer/environment.py` | Target Python/platform: markers and wheel tags |
| `src/pip_conflict_explainer/checker.py` | `check`: requirements files and the `pip install --dry-run` call |
| `src/pip_conflict_explainer/cli.py`, `render.py` | Command line and text output |

## Adding a new error message

1. Reproduce it in a throwaway virtual environment, preferably with `pip install --dry-run`, so nothing is installed.
2. Save the full output under `tests/fixtures/` (short file name; Windows path limits apply). Replace local paths with something like `C:\work\` and remove anything private.
3. Add a test in `tests/test_parser.py` that asserts the parsed result exactly, then make it pass.
4. If the fix search needs new PyPI data, add the versions to `scripts/record_pypi_fixtures.py` and run it (it only reads from PyPI).

## Pull requests

- Keep the only runtime dependency `packaging`, and keep Python 3.10 support.
- Add or update tests; `python -m pytest` must pass.
- Use type hints and short docstrings, and keep output text short and concrete.
- Update `CHANGELOG.md` and the docs when behaviour changes. Examples in the docs must come from real runs.
