"""Turn a parsed error into a plain-English explanation and ranked fixes."""

from __future__ import annotations

import itertools
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import Specifier, SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from .environment import TargetEnvironment, current_platform_key, platform_from_wheel_tag, wheel_pythons
from .models import Cause, Change, Fix, ParsedError, Report
from .parser import exact_version, name_of, parse_error
from .pypi import DEFAULT_URL, BudgetExceeded, NetworkError, OfflineError, PyPIClient
from .solver import Index, SearchLimit, Solver, mentions_prerelease

IndexFactory = Callable[[], Index]
_ORDER = {">=": 0, ">": 0, "~=": 1, "==": 1, "===": 1, "!=": 2, "<=": 3, "<": 3}


@dataclass
class Root:
    """A requirement the user (or pip) asked for, which a fix may change."""

    requirement: Requirement
    text: str
    origin: str = "user"  # "user", "constraint" or "implicit"

    @property
    def name(self) -> str:
        return canonicalize_name(self.requirement.name)


# -- small helpers -------------------------------------------------------
def _parse(text: str) -> Requirement | None:
    try:
        return Requirement(text)
    except InvalidRequirement:
        return None


def _version(text: str | None) -> Version | None:
    try:
        return Version(text) if text else None
    except InvalidVersion:
        return None


def _join(items: Sequence[str], word: str = "and") -> str:
    items = list(items)
    if len(items) <= 2:
        return f" {word} ".join(items)
    return ", ".join(items[:-1]) + f" {word} " + items[-1]


def _sentence(text: str) -> str:
    """Capitalise "you ..."/"your ..." but never a package name."""
    return text[:1].upper() + text[1:] if text.startswith("you") else text


def pretty_spec(spec: SpecifierSet) -> str:
    """``<2,>=1.22.4`` -> ``>=1.22.4,<2`` (lower bounds first)."""
    return ",".join(str(s) for s in sorted(spec, key=lambda s: (_ORDER.get(s.operator, 1), s.version)))


def pretty_requirement(req: Requirement, spec: SpecifierSet | None = None, marker: bool = True) -> str:
    """Format a requirement with a readable specifier order."""
    extras = f"[{','.join(sorted(req.extras))}]" if req.extras else ""
    text = req.name + extras + pretty_spec(req.specifier if spec is None else spec)
    return f"{text}; {req.marker}" if marker and req.marker else text


def simplify(spec: SpecifierSet) -> SpecifierSet:
    """Keep only the tightest lower and upper bound (``>=1,>=2,<3`` -> ``>=2,<3``)."""
    items = list(spec)
    try:
        lowers = [s for s in items if s.operator in (">=", ">")]
        uppers = [s for s in items if s.operator in ("<=", "<")]
        keep: list[Specifier] = [s for s in items if s not in lowers and s not in uppers]
        if lowers:
            keep.append(max(lowers, key=lambda s: (Version(s.version), s.operator == ">")))
        if uppers:
            keep.append(min(uppers, key=lambda s: (Version(s.version), s.operator != "<")))
    except InvalidVersion:
        return spec
    return SpecifierSet(",".join(str(s) for s in keep))


def python_needed(name: str, version: str | None, spec: str, python: str) -> str:
    """The standard "X needs Python Y; you have Z." sentence."""
    who = f"{name} {version}" if version else name
    return f"{who} needs Python {spec}; you have {python}."


# -- explanation of the error text ---------------------------------------
def explain_lines(parsed: ParsedError, env: TargetEnvironment) -> list[str]:
    """Plain-English sentences for what the error says (no network needed)."""
    if parsed.kind == "conflict":
        return _conflict_lines(parsed)
    if parsed.kind == "requires-python":
        return _python_lines(parsed, env)
    if parsed.kind == "no-matching-distribution":
        return _missing_lines(parsed)
    if parsed.kind == "none":
        return ["No pip or uv dependency error was found in the input."]
    built = next((m.group(1) for line in parsed.error_lines if (m := re.search(r"Failed to build '?([\w.-]+)", line))), None)
    if built or any("subprocess-exited-with-error" in line for line in parsed.error_lines):
        what = f"building {built} from source" if built else "building a package from source"
        return [
            f"pip failed while {what}. This is a build error, not a dependency conflict; it usually means "
            "there is no wheel for your Python version, so pip tried to compile the package.",
            *parsed.error_lines[:3],
        ]
    return ["This is not a dependency conflict that pip-conflict can explain:", *parsed.error_lines[:3]]


