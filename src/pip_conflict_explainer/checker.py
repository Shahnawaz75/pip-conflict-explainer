"""``pip-conflict check``: dry-run pip on a requirements file and explain failures.

pip is run as ``python -m pip install --dry-run --ignore-installed --report ...``.
``--dry-run`` downloads package metadata (and may build source packages to read
their metadata) but installs nothing and changes no environment.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from .core import build_report, make_index_factory
from .environment import TargetEnvironment
from .models import ParsedError, Report, UsageError
from .parser import parse_error
from .pypi import DEFAULT_URL
from .solver import Index

Runner = Callable[[list[str], float], "tuple[int, str]"]


def _logical_lines(text: str) -> list[str]:
    """Join ``\\`` continuations and drop comments, like pip does."""
    lines: list[str] = []
    buffer = ""
    for raw in text.splitlines():
        if raw.endswith("\\"):
            buffer += raw[:-1] + " "
            continue
        line = re.sub(r"(^|\s)#.*$", "", buffer + raw).strip()
        buffer = ""
        if line:
            lines.append(line)
    if buffer.strip():
        lines.append(buffer.strip())
    return lines


def read_requirements(path: Path, _seen: set[Path] | None = None) -> tuple[list[str], list[str]]:
    """Return ``(requirements, constraints)`` from a requirements file.

    ``-r`` and ``-c`` includes are followed; other pip options, editables and
    per-line options such as ``--hash`` are skipped.
    """
    seen = set() if _seen is None else _seen
    path = path.resolve()
    if path in seen:
        return [], []
    seen.add(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise UsageError(f"cannot read {path.name}: {exc.strerror or exc}") from exc
    requirements: list[str] = []
    constraints: list[str] = []
    for line in _logical_lines(text):
        include = re.match(r"^(-r|--requirement|-c|--constraint)(?:\s*=\s*|\s+|(?=[^\s=-]))(?P<file>.+)$", line)
        if include:
            more, more_constraints = read_requirements(path.parent / include["file"].strip(), seen)
            if include.group(1) in ("-c", "--constraint"):
                constraints += more + more_constraints
            else:
                requirements += more
                constraints += more_constraints
        elif not line.startswith("-"):
            requirements.append(re.split(r"\s+--?[A-Za-z]", line)[0].strip())
    return requirements, constraints


def _toml_dependencies(text: str) -> list[str]:
    """Tiny reader for ``[project] dependencies = [...]`` (Python 3.10 without tomli)."""
    table = None
    for match in re.finditer(r"(?m)^[ \t]*\[([^\[\]]+)\][ \t]*$|^[ \t]*dependencies[ \t]*=[ \t]*\[", text):
        if match.group(1) is not None:
            table = match.group(1).strip()
            continue
        if table != "project":
            continue
        items: list[str] = []
        i = match.end()
        while i < len(text):
            char = text[i]
            if char in "\"'":
                end = text.index(char, i + 1)
                items.append(text[i + 1 : end])
                i = end + 1
            elif char == "#":
                newline = text.find("\n", i)
                i = len(text) if newline == -1 else newline
            elif char == "]":
                break
            else:
                i += 1
        return items
    return []


def read_pyproject(path: Path) -> list[str]:
    """``[project].dependencies`` of a ``pyproject.toml``."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise UsageError(f"cannot read {path.name}: {exc.strerror or exc}") from exc
    if sys.version_info >= (3, 11):
        import tomllib
    else:  # Python 3.10: use tomli if it happens to be installed, else a minimal reader
        try:
            import tomli as tomllib  # type: ignore[import-not-found,no-redef,unused-ignore]
        except ModuleNotFoundError:
            return _toml_dependencies(text)
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise UsageError(f"{path.name} is not valid TOML: {exc}") from exc
    dependencies = data.get("project", {}).get("dependencies", [])
    if not isinstance(dependencies, list):
        raise UsageError(f"[project].dependencies in {path.name} is not a list")
    return [str(item) for item in dependencies]


