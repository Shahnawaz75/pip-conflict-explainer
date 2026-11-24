"""Target Python/platform: marker values, wheel tags and Requires-Python."""

from __future__ import annotations

import pytest
from packaging.markers import Marker

from pip_conflict_explainer.environment import TargetEnvironment, platform_from_wheel_tag, wheel_pythons


def test_overrides_set_marker_values() -> None:
    env = TargetEnvironment.create("3.12", "linux")
    assert env.markers["python_version"] == "3.12"
    assert env.markers["python_full_version"].startswith("3.12.")  # 3.12.0, or the real one when running 3.12
    assert env.markers["sys_platform"] == "linux"
    assert env.evaluate(Marker('python_version >= "3.11" and sys_platform == "linux"'))
    assert not env.evaluate(Marker('platform_system == "Windows"'))
    assert env.evaluate(Marker('extra == "fast"'), extra="fast")
    assert TargetEnvironment.create("3.10.4", "macos").python_full_version == "3.10.4"


def test_wheel_compatibility() -> None:
    win310 = TargetEnvironment.create("3.10", "windows")
    assert win310.file_kind(["pkg-1.0-cp310-cp310-win_amd64.whl"]) == "wheel"
    assert win310.file_kind(["pkg-1.0-cp38-abi3-win_amd64.whl"]) == "wheel"
    assert win310.file_kind(["pkg-1.0-py3-none-any.whl"]) == "wheel"
    assert win310.file_kind(["pkg-1.0-cp311-cp311-win_amd64.whl", "pkg-1.0.tar.gz"]) == "sdist"
    assert win310.file_kind(["pkg-1.0-cp310-cp310-manylinux_2_17_x86_64.whl"]) is None
    linux = TargetEnvironment.create("3.12", "linux")
    assert linux.file_kind(["pkg-1.0-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"]) == "wheel"
    mac = TargetEnvironment.create("3.12", "macos")
    assert mac.file_kind(["pkg-1.0-cp312-cp312-macosx_11_0_arm64.whl"]) == "wheel"
    assert mac.file_kind(["pkg-1.0-cp312-cp312-macosx_10_9_x86_64.whl"]) is None


def test_requires_python() -> None:
    env = TargetEnvironment.create("3.10", "linux")
    assert env.python_ok(">=3.8") and env.python_ok(None) and env.python_ok("not a specifier")
    assert not env.python_ok(">=3.11")
    assert not env.python_ok("<3.10,>=3.7")


def test_bad_values_are_rejected() -> None:
    with pytest.raises(ValueError):
        TargetEnvironment.create("python3", None)
    with pytest.raises(ValueError):
        TargetEnvironment.create(None, "solaris")


def test_platform_and_python_helpers() -> None:
    assert platform_from_wheel_tag("win_amd64") == "windows"
    assert platform_from_wheel_tag("manylinux_2_17_aarch64") == "linux-aarch64"
    assert platform_from_wheel_tag("macosx_11_0_arm64") == "macos"
    assert wheel_pythons(["t-1-cp311-cp311-win_amd64.whl", "t-1-cp39-cp39-win_amd64.whl", "t-1.tar.gz"]) == ["3.9", "3.11"]