def _user_phrase(cause: Cause) -> str:
    req = _parse(cause.requirement)
    shown = pretty_requirement(req) if req else cause.requirement
    if cause.constraint:
        return f"your constraints say {shown}"
    if cause.installed and req:
        return f"you have {req.name} {exact_version(cause.requirement)} installed"
    return f"you pinned {shown}" if exact_version(cause.requirement) else f"you asked for {shown}"


def _parent_phrases(parents: Sequence[Cause]) -> list[str]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for cause in parents:
        grouped.setdefault((cause.parent or "", cause.requirement), []).append(
            cause.parent_version or cause.parent_spec or ""
        )
    phrases = []
    for (parent, requirement), versions in grouped.items():
        req = _parse(requirement)
        need = pretty_requirement(req, marker=False) if req else requirement
        when = f" (for {req.marker})" if req and req.marker else ""
        if all(_version(v) for v in versions):
            shown = versions[:3] + ([f"{len(versions) - 3} more"] if len(versions) > 3 else [])
            who = f"{parent} {_join(shown)}"
        else:
            who = f"{parent}{versions[0]}"
        phrases.append(f"{who} {'need' if len(versions) > 1 else 'needs'} {need}{when}")
    return phrases


def _clash_sentence(name: str, users: Sequence[Cause], parents: Sequence[Cause]) -> str | None:
    pins = [exact_version(c.requirement) for c in users if exact_version(c.requirement)]
    if len(pins) == 1 and parents and (pinned := _version(pins[0])):
        old: list[str] = []
        new: list[str] = []
        for cause in parents:
            req = _parse(cause.requirement)
            if req is None or req.specifier.contains(pinned, prereleases=True):
                continue
            who = f"{cause.parent} {cause.parent_version or cause.parent_spec or ''}".strip()
            low = [s for s in req.specifier if s.operator in (">=", ">", "~=", "==") and (_version(s.version) or pinned) > pinned]
            (old if low else new).append(who)
        if old and not new:
            return f"{name} {pins[0]} is too old for {_join(sorted(set(old)))}."
        if new and not old:
            return f"{name} {pins[0]} is too new for {_join(sorted(set(new)))}."
        return None
    specs = []
    for cause in [*users, *parents]:
        req = _parse(cause.requirement)
        if req and str(req.specifier) and pretty_spec(req.specifier) not in specs:
            specs.append(pretty_spec(req.specifier))
    if len(specs) >= 2:
        return f"No version of {name} matches {'both' if len(specs) == 2 else 'all of'} {_join(specs)}."
    return None


def _conflict_lines(parsed: ParsedError) -> list[str]:
    groups: dict[str, list[Cause]] = {}
    for cause in parsed.causes:
        groups.setdefault(name_of(cause.requirement), []).append(cause)
    lines = []
    for name, causes in groups.items():
        users = [c for c in causes if c.parent is None]
        parents = [c for c in causes if c.parent]
        if not parents and len(users) < 2:
            continue
        user_bits = [_user_phrase(c) for c in users]
        parent_bits = _parent_phrases(parents)
        first, rest = (user_bits, parent_bits) if user_bits else (parent_bits[:1], parent_bits[1:])
        lines.append(_sentence(_join(first) + (", but " + _join(rest) if rest else "")) + ".")
        if clash := _clash_sentence(name, users, parents):
            lines.append(clash)
    return lines or ["pip reported a dependency conflict but did not say which requirements clash."]


