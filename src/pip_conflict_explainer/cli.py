"""Command line interface: ``pip-conflict explain`` and ``pip-conflict check``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .checker import check
from .core import explain
from .environment import PLATFORMS
from .models import UsageError
from .pypi import DEFAULT_URL
from .render import render_text


def build_parser() -> argparse.ArgumentParser:
    """The argument parser for ``pip-conflict``."""
    parser = argparse.ArgumentParser(
        prog="pip-conflict",
        description="Explain pip/uv dependency conflicts (ResolutionImpossible) and find versions that work.",
        epilog="Exit codes: 0 = no conflict or a fix was found, 1 = conflict without an automatic fix "
        "(any conflict with --strict), 2 = error.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="print a JSON report instead of text")
    common.add_argument("--offline", action="store_true", help="explain only; do not contact PyPI")
    common.add_argument("--pre", action="store_true", help="also consider pre-releases")
    common.add_argument("--strict", action="store_true", help="exit 1 on any conflict, even when a fix was found (CI)")
    common.add_argument("--max-options", type=int, default=3, metavar="N", help="fixes to show (default: 3)")
    common.add_argument("--max-requests", type=int, default=150, metavar="N", help="PyPI request limit (default: 150)")
    common.add_argument("--timeout", type=float, default=30.0, metavar="SEC", help="PyPI search time limit (default: 30)")
    common.add_argument("--cache-dir", metavar="DIR", help="cache folder (default: your user cache folder)")
    common.add_argument("--no-cache", action="store_true", help="do not read or write the PyPI cache")
    common.add_argument("--pypi-url", default=DEFAULT_URL, metavar="URL", help=f"PyPI JSON API base (default: {DEFAULT_URL})")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")

    explain_cmd = commands.add_parser(
        "explain",
        parents=[common],
        help="explain pip/uv output from a file or stdin",
        description="Explain a pip or uv dependency error, e.g.  pip install ... 2>&1 | pip-conflict explain",
    )
    explain_cmd.add_argument("file", nargs="?", default="-", help="file with the pip/uv output (default: stdin)")
    explain_cmd.add_argument("--python", metavar="X.Y", help="target Python (default: detected, else this interpreter)")
    explain_cmd.add_argument("--platform", metavar="NAME", help=f"target platform: {', '.join(PLATFORMS)} (default: this machine)")

    check_cmd = commands.add_parser(
        "check",
        parents=[common],
        help="dry-run pip on requirements.txt or pyproject.toml and explain any conflict",
        description="Run pip install --dry-run (installs nothing) and explain a conflict if there is one.",
    )
    check_cmd.add_argument("requirements", help="requirements.txt or pyproject.toml")
    check_cmd.add_argument("-c", "--constraint", action="append", default=[], metavar="FILE", help="constraints file")
    check_cmd.add_argument("--python", metavar="X.Y|PATH", help="interpreter to run pip with (default: this one)")
    check_cmd.add_argument("--pip-timeout", type=float, default=600.0, metavar="SEC", help="pip time limit (default: 600)")
    return parser


def decode(data: bytes) -> str:
    """Decode pip output saved by any shell (UTF-8, UTF-16 from PowerShell, cp1252)."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    head = data[:400]
    if head and head.count(b"\x00") > len(head) // 4:
        return data.decode("utf-16-le", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def read_input(source: str) -> str:
    """Read the pip/uv output from a file or from stdin (``-``)."""
    if source == "-":
        if sys.stdin is None or sys.stdin.isatty():
            raise UsageError("nothing to explain: pipe pip's output in (pip install ... 2>&1 | pip-conflict explain) or pass a file")
        return decode(sys.stdin.buffer.read())
    try:
        return decode(Path(source).read_bytes())
    except OSError as exc:
        raise UsageError(f"cannot read {source}: {exc.strerror or exc}") from exc


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of the ``pip-conflict`` command; returns the exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    options = {
        "offline": args.offline,
        "pre": args.pre,
        "max_options": args.max_options,
        "max_requests": args.max_requests,
        "timeout": args.timeout,
        "cache_dir": args.cache_dir,
        "use_cache": not args.no_cache,
        "pypi_url": args.pypi_url,
    }
    try:
        if args.command == "explain":
            report = explain(read_input(args.file), python=args.python, platform=args.platform, **options)
        else:
            report = check(
                args.requirements, python=args.python, constraints=args.constraint, pip_timeout=args.pip_timeout, **options
            )
    except (UsageError, ValueError) as exc:
        if args.json:
            print(json.dumps({"error": str(exc), "exit_code": 2}, indent=2))
        else:
            print(f"pip-conflict: error: {exc}", file=sys.stderr)
        return 2
    code = report.exit_code
    if args.strict and code == 0 and report.parsed.kind != "none":
        code = 1
    if args.json:
        print(json.dumps({**report.to_dict(), "exit_code": code}, indent=2))
    else:
        sys.stdout.write(render_text(report))
    return code
