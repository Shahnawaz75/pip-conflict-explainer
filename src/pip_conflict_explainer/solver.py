"""A small, bounded backtracking search over the packages involved in a conflict.

This is not a full resolver: only packages in ``scope`` (the ones named in the
error) are expanded, and dependencies on anything else are assumed to work out.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Protocol

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from .environment import TargetEnvironment
from .pypi import Release

Requirements = dict[str, list[tuple[Requirement, "str | None"]]]


class Index(Protocol):
    """What the solver needs from a package index (see :class:`~.pypi.PyPIClient`)."""

    def releases(self, name: str) -> list[Release] | None: ...

    def dependencies(self, name: str, version: Version) -> list[str] | None: ...

    def prefetch(self, name: str, versions: Sequence[Version]) -> None: ...


class SearchLimit(Exception):
    """Raised when the search used up its step budget."""


def mentions_prerelease(spec: SpecifierSet) -> bool:
    """True if a specifier names a pre-release (``>=2.0b1``), which allows pre-releases."""
    for item in spec:
        if item.operator == "===":
            continue
        try:
            if Version(item.version.rstrip(".*")).is_prerelease:
                return True
        except InvalidVersion:
            continue
    return False


class Solver:
    """Find one set of versions (newest first) that satisfies the given requirements."""

    gallop_after = 12  # candidate lists longer than this are probed, not scanned

    def __init__(
        self,
        index: Index,
        env: TargetEnvironment,
        scope: Sequence[str] | set[str],
        *,
        allow_pre: bool = False,
        max_steps: int = 3000,
    ) -> None:
        self.index = index
        self.env = env
        self.scope = {canonicalize_name(name) for name in scope}
        self.allow_pre = allow_pre
        self.max_steps = max_steps
        self.steps = 0
        self._roots: list[Requirement] = []
        self._constraints: dict[str, list[SpecifierSet]] = {}
        self._deps: dict[tuple[str, Version], list[Requirement]] = {}
        self._kinds: dict[tuple[str, Version], str | None] = {}
        self._candidates: dict[tuple[str, tuple[str, ...]], list[Release]] = {}

    # -- public API ------------------------------------------------------
    def solve(self, roots: Sequence[Requirement], constraints: Sequence[Requirement] = ()) -> dict[str, Release] | None:
        """Return ``{name: release}`` satisfying *roots*, or ``None`` if impossible.

        May raise :class:`SearchLimit` or the index's budget/network errors.
        """
        self._roots = [r for r in roots if self._applies(r, ())]
        self._constraints = {}
        for item in constraints:
            if self._applies(item, ()):
                self._constraints.setdefault(canonicalize_name(item.name), []).append(item.specifier)
        self._candidates = {}
        return self._search({})

    def collect(self, pins: dict[str, Release]) -> Requirements:
        """All requirements in scope implied by the roots and the pinned releases."""
        extras: dict[str, frozenset[str]] = {}
        while True:
            reqs: Requirements = {}
            for root in self._roots:
                reqs.setdefault(canonicalize_name(root.name), []).append((root, None))
            for name, release in pins.items():
                for dep in self.dependencies(name, release.version, extras.get(name, frozenset())):
                    reqs.setdefault(canonicalize_name(dep.name), []).append((dep, f"{name} {release.version}"))
            wanted = {name: frozenset().union(*(r.extras for r, _ in items)) for name, items in reqs.items()}
            if all(wanted[name] <= extras.get(name, frozenset()) for name in wanted if name in pins):
                return reqs
            for name, more in wanted.items():
                extras[name] = extras.get(name, frozenset()) | more

    def candidates(self, name: str, specs: Sequence[SpecifierSet]) -> list[Release]:
        """Releases allowed by *specs* and the constraints, wheels first, newest first."""
        specs = [*specs, *self._constraints.get(name, [])]
        key = (name, tuple(sorted(str(spec) for spec in specs)))
        if key in self._candidates:
            return self._candidates[key]
        allow_pre = self.allow_pre or any(mentions_prerelease(spec) for spec in specs)
        exact = {item.version for spec in specs for item in spec if item.operator in ("==", "===")}
        wheels: list[Release] = []
        sdists: list[Release] = []
        for release in self.index.releases(name) or []:
            version = release.version
            if version.is_prerelease and not allow_pre:
                continue
            if not all(spec.contains(version, prereleases=True) for spec in specs):
                continue
            if release.yanked and not any(_same_version(version, pin) for pin in exact):
                continue  # PEP 592: yanked releases only count when pinned exactly
            if not self.env.python_ok(release.requires_python):
                continue
            kind = self.kind(name, release)
            if kind == "wheel":
                wheels.append(release)
            elif kind == "sdist":
                sdists.append(release)
        self._candidates[key] = wheels + sdists
        return self._candidates[key]

    def kind(self, name: str, release: Release) -> str | None:
        """``"wheel"``, ``"sdist"`` or ``None`` for this target (cached)."""
        key = (name, release.version)
        if key not in self._kinds:
            self._kinds[key] = self.env.file_kind(release.files)
        return self._kinds[key]

    def dependencies(self, name: str, version: Version, extras: frozenset[str] = frozenset()) -> list[Requirement]:
        """In-scope dependencies of one release whose markers apply to the target."""
        key = (name, version)
        if key not in self._deps:
            parsed = []
            for line in self.index.dependencies(name, version) or []:
                try:
                    parsed.append(Requirement(line))
                except InvalidRequirement:
                    continue
            self._deps[key] = parsed
        return [r for r in self._deps[key] if canonicalize_name(r.name) in self.scope and self._applies(r, extras)]

    # -- search ----------------------------------------------------------
    def _applies(self, req: Requirement, extras: frozenset[str] | tuple[()]) -> bool:
        if req.marker is None:
            return True
        return any(self.env.evaluate(req.marker, extra) for extra in ("", *sorted(extras)))

    def _search(self, pins: dict[str, Release]) -> dict[str, Release] | None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise SearchLimit(f"stopped after {self.max_steps} search steps")
        reqs = self.collect(pins)
        for name, release in pins.items():
            if not all(r.specifier.contains(release.version, prereleases=True) for r, _ in reqs.get(name, [])):
                return None
        open_names = [name for name in reqs if name not in pins and name in self.scope]
        if not open_names:
            return dict(pins)
        options = {name: self.candidates(name, [r.specifier for r, _ in reqs[name]]) for name in open_names}
        if not all(options.values()):
            return None
        name = min(open_names, key=lambda n: len(options[n]))
        for release in self._ordered(name, options[name], pins, reqs):
            found = self._search({**pins, name: release})
            if found is not None:
                return found
        return None

    def _ordered(self, name: str, cands: list[Release], pins: dict[str, Release], reqs: Requirements) -> Iterator[Release]:
        """Yield candidates, skipping ahead past versions that need newer dependencies.

        Long lists are probed at 0, 1, 3, 7, 15, ... and then bisected to find the
        first release whose dependencies do not ask for something newer than what
        is already chosen. Skipped releases are tried last, so nothing is lost.
        """
        if len(cands) <= self.gallop_after:
            self.index.prefetch(name, [c.version for c in cands])
            yield from cands
            return
        probes = []
        index = 0
        while index < len(cands):
            probes.append(index)
            index = index * 2 + 1
        self.index.prefetch(name, [cands[i].version for i in probes[:8]])
        too_new: set[int] = set()
        low, high = -1, len(cands)
        for index in probes:
            if not self._needs_newer(name, cands[index], pins, reqs):
                high = index
                break
            too_new.add(index)
            low = index
        while high - low > 1:
            middle = (low + high) // 2
            if self._needs_newer(name, cands[middle], pins, reqs):
                too_new.add(middle)
                low = middle
            else:
                high = middle
        start = min(high, len(cands))
        self.index.prefetch(name, [c.version for c in cands[start : start + 8]])
        yield from cands[start:]
        yield from (c for i, c in enumerate(cands[:start]) if i not in too_new)

    def _needs_newer(self, name: str, release: Release, pins: dict[str, Release], reqs: Requirements) -> bool:
        """True if *release* depends on something newer than the current choices allow."""
        for dep in self.dependencies(name, release.version):
            dep_name = canonicalize_name(dep.name)
            if dep_name in pins:
                allowed = [pins[dep_name]]
            elif dep_name in reqs:
                allowed = self.candidates(dep_name, [r.specifier for r, _ in reqs[dep_name]])
            else:
                continue
            if not allowed or any(dep.specifier.contains(a.version, prereleases=True) for a in allowed):
                continue
            top = max(a.version for a in allowed)
            for other in self.index.releases(dep_name) or []:
                if other.version > top and dep.specifier.contains(other.version, prereleases=True):
                    return True
        return False


def _same_version(version: Version, text: str) -> bool:
    try:
        return version == Version(text)
    except InvalidVersion:
        return str(version) == text