def _python_lines(parsed: ParsedError, env: TargetEnvironment) -> list[str]:
    lines = []
    for item in parsed.python_mismatches:
        if item.python:  # pip's "requires a different Python" message
            lines.append(python_needed(item.package or "a package", item.version, item.requires_python, item.python))
    if lines:
        spec = parsed.python_mismatches[0].requires_python
        example = _python_example(spec)
        hint = f" (for example Python {example})" if example else ""
        lines.append(f"Run pip with a Python that matches {spec}{hint}, or lower requires-python if you maintain the package.")
        return lines
    pinned = {(name_of(u.requirement), exact_version(u.requirement)) for u in parsed.unavailable}
    for item in parsed.python_mismatches:
        key = (canonicalize_name(item.package or ""), item.version)
        if parsed.tool == "uv" or key in pinned:
            lines.append(python_needed(item.package or "a package", item.version, item.requires_python, env.python_version))
    for missing in parsed.unavailable:
        name = name_of(missing.requirement)
        finals = [v for v in missing.available or () if (ver := _version(v)) and not ver.is_prerelease]
        if finals:
            newest = max(finals, key=Version)
            lines.append(f"The newest {name} that pip could use on this Python is {newest}.")
    return lines


def _missing_lines(parsed: ParsedError) -> list[str]:
    lines = []
    for item in parsed.unavailable:
        name = name_of(item.requirement)
        if item.reason == "not-found":
            lines.append(f"{name} was not found in the package registry. Check the spelling of the name.")
        elif item.reason == "no-version":
            lines.append(f"There is no version of {name} that matches `{item.requirement}`.")
        elif item.reason == "only-available":
            asked = [c.requirement for c in parsed.causes if c.parent is None and name_of(c.requirement) == name]
            wanted = f"you asked for {_join(asked)}" if asked else "that does not match the request"
            lines.append(f"Only {item.requirement} is available, but {wanted}.")
        elif item.reason == "no-wheel":
            pythons = [f"3.{t[3:]}" for t in item.wheel_tags if t.startswith("cp3")]
            extra = f"; its wheels are for Python {_join(pythons)}" if pythons else ""
            lines.append(f"{item.requirement} has no wheel for this Python version or platform{extra}.")
        elif item.available is None:
            lines.append(f"pip found no distribution matching `{item.requirement}`.")
        elif not item.available:
            lines.append(
                f"pip found no installable version of {name} at all: either the name is misspelled, "
                f"or {name} has no files for this Python version and platform."
            )
        else:
            finals = [v for v in item.available if (ver := _version(v)) and not ver.is_prerelease]
            if finals:
                newest = max(finals, key=Version)
                lines.append(f"No {name} release matches `{item.requirement}`. The newest version pip could see is {newest}.")
            else:
                shown = ", ".join(item.available[-3:])
                lines.append(f"No {name} release matches `{item.requirement}`. pip could only see pre-releases: {shown}.")
        pinned = exact_version(item.requirement)
        if pinned and pinned in parsed.yanked:
            lines.append(f"{name} {pinned} was yanked by its maintainers.")
    return lines


def _python_example(spec: str) -> str | None:
    try:
        parsed = SpecifierSet(spec)
    except ValueError:
        return None
    for minor in range(8, 20):
        if parsed.contains(f"3.{minor}.0", prereleases=True):
            return f"3.{minor}"
    return None


