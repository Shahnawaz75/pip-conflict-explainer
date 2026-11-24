"""The ``pip-conflict`` command: input handling, text/JSON output and exit codes."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
from helpers import FIXTURES

from pip_conflict_explainer import __version__
from pip_conflict_explainer import checker as check_module
from pip_conflict_explainer.cli import decode, main


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def test_explain_file_offline(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "explain", str(FIXTURES / "pip_pandas_numpy.txt"), "--offline")
    assert code == 1  # explained, but no automatic fix offline
    assert out.startswith("Dependency conflict (pip ResolutionImpossible)\nTarget: Python 3.10")
    assert "You pinned numpy==1.21.0, but pandas 2.2.0 needs numpy>=1.22.4,<2" in out


def test_explain_json(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "explain", str(FIXTURES / "uv_requests_urllib3.txt"), "--offline", "--json")
    data = json.loads(out)
    assert code == data["exit_code"] == 1
    assert data["parsed"]["tool"] == "uv" and data["parsed"]["kind"] == "conflict"
    assert data["explanation"][0] == "You pinned urllib3==1.20, but requests 2.31.0 needs urllib3>=1.21.1,<3."


def test_explain_from_stdin(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    data = (FIXTURES / "pip_boto3.txt").read_bytes()
    fake_stdin = io.TextIOWrapper(io.BytesIO(data))
    monkeypatch.setattr(sys, "stdin", fake_stdin)
    code, out, _ = run(capsys, "explain", "--offline")
    assert code == 1 and "aiobotocore 2.5.0 needs botocore>=1.29.76,<1.29.77" in out


def test_no_conflict_and_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ok = tmp_path / "ok.txt"
    ok.write_text("Successfully installed requests-2.32.5\n", encoding="utf-8")
    code, out, _ = run(capsys, "explain", str(ok))
    assert code == 0 and "No pip or uv dependency error was found" in out
    code, _, err = run(capsys, "explain", str(tmp_path / "missing.txt"))
    assert code == 2 and "pip-conflict: error: cannot read" in err
    code, out, _ = run(capsys, "explain", str(ok), "--python", "three", "--json")
    assert code == 2 and "error" in json.loads(out)


def test_utf16_files_from_powershell(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    text = (FIXTURES / "pip_requests_urllib3.txt").read_text(encoding="utf-8")
    saved = tmp_path / "error.txt"
    saved.write_bytes(text.encode("utf-16"))  # what "pip ... > error.txt" gives in Windows PowerShell
    code, out, _ = run(capsys, "explain", str(saved), "--offline")
    assert code == 1 and "You pinned urllib3==1.20" in out
    assert decode("café".encode("cp1252")) == "café"


def test_check_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def fake_run(command: list[str], timeout: float) -> tuple[int, str]:
        report = Path(command[command.index("--report") + 1])
        report.write_text(json.dumps({"install": [{"metadata": {"name": "rich", "version": "14.0.0"}}]}), encoding="utf-8")
        return 0, "Would install rich-14.0.0\n"

    monkeypatch.setattr(check_module, "run_command", fake_run)
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("rich\n", encoding="utf-8")
    code, out, _ = run(capsys, "check", str(requirements))
    assert code == 0 and "No conflict: pip can resolve everything in requirements.txt" in out
    assert run(capsys, "check", str(requirements), "--strict")[0] == 0  # --strict only fails real conflicts


def test_strict_fails_on_any_conflict(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from pip_conflict_explainer import core
    from pip_conflict_explainer.models import Fix

    real = core.build_report

    def with_fix(*args, **kwargs):  # pretend the PyPI search found a fix
        report = real(*args, **kwargs)
        report.fixes = [Fix("relax your pin", [], {}, [])]
        return report

    monkeypatch.setattr(core, "build_report", with_fix)
    error = str(FIXTURES / "pip_requests_urllib3.txt")
    assert run(capsys, "explain", error, "--offline")[0] == 0
    code, out, _ = run(capsys, "explain", error, "--offline", "--strict", "--json")
    assert code == 1 and json.loads(out)["exit_code"] == 1


def test_module_entry_point() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pip_conflict_explainer", "--version"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0 and result.stdout.strip() == f"pip-conflict {__version__}"
