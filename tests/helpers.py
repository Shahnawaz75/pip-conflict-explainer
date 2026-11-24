"""Test helpers: fixture loading, a fixture-backed PyPI client and a fake index."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from packaging.version import Version

from pip_conflict_explainer.pypi import NotFound, PyPIClient, Release

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    """A real pip/uv output saved in tests/fixtures."""
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_fetch(url: str, timeout: float) -> bytes:
    """Serve recorded PyPI JSON from tests/fixtures/pypi; anything else is a 404."""
    path = url.removeprefix("https://pypi.org/pypi/").removesuffix("/json")
    file = FIXTURES / "pypi" / (path.replace("/", "-") + ".json")
    if not file.is_file():
        raise NotFound(url)
    return file.read_bytes()


def recorded_index(**kwargs: Any) -> PyPIClient:
    """A PyPI client whose HTTP layer is replaced by the recorded fixtures."""
    return PyPIClient(use_cache=False, fetch=fixture_fetch, **kwargs)


class FakeIndex:
    """Synthetic index: ``{name: {version: {"deps": [...], "requires_python": ..., ...}}}``."""

    def __init__(self, packages: dict[str, dict[str, dict[str, Any]]]) -> None:
        self.packages = packages
        self.dependency_calls = 0

    def releases(self, name: str) -> list[Release] | None:
        versions = self.packages.get(name)
        if versions is None:
            return None
        found = [
            Release(Version(v), info.get("requires_python"), info.get("yanked", False), tuple(info.get("files", ())))
            for v, info in versions.items()
        ]
        return sorted(found, key=lambda release: release.version, reverse=True)

    def dependencies(self, name: str, version: Version) -> list[str] | None:
        self.dependency_calls += 1
        for raw, info in self.packages[name].items():
            if Version(raw) == version:
                return list(info.get("deps", []))
        return None

    def prefetch(self, name: str, versions: object) -> None:
        return None