# -- what to search ------------------------------------------------------
def build_roots(
    parsed: ParsedError,
    requirements: Sequence[str] | None = None,
    constraints: Sequence[str] = (),
) -> tuple[list[Root], set[str]]:
    """Return the requirements a fix may change, and the package names in scope.

    With *requirements* (the ``check`` command) the real requirements file is
    used; otherwise the roots are read from the error text.
    """
    scope: set[str] = set()
    for cause in parsed.causes:
        scope.add(name_of(cause.requirement))
        if cause.parent:
            scope.add(canonicalize_name(cause.parent.split("[")[0]))
    named = [*parsed.requested, *(u.requirement for u in parsed.unavailable)]
    named += [m.package for m in parsed.python_mismatches if m.package and m.version]
    scope.update(name_of(item) for item in named if _parse(item))
    scope.discard("python")

    roots: list[Root] = []

    def add(text: str, origin: str) -> None:
        req = _parse(text)
        if req is None or req.url or canonicalize_name(req.name) not in scope:
            return
        for root in roots:
            if root.text == text and (root.origin == "constraint") == (origin == "constraint"):
                if origin == "user":
                    root.origin = "user"  # asked for explicitly, not only seen installed
                return
        roots.append(Root(req, text, origin))

    if requirements is not None:
        for line in requirements:
            add(line, "user")
        for line in constraints:
            add(line, "constraint")
    else:
        for cause in parsed.causes:
            if cause.parent is None:
                add(cause.requirement, "constraint" if cause.constraint else "implicit" if cause.installed else "user")
        for item in parsed.requested:
            add(item, "user")
        for missing in parsed.unavailable:
            if missing.reason != "only-available":
                add(missing.requirement, "user")
    # Packages pip tried that nothing above pins: pin them to the versions seen.
    covered = {r.name for r in roots if r.origin != "constraint"}
    seen: dict[str, list[Version]] = {}
    for cause in parsed.causes:
        if cause.parent and (version := _version(cause.parent_version)):
            seen.setdefault(canonicalize_name(cause.parent.split("[")[0]), []).append(version)
    for mismatch in parsed.python_mismatches:
        if mismatch.package and mismatch.python and (version := _version(mismatch.version)):
            seen.setdefault(canonicalize_name(mismatch.package), []).append(version)
    for name, versions in seen.items():
        if name not in covered:
            low, high = min(versions), max(versions)
            add(f"{name}=={low}" if low == high else f"{name}>={low},<={high}", "implicit")
    return roots, scope


# -- PyPI diagnosis ------------------------------------------------------
def diagnose(root: Root, index: Index, env: TargetEnvironment, pre: bool = False) -> list[tuple[str, str]]:
    """Explain, from PyPI data, why a requirement has no usable release (if it has none).

    Returns ``(code, sentence)`` pairs; codes are ``missing``, ``no-match``,
    ``python``, ``no-wheel``, ``pre-only``, ``use-python`` and ``sdist``.
    """
    req = root.requirement
    releases = index.releases(req.name)
    if releases is None:
        return [("missing", f"{req.name} does not exist on PyPI. Check the spelling, or whether it comes from another index.")]
    if not releases:
        return [("missing", f"{req.name} has no files on PyPI.")]
    allow_pre = pre or mentions_prerelease(req.specifier)
    matching = [
        r
        for r in releases
        if req.specifier.contains(r.version, prereleases=True) and (allow_pre or not r.version.is_prerelease)
    ]
    newest = next((r for r in releases if not r.version.is_prerelease and not r.yanked), releases[0])
    if not matching:
        return [("no-match", f"No release of {req.name} matches `{root.text}`; the newest is {newest.version}.")]
    fits = [r for r in matching if env.python_ok(r.requires_python)]
    if not fits:
        first = matching[0]
        return [("python", python_needed(req.name, str(first.version), first.requires_python or "?", env.python_version))]
    kinds = {r.version: env.file_kind(r.files) for r in fits}
    if not any(kinds.values()):
        first = fits[0]
        pythons = wheel_pythons(first.files)
        line = f"{req.name} {first.version} has no wheel for {env.label}"
        lines = [("no-wheel", line + (f" (its wheels are for Python {_join(pythons)})." if pythons else "."))]
        usable = [r for r in releases if not r.yanked and env.python_ok(r.requires_python) and env.file_kind(r.files)]
        if usable and all(r.version.is_prerelease for r in usable) and not pre:
            lines.append((
                "pre-only",
                f"Only pre-releases of {req.name} support {env.label} so far (newest: {usable[0].version}); "
                "add --pre to consider them.",
            ))
        if pythons:
            lines.append(("use-python", f"To keep {req.name} {first.version}, use Python {_join(pythons, 'or')}."))
        return lines
    if exact_version(root.text) and all(kind == "sdist" for kind in kinds.values() if kind):
        return [("sdist", f"{req.name} {fits[0].version} has no wheel for {env.label}, so pip has to build it from source.")]
    return []


