"""Plain data classes shared by the parser, the fix search and the renderers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class UsageError(Exception):
    """Bad input: a missing file, an unknown interpreter, nothing on stdin..."""


@dataclass(frozen=True)
class Cause:
    """One "who requires what" fact taken from a pip or uv error.

    ``parent`` is ``None`` when the requirement came from the user (command
    line, requirements file or, with ``constraint=True``, a constraints file)
    or, with ``installed=True``, is a version already installed (``pip check``).
    """

    requirement: str
    parent: str | None = None
    parent_version: str | None = None
    parent_spec: str | None = None
    constraint: bool = False
    installed: bool = False


@dataclass(frozen=True)
class PythonMismatch:
    """A package (version) that needs a different Python than the one used."""

    package: str | None
    requires_python: str
    version: str | None = None
    python: str | None = None


@dataclass(frozen=True)
class Unavailable:
    """A requirement for which pip or uv found nothing usable.

    ``reason`` is one of ``no-matching-distribution`` (pip), ``not-found``,
    ``no-version``, ``only-available`` or ``no-wheel`` (uv).
    """

    requirement: str
    reason: str = "no-matching-distribution"
    available: tuple[str, ...] | None = None
    wheel_tags: tuple[str, ...] = ()


@dataclass
class ParsedError:
    """Everything the parser could read from a pip or uv error message."""

    tool: str = "unknown"
    kind: str = "none"
    requested: list[str] = field(default_factory=list)
    causes: list[Cause] = field(default_factory=list)
    python_mismatches: list[PythonMismatch] = field(default_factory=list)
    unavailable: list[Unavailable] = field(default_factory=list)
    no_candidates: list[str] = field(default_factory=list)
    yanked: list[str] = field(default_factory=list)
    python_version: str | None = None
    platform_tag: str | None = None
    error_lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dictionary."""
        return asdict(self)


@dataclass
class Change:
    """One requirement the user has to change for a fix."""

    name: str
    old: str
    new: str
    version: str
    constraint: bool = False


@dataclass
class Fix:
    """A concrete set of versions that resolves the conflict."""

    summary: str
    changes: list[Change]
    pins: dict[str, str]
    requirements: list[str]
    notes: list[str] = field(default_factory=list)


@dataclass
class Report:
    """The result of :func:`explain` or :func:`check`."""

    parsed: ParsedError
    explanation: list[str] = field(default_factory=list)
    target: dict[str, str] = field(default_factory=dict)
    fixes: list[Fix] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    search: dict[str, Any] = field(default_factory=dict)
    check: dict[str, Any] | None = None
    error: str | None = None

    @property
    def exit_code(self) -> int:
        """0 = no conflict or a fix was found, 1 = no automatic fix, 2 = error."""
        if self.error or self.parsed.kind == "unrecognized":
            return 2
        if self.parsed.kind == "none":
            return 0
        return 0 if self.fixes else 1

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dictionary (used by ``--json``)."""
        data = asdict(self)
        data["exit_code"] = self.exit_code
        return data
