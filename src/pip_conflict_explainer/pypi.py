"""A small read-only client for the PyPI JSON API, with a disk cache and a budget."""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from . import __version__

DEFAULT_URL = "https://pypi.org/pypi"
DEFAULT_TTL = 24 * 3600.0
USER_AGENT = f"pip-conflict-explainer/{__version__} (+https://github.com/Shahnawaz75/pip-conflict-explainer)"

Fetch = Callable[[str, float], bytes]


class PyPIError(Exception):
    """Base class for lookup problems."""


class OfflineError(PyPIError):
    """Raised when offline mode needs data that is not in the cache."""


class BudgetExceeded(PyPIError):
    """Raised when the request or time budget is used up."""


class NetworkError(PyPIError):
    """Raised when PyPI cannot be reached and nothing is cached."""


class NotFound(Exception):
    """Raised by a fetch function for HTTP 404."""


@dataclass(frozen=True)
class Release:
    """One release of a project as listed by PyPI."""

    version: Version
    requires_python: str | None = None
    yanked: bool = False
    files: tuple[str, ...] = ()


def default_cache_dir() -> Path:
    """The per-user cache folder (``PIP_CONFLICT_CACHE_DIR`` overrides it)."""
    override = os.environ.get("PIP_CONFLICT_CACHE_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "pip-conflict-explainer" / "Cache"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "pip-conflict-explainer"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "pip-conflict-explainer"


def http_get(url: str, timeout: float) -> bytes:
    """GET *url* and return the body; raise :class:`NotFound` on HTTP 404."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - https URL
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NotFound(url) from exc
        raise


def _trim_project(doc: dict[str, Any]) -> dict[str, Any]:
    """Keep only what the search needs from ``/pypi/<name>/json``."""
    releases: dict[str, Any] = {}
    for version, files in (doc.get("releases") or {}).items():
        if not files:
            continue
        live = [f for f in files if not f.get("yanked")]
        releases[version] = {
            "files": [f["filename"] for f in (live or files)],
            "requires_python": next((f["requires_python"] for f in files if f.get("requires_python")), None),
            "yanked": not live,
        }
    return {"name": (doc.get("info") or {}).get("name"), "releases": releases}


def _trim_release(doc: dict[str, Any]) -> dict[str, Any]:
    """Keep only what the search needs from ``/pypi/<name>/<version>/json``."""
    info = doc.get("info") or {}
    return {"requires_dist": info.get("requires_dist"), "requires_python": info.get("requires_python") or None}


class PyPIClient:
    """Read-only PyPI JSON client.

    Responses are trimmed and cached on disk for ``ttl`` seconds. Each network
    request counts against ``max_requests`` and the ``time_budget`` (seconds
    from creation); when either runs out :class:`BudgetExceeded` is raised, so
    a search can never hang. ``fetch`` can be replaced in tests.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_URL,
        *,
        cache_dir: str | Path | None = None,
        use_cache: bool = True,
        ttl: float = DEFAULT_TTL,
        offline: bool = False,
        max_requests: int = 150,
        time_budget: float = 30.0,
        timeout: float = 10.0,
        fetch: Fetch | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.cache_dir = (Path(cache_dir) if cache_dir else default_cache_dir()) if use_cache else None
        self.ttl = ttl
        self.offline = offline
        self.max_requests = max_requests
        self.time_budget = time_budget
        self.timeout = timeout
        self.stats = {"requests": 0, "cache_hits": 0}
        self._fetch = fetch or http_get
        self._deadline = time.monotonic() + time_budget
        self._memory: dict[str, Any] = {}
        self._releases: dict[str, list[Release] | None] = {}
        self._raw_versions: dict[tuple[str, Version], str] = {}
        self._lock = threading.Lock()

    def releases(self, name: str) -> list[Release] | None:
        """All releases of *name*, newest first, or ``None`` if PyPI has no such project."""
        key = canonicalize_name(name)
        if key not in self._releases:
            data = self._get(f"project-{key}", f"{self.base_url}/{key}/json", _trim_project)
            found: list[Release] | None = None
            if data is not None:
                found = []
                for raw, info in data["releases"].items():
                    try:
                        version = Version(raw)
                    except InvalidVersion:
                        continue
                    self._raw_versions[(key, version)] = raw
                    files = tuple(info.get("files") or ())
                    found.append(Release(version, info.get("requires_python"), bool(info.get("yanked")), files))
                found.sort(key=lambda release: release.version, reverse=True)
            self._releases[key] = found
        return self._releases[key]

    def dependencies(self, name: str, version: Version) -> list[str] | None:
        """``Requires-Dist`` of one release (``None`` if PyPI does not know them)."""
        key = canonicalize_name(name)
        raw = self._raw_versions.get((key, version), str(version))
        data = self._get(f"release-{key}-{raw}", f"{self.base_url}/{key}/{raw}/json", _trim_release)
        return None if data is None else data.get("requires_dist")

    def prefetch(self, name: str, versions: Sequence[Version]) -> None:
        """Fetch several releases' metadata in parallel (errors are left for later)."""
        key = canonicalize_name(name)
        todo = [v for v in versions if f"release-{key}-{self._raw_versions.get((key, v), v)}" not in self._memory]
        if self.offline or len(todo) < 2:
            return

        def one(version: Version) -> None:
            try:
                self.dependencies(name, version)
            except PyPIError:
                pass

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(one, todo))

    # -- internals -------------------------------------------------------
    def _get(self, key: str, url: str, trim: Callable[[dict[str, Any]], dict[str, Any]]) -> Any:
        with self._lock:
            if key in self._memory:
                return self._memory[key]
        cached = self._read_cache(key)
        if cached is not None and (self.offline or time.time() - cached[0] < self.ttl):
            with self._lock:
                self.stats["cache_hits"] += 1
            return self._remember(key, cached[1])
        if self.offline:
            raise OfflineError(f"offline mode: {url} is not cached")
        self._spend()
        try:
            data = trim(json.loads(self._fetch(url, self.timeout).decode("utf-8")))
        except NotFound:
            data = None
        except (OSError, ValueError) as exc:
            if cached is not None:  # stale cache beats no answer
                return self._remember(key, cached[1])
            raise NetworkError(f"could not fetch {url}: {exc}") from exc
        self._write_cache(key, url, data)
        return self._remember(key, data)

    def _remember(self, key: str, data: Any) -> Any:
        with self._lock:
            self._memory[key] = data
        return data

    def _spend(self) -> None:
        with self._lock:
            if self.stats["requests"] >= self.max_requests:
                raise BudgetExceeded(f"used the limit of {self.max_requests} PyPI requests")
            if time.monotonic() > self._deadline:
                raise BudgetExceeded(f"used the {self.time_budget:g} second time limit")
            self.stats["requests"] += 1

    def _cache_path(self, key: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / (re.sub(r"[^A-Za-z0-9._-]", "_", key) + ".json")

    def _read_cache(self, key: str) -> tuple[float, Any] | None:
        path = self._cache_path(key)
        if path is None or not path.is_file():
            return None
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            return float(entry["time"]), entry["data"]
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _write_cache(self, key: str, url: str, data: Any) -> None:
        path = self._cache_path(key)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
            tmp.write_text(json.dumps({"time": time.time(), "url": url, "data": data}), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            pass