def find_interpreter(spec: str | None) -> str:
    """Resolve ``--python`` (a version such as ``3.12``, a venv folder or an executable)."""
    if not spec:
        return sys.executable
    path = Path(spec)
    if path.is_dir():
        for candidate in (path / "Scripts" / "python.exe", path / "bin" / "python"):
            if candidate.is_file():
                return str(candidate)
    if path.is_file():
        return str(path)
    if re.fullmatch(r"3\.\d{1,2}", spec):
        if spec == f"{sys.version_info[0]}.{sys.version_info[1]}":
            return sys.executable
        launcher = shutil.which("py") if os.name == "nt" else None
        if launcher:
            found = subprocess.run(
                [launcher, f"-{spec}", "-c", "import sys; print(sys.executable)"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if found.returncode == 0 and found.stdout.strip():
                return found.stdout.strip()
        on_path = shutil.which(f"python{spec}")
        if on_path:
            return on_path
    raise UsageError(f"no Python interpreter found for --python {spec!r}; give a version like 3.12 or a path")


def interpreter_version(executable: str) -> str:
    """``X.Y.Z`` of an interpreter."""
    if Path(executable) == Path(sys.executable):
        return platform.python_version()
    try:
        proc = subprocess.run(
            [executable, "-c", "import platform; print(platform.python_version())"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UsageError(f"could not run {executable}: {exc}") from exc
    match = re.match(r"3\.\d+\.\d+", proc.stdout.strip())
    if proc.returncode != 0 or not match:
        raise UsageError(f"could not get the Python version of {executable}")
    return match.group(0)


def run_command(command: list[str], timeout: float) -> tuple[int, str]:
    """Run *command*, returning ``(exit code, combined stdout+stderr)``."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PIP_NO_INPUT": "1"}
    try:
        proc = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise UsageError(f"pip did not finish within {timeout:g} seconds (see --pip-timeout)") from exc
    except OSError as exc:
        raise UsageError(f"could not run {command[0]}: {exc}") from exc
    return proc.returncode, proc.stdout or ""


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def check(
    path: str | Path,
    *,
    python: str | None = None,
    constraints: Sequence[str | Path] = (),
    offline: bool = False,
    pre: bool = False,
    max_options: int = 3,
    max_requests: int = 150,
    timeout: float = 30.0,
    pip_timeout: float = 600.0,
    cache_dir: str | Path | None = None,
    use_cache: bool = True,
    pypi_url: str = DEFAULT_URL,
    index: Index | None = None,
    runner: Runner | None = None,
) -> Report:
    """Dry-run ``pip install`` for a ``requirements.txt`` or ``pyproject.toml``.

    Nothing is installed. If pip reports a dependency conflict it is explained
    and fixes are searched for, exactly like :func:`explain`.
    """
    path = Path(path)
    if not path.is_file():
        raise UsageError(f"{path} does not exist")
    is_toml = path.suffix.lower() == ".toml"
    requirements, constraint_lines = (read_pyproject(path), []) if is_toml else read_requirements(path)
    for item in constraints:
        more, more_constraints = read_requirements(Path(item))
        constraint_lines += more + more_constraints
    executable = find_interpreter(python)
    version = interpreter_version(executable)
    with tempfile.TemporaryDirectory(prefix="pip-conflict-") as tmp:
        requirements_file = path
        if is_toml:
            requirements_file = Path(tmp) / "requirements.txt"
            requirements_file.write_text("\n".join(requirements) + "\n", encoding="utf-8")
        report_file = Path(tmp) / "report.json"
        options = ["--dry-run", "--ignore-installed", "--disable-pip-version-check", "--no-input", "--no-color"]
        command = [executable, "-m", "pip", "install", *options, "--report", str(report_file), "-r", str(requirements_file)]
        for item in constraints:
            command += ["-c", str(item)]
        if pre:
            command.append("--pre")
        returncode, output = (runner or run_command)(command, pip_timeout)
        pip_report = _load_json(report_file)
    shown = f"python -m pip install --dry-run --ignore-installed --report <tmp>/report.json -r {path}"
    info: dict[str, Any] = {"file": str(path), "python": version, "returncode": returncode, "command": shown}
    env = TargetEnvironment.create(version, None, source="interpreter used for the check")
    if returncode == 0:
        installs = [f"{i['metadata']['name']}=={i['metadata']['version']}" for i in (pip_report or {}).get("install", [])]
        info["would_install"] = installs
        report = Report(parsed=ParsedError(tool="pip", kind="none"), target=env.describe(), check=info)
        report.explanation = [
            f"No conflict: pip can resolve everything in {path.name} for Python {version} "
            f"(it would install {len(installs)} packages). Nothing was installed."
        ]
        return report
    parsed = parse_error(output)
    if parsed.kind in ("none", "unrecognized"):
        tail = [line for line in output.strip().splitlines() if line.strip()][-8:]
        info["output_tail"] = tail
        message = "pip failed, but not because of a dependency conflict:\n" + "\n".join(tail)
        return Report(parsed=parsed, target=env.describe(), check=info, error=message)
    factory = (lambda: index) if index is not None else make_index_factory(
        max_requests=max_requests, timeout=timeout, cache_dir=cache_dir, use_cache=use_cache, pypi_url=pypi_url
    )
    report = build_report(
        parsed,
        env,
        index_factory=factory,
        requirements=requirements,
        constraints=constraint_lines,
        offline=offline,
        pre=pre,
        max_options=max_options,
    )
    report.check = info
    return report