# -- fix search ----------------------------------------------------------
def _relaxed(req: Requirement) -> Requirement:
    copy = Requirement(str(req))
    copy.specifier = SpecifierSet()
    return copy


def _summary(changes: Sequence[Change], kept: Sequence[str], origins: dict[str, str]) -> str:
    if len(changes) > 1:
        parts = _join([f"`{c.old}` -> `{c.new}`" for c in changes])
        return f"change {parts} (newest that fits: {', '.join(f'{c.name} {c.version}' for c in changes)})"
    change = changes[0]
    fixed = any(op in change.new for op in ("==", "<=")) and not any(op in change.new for op in (">=", ">"))
    suffix = "" if fixed else f" (newest that fits: {change.version})"
    if change.constraint:
        return f"change your constraint `{change.old}` -> `{change.new}`{suffix}"
    old_pin = _version(exact_version(change.old))
    older = old_pin is not None and Version(change.version) < old_pin
    if origins.get(change.old) == "implicit":
        return f"use `{change.new}` instead of {change.name} {exact_version(change.old) or change.old}{suffix}"
    if older and kept:
        return f"keep {_join(kept)} and use `{change.new}`{suffix}"
    if older:
        return f"use `{change.new}` instead of `{change.old}`{suffix}"
    if old_pin is not None and fixed:
        return f"upgrade your pin `{change.old}` -> `{change.new}`"
    if old_pin is not None:
        return f"relax your pin `{change.old}` -> `{change.new}`{suffix}"
    return f"change `{change.old}` -> `{change.new}`{suffix}"


def _make_fix(
    roots: Sequence[Root],
    relaxed: set[int],
    pins: dict[str, Any],
    solver: Solver,
    index: Index,
    env: TargetEnvironment,
) -> tuple[tuple[int, int, int], Fix]:
    reqs = solver.collect(pins)
    changes: list[Change] = []
    kept: list[str] = []
    notes: list[str] = []
    for i, root in enumerate(roots):
        release = pins.get(root.name)
        if i not in relaxed:
            if root.origin == "constraint":
                kept.append(f"your constraint {root.text}")
            elif release is not None and exact_version(root.text):
                kept.append(f"{root.requirement.name} {release.version}")
            continue
        if release is None or root.requirement.specifier.contains(release.version, prereleases=True):
            continue
        imposed = SpecifierSet()
        for dep, source in reqs.get(root.name, []):
            if source is not None:
                imposed &= dep.specifier
        if str(imposed):
            spec = simplify(imposed)
        else:
            pinned = _version(exact_version(root.text))
            known = {r.version for r in index.releases(root.name) or []}
            older = pinned is not None and pinned in known and release.version < pinned
            spec = SpecifierSet(f"<={release.version}" if older else f"=={release.version}")
        new = pretty_requirement(root.requirement, spec)
        changes.append(Change(root.requirement.name, root.text, new, str(release.version), root.origin == "constraint"))
        pinned_release = next(
            (r for r in index.releases(root.name) or [] if str(r.version) == exact_version(root.text)), None
        )
        if pinned_release is not None and not env.python_ok(pinned_release.requires_python):
            notes.append(
                python_needed(root.requirement.name, str(pinned_release.version), pinned_release.requires_python or "?", env.python_version)
            )
    sdists = sorted(f"{name} {r.version}" for name, r in pins.items() if solver.kind(name, r) == "sdist")
    if sdists:
        notes.append(f"no wheel for {env.label}: {_join(sdists)} (pip would build from source)")
    origins = {r.text: r.origin for r in roots}
    changed = {c.old: c.new for c in changes}
    requirements = [changed.get(r.text, r.text) for r in roots if r.origin != "constraint"]
    fix = Fix(
        summary=_summary(changes, kept, origins) if changes else "",
        changes=changes,
        pins={name: str(r.version) for name, r in sorted(pins.items())},
        requirements=requirements,
        notes=notes,
    )
    age = 0
    for name, release in pins.items():
        finals = [r.version for r in index.releases(name) or [] if not r.version.is_prerelease]
        age += finals.index(release.version) if release.version in finals else len(finals)
    return (len(changes), len(sdists), age), fix


