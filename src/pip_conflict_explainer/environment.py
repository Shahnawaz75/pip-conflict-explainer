"""The Python version and platform that fixes are computed for."""

from __future__ import annotations

import re
import sys
import sysconfig
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import cached_property, lru_cache

from packaging import tags
from packaging.markers import Marker, default_environment
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import InvalidWheelFilename, parse_wheel_filename

# Marker values for the platforms accepted by ``--platform``.
PLATFORMS: dict[str, dict[str, str]] = {
    "windows": {"sys_platform": "win32", "platform_system": "Windows", "os_name": "nt", "platform_machine": "AMD64"},
    "linux": {"sys_platform": "linux", "platform_system": "Linux", "os_name": "posix", "platform_machine": "x86_64"},
    "linux-aarch64": {
        "sys_platform": "linux",
        "platform_system": "Linux",
        "os_name": "posix",
        "platform_machine": "aarch64",
    },
    "macos": {"sys_platform": "darwin", "platform_system": "Darwin", "os_name": "posix", "platform_machine": "arm64"},
    "macos-x86_64": {
        "sys_platform": "darwin",
        "platform_system": "Darwin",
        "os_name": "posix",
        "platform_machine": "x86_64",
    },
}
ALIASES = {
    "win": "windows",
    "win32": "windows",
    "win_amd64": "windows",
    "win-amd64": "windows",
    "linux-x86_64": "linux",
    "manylinux": "linux",
    "darwin": "macos",
    "mac": "macos",
    "macos-arm64": "macos",
}
_SDIST_SUFFIXES = (".tar.gz", ".zip", ".tar.bz2", ".tgz", ".tar.xz")


def _wheel_platforms(key: str) -> list[str]:
    """Wheel platform tags pip would accept on the given ``--platform``."""
    arch = PLATFORMS[key]["platform_machine"]
    if key == "windows":
        return ["win_amd64"]
    if key.startswith("linux"):
        lowest = 4 if arch == "x86_64" else 16
        names = [f"manylinux_2_{minor}_{arch}" for minor in range(40, lowest, -1)]
        names.append(f"manylinux2014_{arch}")
        if arch == "x86_64":
            names += ["manylinux2010_x86_64", "manylinux1_x86_64"]
        return names
    return list(tags.mac_platforms((15, 0), arch))


def current_platform_key() -> str | None:
    """The ``--platform`` name matching this machine, if there is one."""
    plat = sysconfig.get_platform()
    if plat == "win-amd64":
        return "windows"
    if plat.startswith("linux"):
        return "linux-aarch64" if plat.endswith("aarch64") else "linux" if plat.endswith("x86_64") else None
    if plat.startswith("macosx"):
        return "macos" if plat.endswith(("arm64", "universal2")) else "macos-x86_64"
    return None


def platform_from_wheel_tag(tag: str) -> str | None:
    """Map a wheel platform tag such as ``win_amd64`` to a ``--platform`` name."""
    if tag == "win_amd64":
        return "windows"
    if "linux" in tag:
        return "linux-aarch64" if tag.endswith("aarch64") else "linux" if tag.endswith("x86_64") else None
    if tag.startswith("macosx"):
        return "macos" if tag.endswith(("arm64", "universal2")) else "macos-x86_64"
    return None


@lru_cache(maxsize=4096)
def _specifier(text: str) -> SpecifierSet | None:
    try:
        return SpecifierSet(text)
    except InvalidSpecifier:
        return None


def wheel_pythons(files: Iterable[str]) -> list[str]:
    """Python versions (``3.10`` ...) that the CPython wheels in *files* are built for."""
    found: set[tuple[int, int]] = set()
    for name in files:
        match = re.search(r"-cp3(\d{1,2})-cp3\d{1,2}t?-", name)
        if match:
            found.add((3, int(match.group(1))))
    return [f"{major}.{minor}" for major, minor in sorted(found)]


