"""The PyPI client: trimming, disk cache with TTL, offline mode, failures and the budget."""

from __future__ import annotations

import json
import time

import pytest
from helpers import fixture_fetch
from packaging.version import Version

from pip_conflict_explainer.pypi import BudgetExceeded, NetworkError, OfflineError, PyPIClient


class CountingFetch:
    def __init__(self, fail: bool = False) -> None:
        self.urls: list[str] = []
        self.fail = fail

    def __call__(self, url: str, timeout: float) -> bytes:
        self.urls.append(url)
        if self.fail:
            raise OSError("network is unreachable")
        return fixture_fetch(url, timeout)


def test_releases_are_trimmed_and_sorted(tmp_path) -> None:
    client = PyPIClient(cache_dir=tmp_path, fetch=fixture_fetch)
    releases = client.releases("NumPy")
    assert releases is not None
    assert [str(r.version) for r in releases][:3] == ["2.3.5", "2.3.0", "2.2.6"]
    newest = releases[0]
    assert newest.requires_python == ">=3.11"
    assert any(name.endswith("cp314-win_amd64.whl") for name in newest.files)
    assert client.dependencies("pandas", Version("2.2.0"))[:3] == [
        'numpy<2,>=1.22.4; python_version < "3.11"',
        'numpy<2,>=1.23.2; python_version == "3.11"',
        'numpy<2,>=1.26.0; python_version >= "3.12"',
    ]
    assert client.releases("no-such-project-here") is None  # HTTP 404


def test_cache_is_reused_until_the_ttl_expires(tmp_path) -> None:
    fetch = CountingFetch()
    PyPIClient(cache_dir=tmp_path, fetch=fetch).releases("urllib3")
    PyPIClient(cache_dir=tmp_path, fetch=fetch).releases("urllib3")
    assert len(fetch.urls) == 1
    entry = tmp_path / "project-urllib3.json"
    data = json.loads(entry.read_text(encoding="utf-8"))
    data["time"] = time.time() - 2 * 24 * 3600
    entry.write_text(json.dumps(data), encoding="utf-8")
    PyPIClient(cache_dir=tmp_path, fetch=fetch).releases("urllib3")
    assert len(fetch.urls) == 2


def test_offline_mode_uses_only_the_cache(tmp_path) -> None:
    with pytest.raises(OfflineError):
        PyPIClient(cache_dir=tmp_path, offline=True, fetch=CountingFetch()).releases("urllib3")
    PyPIClient(cache_dir=tmp_path, fetch=fixture_fetch).releases("urllib3")
    offline = PyPIClient(cache_dir=tmp_path, offline=True, ttl=0, fetch=CountingFetch(fail=True))
    assert offline.releases("urllib3") is not None  # stale entries are fine offline


def test_network_errors(tmp_path) -> None:
    with pytest.raises(NetworkError):
        PyPIClient(cache_dir=tmp_path, fetch=CountingFetch(fail=True)).releases("urllib3")
    PyPIClient(cache_dir=tmp_path, fetch=fixture_fetch).releases("urllib3")
    stale = PyPIClient(cache_dir=tmp_path, ttl=0, fetch=CountingFetch(fail=True))
    assert stale.releases("urllib3") is not None  # falls back to the stale cache


def test_request_and_time_budget() -> None:
    client = PyPIClient(use_cache=False, max_requests=1, fetch=fixture_fetch)
    client.releases("urllib3")
    with pytest.raises(BudgetExceeded):
        client.releases("requests")
    late = PyPIClient(use_cache=False, time_budget=-1, fetch=fixture_fetch)  # deadline already passed
    with pytest.raises(BudgetExceeded):
        late.releases("urllib3")


def test_prefetch_fills_the_memory_cache() -> None:
    fetch = CountingFetch()
    client = PyPIClient(use_cache=False, fetch=fetch)
    versions = [r.version for r in client.releases("requests") or []]
    client.prefetch("requests", versions)
    count = len(fetch.urls)
    assert count == 1 + len(versions)
    client.dependencies("requests", versions[0])
    assert len(fetch.urls) == count
