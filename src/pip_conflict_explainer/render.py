"""Human-readable text output."""

from __future__ import annotations

import textwrap

from .models import Fix, Report

TITLES = {
    "conflict": "Dependency conflict",
    "requires-python": "Python version mismatch",
    "no-matching-distribution": "No matching distribution",
    "none": "No dependency conflict found",
    "unrecognized": "Not a dependency conflict",
}
WIDTH = 100


def _wrap(text: str, indent: str = "", subsequent: str | None = None) -> str:
    return textwrap.fill(
        text,
        width=WIDTH,
        initial_indent=indent,
        subsequent_indent=indent if subsequent is None else subsequent,
        break_long_words=False,
        break_on_hyphens=False,
    )


def _quote(requirement: str) -> str:
    return '"' + requirement.replace('"', "'") + '"'


def dry_run_command(fix: Fix) -> str:
    """``pip install --dry-run ...`` for the requirements of a fix."""
    command = "pip install --dry-run " + " ".join(_quote(r) for r in fix.requirements)
    if any(change.constraint for change in fix.changes):
        command += " -c constraints.txt   # after updating the constraint"
    return command


def render_text(report: Report) -> str:
    """Render a report the way the CLI prints it."""
    parsed = report.parsed
    title = TITLES.get(parsed.kind, parsed.kind)
    if parsed.kind == "conflict" and any(cause.installed for cause in parsed.causes):
        title += " between installed packages (pip)"
    elif parsed.kind == "conflict":
        title += " (pip ResolutionImpossible)" if parsed.tool == "pip" else " (uv: no solution found)"
    lines = [title]
    if report.check:
        lines.append(f"Checked: {report.check['file']} with Python {report.check['python']} (pip --dry-run, nothing installed)")
    target = report.target
    if target and parsed.kind not in ("none", "unrecognized"):
        python = target["python_full_version"]
        if python == f"{target['python']}.0" and target["source"] != "current interpreter":
            python = target["python"]  # only X.Y is known
        lines.append(f"Target: Python {python} on {target['platform']} ({target['source']})")
    lines.append("")
    lines += [_wrap(line) for line in report.explanation]
    if report.fixes:
        lines += ["", "Versions that work (checked on PyPI):"]
        for number, fix in enumerate(report.fixes, 1):
            lines.append(_wrap(f"Option {number}: {fix.summary}", "  ", " " * 12))
            lines += [_wrap(f"note: {note}", " " * 12, " " * 18) for note in fix.notes]
        lines += ["", "Check option 1 without installing anything:", "  " + dry_run_command(report.fixes[0])]
    if report.notes:
        lines.append("")
        lines += [_wrap(note) for note in report.notes]
    if report.error:
        lines += ["", f"Error: {report.error}"]
    return "\n".join(lines).rstrip() + "\n"