def search_fixes(
    roots: Sequence[Root],
    scope: set[str],
    index: Index,
    env: TargetEnvironment,
    *,
    pre: bool = False,
    max_options: int = 3,
) -> tuple[list[Fix], dict[str, Any]]:
    """Relax 1, then 2, then 3 roots at a time and keep the solutions, best first."""
    solver = Solver(index, env, scope, allow_pre=pre)
    info: dict[str, Any] = {"reproduced": True, "complete": True, "attempts": 0}

    def attempt(relaxed: set[int]) -> dict[str, Any] | None:
        info["attempts"] += 1
        reqs = [_relaxed(r.requirement) if i in relaxed else r.requirement for i, r in enumerate(roots) if r.origin != "constraint"]
        cons = [r.requirement for i, r in enumerate(roots) if r.origin == "constraint" and i not in relaxed]
        return solver.solve(reqs, cons)

    found: list[tuple[tuple[int, int, int], Fix]] = []
    try:
        baseline = attempt(set())
        if baseline is not None:
            info["reproduced"] = False
            info["baseline"] = {name: str(r.version) for name, r in sorted(baseline.items())}
            return [], info
        relaxable = [i for i, root in enumerate(roots) if str(root.requirement.specifier)]
        seen: set[tuple[tuple[str, str], ...]] = set()
        for size in range(1, min(len(relaxable), 3) + 1):
            for combo in itertools.combinations(relaxable, size):
                pins = attempt(set(combo))
                if pins is None:
                    continue
                rank, fix = _make_fix(roots, set(combo), pins, solver, index, env)
                key = tuple(sorted(fix.pins.items()))
                if fix.changes and key not in seen:
                    seen.add(key)
                    found.append((rank, fix))
            if len(found) >= max_options:
                break
    except (BudgetExceeded, SearchLimit) as exc:
        info["complete"] = False
        info["stopped"] = str(exc)
    found.sort(key=lambda item: item[0])
    return [fix for _, fix in found[:max_options]], info


# -- putting it together -------------------------------------------------
def target_for(parsed: ParsedError, python: str | None = None, platform: str | None = None) -> TargetEnvironment:
    """Pick the target: explicit options first, then what the error text shows."""
    source = "--python" if python else None
    detected = f"detected from the {parsed.tool} output"
    if not python and parsed.python_version:
        python, source = parsed.python_version, detected
    elif not python and (guess := _python_from_ignored(parsed)):
        python, source = guess, f"inferred from the {parsed.tool} output"
    if platform:
        source = source or "--platform"
    elif parsed.platform_tag:
        guess = platform_from_wheel_tag(parsed.platform_tag)
        if guess and guess != current_platform_key():
            platform, source = guess, source or detected
    return TargetEnvironment.create(python, platform, source=source)


def _python_from_ignored(parsed: ParsedError) -> str | None:
    """Guess pip's Python from "Ignored the following versions that require a different python".

    pip's Python satisfies none of the listed Requires-Python values; if the
    running interpreter does, the error came from another (older) Python.
    """
    specs = []
    for item in parsed.python_mismatches:
        if item.python is None and parsed.tool == "pip":
            try:
                specs.append(SpecifierSet(item.requires_python))
            except ValueError:
                continue
    if not specs:
        return None
    fits = [f"3.{minor}" for minor in range(7, 20) if not any(s.contains(f"3.{minor}.0", prereleases=True) for s in specs)]
    current = f"{sys.version_info[0]}.{sys.version_info[1]}"
    return fits[-1] if fits and current not in fits else None


def make_index_factory(
    *,
    max_requests: int = 150,
    timeout: float = 30.0,
    cache_dir: str | Path | None = None,
    use_cache: bool = True,
    pypi_url: str = DEFAULT_URL,
) -> IndexFactory:
    """Return a callable that creates the PyPI client when it is first needed."""
    return lambda: PyPIClient(
        pypi_url, cache_dir=cache_dir, use_cache=use_cache, max_requests=max_requests, time_budget=timeout
    )


