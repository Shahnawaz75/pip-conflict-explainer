"""The bounded backtracking search on small synthetic indexes with known answers."""

from __future__ import annotations

from typing import Any

import pytest
from helpers import FakeIndex
from packaging.requirements import Requirement

from pip_conflict_explainer.environment import TargetEnvironment
from pip_conflict_explainer.solver import SearchLimit, Solver

PY310 = TargetEnvironment.create("3.10", "linux")
PY312 = TargetEnvironment.create("3.12", "linux")
APP = {
    "app": {"1.0": {"deps": ["lib>=1,<3"]}, "2.0": {"deps": ["lib>=3"]}},
    "lib": {"1.5": {}, "2.5": {}, "3.1": {}, "4.0": {}},
}


def solve(packages: dict[str, Any], roots: list[str], env: TargetEnvironment = PY310, **options: Any):
    solver = Solver(FakeIndex(packages), env, set(packages), **options)
    constraints = [Requirement(c[2:]) for c in roots if c.startswith("c:")]
    pins = solver.solve([Requirement(r) for r in roots if not r.startswith("c:")], constraints)
    return None if pins is None else {name: str(release.version) for name, release in sorted(pins.items())}


def test_newest_versions_that_fit() -> None:
    assert solve(APP, ["app"]) == {"app": "2.0", "lib": "4.0"}
    assert solve(APP, ["app", "lib<3"]) == {"app": "1.0", "lib": "2.5"}


def test_no_solution_returns_none() -> None:
    assert solve(APP, ["app==2.0", "lib<3"]) is None
    assert solve(APP, ["app", "lib>9"]) is None


def test_constraints_limit_but_do_not_add_packages() -> None:
    assert solve(APP, ["app", "c:lib<2"]) == {"app": "1.0", "lib": "1.5"}
    assert solve(APP, ["app", "c:unrelated==1"]) == {"app": "2.0", "lib": "4.0"}


def test_markers_follow_the_target_python() -> None:
    packages = {
        "app": {"1.0": {"deps": ['lib<2; python_version < "3.11"', 'lib>=2; python_version >= "3.11"']}},
        "lib": {"1.5": {}, "2.5": {}},
    }
    assert solve(packages, ["app"], PY310) == {"app": "1.0", "lib": "1.5"}
    assert solve(packages, ["app"], PY312) == {"app": "1.0", "lib": "2.5"}
    assert solve(packages, ['app; python_version >= "3.11"'], PY310) == {}


def test_extras_add_their_dependencies() -> None:
    packages = {
        "app": {"1.0": {"deps": ["lib>=1", 'plugin>=2; extra == "fast"']}},
        "lib": {"1.0": {}},
        "plugin": {"1.0": {}, "2.0": {}},
    }
    assert solve(packages, ["app", "plugin<2"]) == {"app": "1.0", "lib": "1.0", "plugin": "1.0"}
    assert solve(packages, ["app[fast]", "plugin<2"]) is None
    assert solve(packages, ["app[fast]"]) == {"app": "1.0", "lib": "1.0", "plugin": "2.0"}


def test_yanked_releases_only_when_pinned_exactly() -> None:
    packages = {"lib": {"1.0": {}, "1.1": {"yanked": True}}}
    assert solve(packages, ["lib"]) == {"lib": "1.0"}
    assert solve(packages, ["lib>=1.1"]) is None
    assert solve(packages, ["lib==1.1"]) == {"lib": "1.1"}


def test_prereleases_need_pre_or_an_explicit_specifier() -> None:
    packages = {"lib": {"1.0": {}, "2.0rc1": {}}}
    assert solve(packages, ["lib"]) == {"lib": "1.0"}
    assert solve(packages, ["lib"], allow_pre=True) == {"lib": "2.0rc1"}
    assert solve(packages, ["lib>=2.0rc1"]) == {"lib": "2.0rc1"}
    assert solve(packages, ["lib>=2"]) is None


def test_requires_python_and_wheel_tags() -> None:
    packages = {
        "lib": {
            "3.0": {"requires_python": ">=3.11"},
            "2.0": {"files": ["lib-2.0-cp39-cp39-manylinux_2_17_x86_64.whl"]},
            "1.5": {"files": ["lib-1.5.tar.gz"]},
            "1.2": {"files": ["lib-1.2-cp310-cp310-manylinux_2_17_x86_64.whl", "lib-1.2.tar.gz"]},
        }
    }
    solver = Solver(FakeIndex(packages), PY310, {"lib"})
    candidates = solver.candidates("lib", [Requirement("lib").specifier])
    # 3.0 needs a newer Python, 2.0 has no usable file, wheels come before source-only releases.
    assert [str(c.version) for c in candidates] == ["1.2", "1.5"]
    assert solver.kind("lib", candidates[1]) == "sdist"
    assert solve(packages, ["lib"], PY312) == {"lib": "3.0"}


def test_long_candidate_lists_are_probed_not_scanned() -> None:
    packages = {
        "big": {f"{i}.0": {"deps": [f"core>={i}.0"]} for i in range(1, 61)},
        "core": {f"{i}.0": {} for i in range(1, 61)},
    }
    index = FakeIndex(packages)
    pins = Solver(index, PY310, set(packages)).solve([Requirement("big"), Requirement("core==5.0")])
    assert pins is not None and str(pins["big"].version) == "5.0"
    assert index.dependency_calls < 20  # a linear scan would need 56 lookups


def test_step_limit_bounds_the_search() -> None:
    with pytest.raises(SearchLimit):
        Solver(FakeIndex(APP), PY310, set(APP), max_steps=1).solve([Requirement("app")])


def test_dependencies_outside_scope_are_ignored() -> None:
    packages = {"app": {"1.0": {"deps": ["lib>=1", "outside>=99"]}}, "lib": {"1.0": {}}}
    assert solve(packages, ["app"]) == {"app": "1.0", "lib": "1.0"}
