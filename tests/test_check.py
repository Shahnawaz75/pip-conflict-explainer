"""``check``: reading requirements files and the pip dry-run (pip itself is faked)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from helpers import FakeIndex, fixture_text

from pip_conflict_explainer import UsageError, check
from pip_conflict_explainer import checker as check_module
from pip_conflict_explainer.checker import _toml_dependencies, find_interpreter, read_pyproject, read_requirements

INDEX = {
    "pandas": {"2.2.0": {"deps": ["numpy>=1.22.4,<2"]}, "2.0.3": {"deps": ["numpy>=1.21.0"]}},
    "numpy": {"1.21.0": {}, "1.26.4": {}},
}


def fake_pip(returncode: int, output: str = "", install: tuple[tuple[str, str], ...] = ()):
    """A stand-in for running pip: records the command and writes the --report file."""

    def run(command: list[str], timeout: float) -> tuple[int, str]:
        run.command = command  # type: ignore[attr-defined]
        run.requirements = Path(command[command.index("-r") + 1]).read_text(encoding="utf-8")  # type: ignore[attr-defined]
        if returncode == 0:
            report = {"install": [{"metadata": {"name": n, "version": v}} for n, v in install]}
            Path(command[command.index("--report") + 1]).write_text(json.dumps(report), encoding="utf-8")
        return returncode, output

    return run


@pytest.fixture
def py310(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check_module, "interpreter_version", lambda exe: "3.10.22")


def test_read_requirements_follows_includes(tmp_path: Path) -> None:
    (tmp_path / "base.txt").write_text("pandas==2.2.0\n", encoding="utf-8")
    (tmp_path / "constraints.txt").write_text("urllib3<1.21  # pinned by ops\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text(
        "# app\n-r base.txt\n-c constraints.txt\n--index-url https://example.invalid/simple\n"
        "requests==2.31.0 \\\n    --hash=sha256:abc\n"
        'numpy>=1.21 ; python_version < "3.12"  # comment\n-e ./local\n',
        encoding="utf-8",
    )
    requirements, constraints = read_requirements(tmp_path / "requirements.txt")
    assert requirements == ["pandas==2.2.0", "requests==2.31.0", 'numpy>=1.21 ; python_version < "3.12"']
    assert constraints == ["urllib3<1.21"]


def test_read_pyproject_dependencies(tmp_path: Path) -> None:
    text = (
        '[build-system]\nrequires = ["hatchling"]\n\n[project]\nname = "demo"\n'
        'dependencies = [\n  "requests[socks]>=2.31",  # comment ]\n  \'numpy<2; python_version < "3.12"\',\n]\n\n'
        '[project.optional-dependencies]\ndependencies = ["not-this"]\n'
    )
    (tmp_path / "pyproject.toml").write_text(text, encoding="utf-8")
    expected = ["requests[socks]>=2.31", 'numpy<2; python_version < "3.12"']
    assert read_pyproject(tmp_path / "pyproject.toml") == expected
    assert _toml_dependencies(text) == expected  # the Python 3.10 fallback reader


def test_check_without_conflict(tmp_path: Path, py310: None) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("requests==2.32.5\n", encoding="utf-8")
    runner = fake_pip(0, install=(("requests", "2.32.5"), ("idna", "3.10")))
    report = check(requirements, runner=runner, index=FakeIndex({}))
    assert report.exit_code == 0 and report.parsed.kind == "none"
    assert report.check is not None and report.check["would_install"] == ["requests==2.32.5", "idna==3.10"]
    assert report.explanation == [
        "No conflict: pip can resolve everything in requirements.txt for Python 3.10.22 "
        "(it would install 2 packages). Nothing was installed."
    ]
    assert {"--dry-run", "--ignore-installed", "--report"} <= set(runner.command)  # type: ignore[attr-defined]


def test_check_conflict_uses_the_requirements_file(tmp_path: Path, py310: None) -> None:
    requirements = tmp_path / "requirements-pn.txt"
    requirements.write_text("pandas==2.2.0\nnumpy==1.21.0\nrequests\n", encoding="utf-8")
    runner = fake_pip(1, fixture_text("pip_reqfile.txt"))
    report = check(requirements, runner=runner, index=FakeIndex(INDEX))
    assert report.target["python"] == "3.10"
    assert [fix.summary for fix in report.fixes] == [
        "relax your pin `numpy==1.21.0` -> `numpy>=1.22.4,<2` (newest that fits: 1.26.4)",
        "keep numpy 1.21.0 and use `pandas<=2.0.3`",
    ]
    assert report.fixes[0].requirements == ["pandas==2.2.0", "numpy>=1.22.4,<2"]  # "requests" is not involved
    assert report.exit_code == 0


def test_check_pyproject_and_non_conflict_failures(tmp_path: Path, py310: None) -> None:
    project = tmp_path / "pyproject.toml"
    project.write_text('[project]\nname = "x"\ndependencies = ["requests>=2", "rich"]\n', encoding="utf-8")
    runner = fake_pip(1, "ERROR: Could not install packages due to an OSError: [Errno 28] No space left on device\n")
    report = check(project, runner=runner, index=FakeIndex({}))
    assert runner.requirements == "requests>=2\nrich\n"  # type: ignore[attr-defined]
    assert report.exit_code == 2
    assert report.error is not None and "not because of a dependency conflict" in report.error


def test_interpreter_lookup(tmp_path: Path) -> None:
    assert find_interpreter(None) == sys.executable
    assert find_interpreter(sys.executable) == sys.executable
    with pytest.raises(UsageError):
        find_interpreter("3.99")
    with pytest.raises(UsageError):
        check(tmp_path / "missing.txt")