def build_report(
    parsed: ParsedError,
    env: TargetEnvironment,
    *,
    index_factory: IndexFactory,
    requirements: Sequence[str] | None = None,
    constraints: Sequence[str] = (),
    offline: bool = False,
    pre: bool = False,
    max_options: int = 3,
) -> Report:
    """Explain *parsed* and, unless offline, search PyPI for fixes."""
    report = Report(parsed=parsed, target=env.describe(), explanation=explain_lines(parsed, env))
    if parsed.kind in ("none", "unrecognized"):
        return report
    note = (
        f"pip also listed {_join(parsed.no_candidates)} under \"no matching distributions available for your "
        "environment\". Recent pip versions print that line for every package in a conflict, so on its own it "
        "does not mean a package is missing."
    )
    if parsed.no_candidates:
        report.notes.append(note)
    roots, scope = build_roots(parsed, requirements, constraints)
    if offline:
        report.notes.append("Offline mode: explanation only. Run without --offline to look up versions that work on PyPI.")
        return report
    if not roots:
        if parsed.kind == "conflict":
            report.notes.append("No requirement with a version was found in the error, so there is nothing to search.")
        return report
    index = index_factory()
    said = {(name_of(u.requirement), u.reason) for u in parsed.unavailable}
    try:
        for root in roots:
            if root.origin == "constraint":
                continue
            for code, line in diagnose(root, index, env, pre):
                repeated = (code == "no-match" and any(name == root.name for name, _ in said)) or (
                    code == "no-wheel" and (root.name, "no-wheel") in said
                )
                if not repeated and line not in report.explanation:
                    report.explanation.append(line)
        fixes, search = search_fixes(roots, scope, index, env, pre=pre, max_options=max_options)
    except (NetworkError, OfflineError) as exc:
        report.notes.append(f"Could not look up versions on PyPI ({exc}). Showing the explanation only; use --offline to skip the lookup.")
        return report
    except BudgetExceeded as exc:
        report.notes.append(f"Stopped looking up versions: {exc}.")
        return report
    report.fixes = fixes
    report.search = {**search, **getattr(index, "stats", {})}
    if not search["reproduced"]:
        pins = ", ".join(f"{name} {version}" for name, version in search["baseline"].items())
        report.notes.append(
            f"With PyPI data for {env.label} these requirements look compatible ({pins}). The error may come from a "
            "different Python version or platform (try --python / --platform), another index, or packages outside "
            "the conflict."
        )
    elif not search["complete"]:
        report.notes.append(f"The search stopped early ({search['stopped']}); raise --max-requests or --timeout to look further.")
    elif not fixes and parsed.kind == "conflict":
        report.notes.append(f"No combination of versions of {_join(sorted(scope))} works for {env.label} (checked on PyPI).")
    return report


def explain(
    text: str,
    *,
    python: str | None = None,
    platform: str | None = None,
    offline: bool = False,
    pre: bool = False,
    max_options: int = 3,
    max_requests: int = 150,
    timeout: float = 30.0,
    cache_dir: str | Path | None = None,
    use_cache: bool = True,
    pypi_url: str = DEFAULT_URL,
    index: Index | None = None,
) -> Report:
    """Explain a pip or uv error and suggest versions that work.

    *text* is the error output (the whole log is fine). *python* and *platform*
    override the target; by default they are detected from the text or taken
    from the running interpreter. Pass *index* to use your own package index
    object (tests do this); otherwise PyPI is queried read-only.
    """
    parsed = parse_error(text)
    env = target_for(parsed, python, platform)
    factory = (lambda: index) if index is not None else make_index_factory(
        max_requests=max_requests, timeout=timeout, cache_dir=cache_dir, use_cache=use_cache, pypi_url=pypi_url
    )
    return build_report(parsed, env, index_factory=factory, offline=offline, pre=pre, max_options=max_options)