@dataclass(frozen=True)
class TargetEnvironment:
    """Marker values and wheel tags for one Python version on one platform."""

    python_version: str
    python_full_version: str
    platform: str
    markers: dict[str, str] = field(compare=False)
    platform_key: str | None = None
    is_current: bool = False
    source: str = "current interpreter"

    @classmethod
    def create(cls, python: str | None = None, platform: str | None = None, source: str | None = None) -> TargetEnvironment:
        """Build the environment for ``python`` (e.g. ``"3.12"``) and ``platform``.

        ``None`` means "the interpreter running this code" for either value.
        """
        env = {key: str(value) for key, value in default_environment().items()}
        current = f"{sys.version_info[0]}.{sys.version_info[1]}"
        short, full = current, env["python_full_version"]
        if python:
            if not re.fullmatch(r"3\.\d{1,2}(\.\d+)?", python):
                raise ValueError(f"--python must look like 3.12 or 3.12.4, got {python!r}")
            short = ".".join(python.split(".")[:2])
            if python.count(".") == 2:
                full = python
            elif short != current:
                full = f"{short}.0"
            if short != current:
                env.update(implementation_name="cpython", platform_python_implementation="CPython")
            env.update(python_version=short, python_full_version=full, implementation_version=full)
        key = None
        if platform:
            key = ALIASES.get(platform.lower(), platform.lower())
            if key not in PLATFORMS:
                choices = ", ".join(sorted(PLATFORMS))
                raise ValueError(f"unknown --platform {platform!r}; choose one of: {choices}")
            if key != current_platform_key():
                env.update(PLATFORMS[key], platform_release="", platform_version="")
        is_current = short == current and key is None
        label = key or sysconfig.get_platform()
        return cls(short, full, label, env, key, is_current, source or ("current interpreter" if is_current else "--python/--platform"))

    @property
    def label(self) -> str:
        """Human-readable target, e.g. ``Python 3.12 on win-amd64``."""
        return f"Python {self.python_version} on {self.platform}"

    def describe(self) -> dict[str, str]:
        """JSON-friendly description of the target."""
        return {
            "python": self.python_version,
            "python_full_version": self.python_full_version,
            "platform": self.platform,
            "source": self.source,
        }

    @cached_property
    def supported_tags(self) -> frozenset[tags.Tag]:
        """Wheel tags an installer would accept for this target."""
        if self.is_current:
            return frozenset(tags.sys_tags())
        major, minor = (int(part) for part in self.python_version.split("."))
        platforms = _wheel_platforms(self.platform_key) if self.platform_key else list(tags.platform_tags())
        found = set(tags.cpython_tags((major, minor), platforms=platforms))
        found.update(tags.compatible_tags((major, minor), f"cp{major}{minor}", platforms))
        return frozenset(found)

    def python_ok(self, requires_python: str | None) -> bool:
        """True if ``Requires-Python`` allows this Python (invalid values are ignored)."""
        if not requires_python:
            return True
        spec = _specifier(requires_python)
        return spec is None or spec.contains(self.python_full_version, prereleases=True)

    def file_kind(self, files: Sequence[str]) -> str | None:
        """``"wheel"`` if a wheel fits, ``"sdist"`` if only a source archive does, else ``None``.

        An empty file list means "unknown" and counts as a fitting wheel.
        """
        if not files:
            return "wheel"
        has_sdist = False
        for name in files:
            if name.endswith(".whl"):
                try:
                    wheel_tags = parse_wheel_filename(name)[3]
                except InvalidWheelFilename:
                    continue
                if not self.supported_tags.isdisjoint(wheel_tags):
                    return "wheel"
            elif name.lower().endswith(_SDIST_SUFFIXES):
                has_sdist = True
        return "sdist" if has_sdist else None

    def evaluate(self, marker: Marker, extra: str = "") -> bool:
        """Evaluate an environment marker; markers that cannot be evaluated count as true."""
        try:
            return marker.evaluate({**self.markers, "extra": extra})
        except Exception:  # noqa: BLE001 - unknown marker variables, invalid versions...
            return True
