"""Every test runs without network access and with a private cache folder."""

from __future__ import annotations

import pytest

from pip_conflict_explainer import pypi


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    def blocked(url: str, timeout: float) -> bytes:
        raise AssertionError(f"tests must not use the network: {url}")

    monkeypatch.setattr(pypi, "http_get", blocked)
    monkeypatch.setenv("PIP_CONFLICT_CACHE_DIR", str(tmp_path / "cache"))
