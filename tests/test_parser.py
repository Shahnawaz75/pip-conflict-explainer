"""The parser against real pip 26.3 and uv 0.13.9 output (see tests/fixtures)."""

from __future__ import annotations

from helpers import fixture_text

from pip_conflict_explainer.models import Cause, PythonMismatch, Unavailable
from pip_conflict_explainer.parser import _pip_requirement, _split_triggers, exact_version, name_of, parse_error


def test_pip_pandas_numpy() -> None:
    parsed = parse_error(fixture_text("pip_pandas_numpy.txt"))
    assert (parsed.tool, parsed.kind) == ("pip", "conflict")
    assert parsed.requested == ["pandas==2.2.0", "numpy==1.21.0"]
    assert parsed.causes == [
        Cause("numpy==1.21.0"),
        Cause('numpy<2,>=1.22.4; python_version < "3.11"', parent="pandas", parent_version="2.2.0"),
    ]
    assert parsed.no_candidates == ["numpy"]
    assert (parsed.python_version, parsed.platform_tag) == ("3.10", "win_amd64")
    assert parsed.error_lines == [
        "ERROR: Cannot install numpy==1.21.0 and pandas==2.2.0 because these package versions have "
        "conflicting dependencies.",
        "ERROR: ResolutionImpossible: for help visit "
        "https://pip.pypa.io/en/latest/topics/dependency-resolution/#dealing-with-dependency-conflicts",
    ]


def test_pip_requests_urllib3() -> None:
    parsed = parse_error(fixture_text("pip_requests_urllib3.txt"))
    assert parsed.kind == "conflict"
    assert parsed.requested == ["requests==2.31.0", "urllib3==1.20"]
    assert parsed.causes == [
        Cause("urllib3==1.20"),
        Cause("urllib3<3,>=1.21.1", parent="requests", parent_version="2.31.0"),
    ]
    assert parsed.python_version == "3.14"


def test_pip_transitive_boto3() -> None:
    parsed = parse_error(fixture_text("pip_boto3.txt"))
    assert parsed.kind == "conflict"
    assert parsed.requested == ["boto3==1.34.0", "aiobotocore==2.5.0"]
    assert parsed.causes == [
        Cause("botocore<1.35.0,>=1.34.0", parent="boto3", parent_version="1.34.0"),
        Cause("botocore<1.29.77,>=1.29.76", parent="aiobotocore", parent_version="2.5.0"),
    ]
    assert parsed.no_candidates == ["botocore"]
    assert parsed.python_version is None  # only pure-Python wheels in the log


def test_pip_constraint_and_requirements_file() -> None:
    parsed = parse_error(fixture_text("pip_constraint.txt"))
    assert parsed.kind == "conflict"
    assert parsed.requested == ["requests==2.31.0", "-r req-constraint.txt (line 1)"]
    assert parsed.causes == [
        Cause("urllib3<3,>=1.21.1", parent="requests", parent_version="2.31.0"),
        Cause("urllib3<1.21", constraint=True),
    ]
    reqfile = parse_error(fixture_text("pip_reqfile.txt"))
    assert reqfile.requested == ["pandas==2.2.0", "numpy==1.21.0", "-r requirements-pn.txt (line 1)"]


def test_pip_requires_python_from_ignored_versions() -> None:
    parsed = parse_error(fixture_text("pip_numpy_python.txt"))
    assert (parsed.kind, parsed.requested) == ("requires-python", ["numpy==2.3.0"])
    assert len(parsed.python_mismatches) == 21
    assert parsed.python_mismatches[0] == PythonMismatch("numpy", ">=3.11", version="2.3.0")
    assert parsed.python_mismatches[-1] == PythonMismatch("numpy", ">=3.12", version="2.5.5")
    (missing,) = parsed.unavailable
    assert missing.requirement == "numpy==2.3.0"
    assert missing.available is not None and missing.available[-2:] == ("2.2.5", "2.2.6")


def test_pip_requires_a_different_python() -> None:
    parsed = parse_error(fixture_text("pip_local_python.txt"))
    assert (parsed.tool, parsed.kind) == ("pip", "requires-python")
    assert parsed.python_mismatches == [PythonMismatch("demo-app", ">=3.11", python="3.10.22")]
    assert parsed.python_version == "3.10.22"


def test_pip_no_matching_distribution_cases() -> None:
    tensorflow = parse_error(fixture_text("pip_tensorflow.txt"))
    assert tensorflow.kind == "no-matching-distribution"
    assert tensorflow.unavailable == [Unavailable("tensorflow==2.15.0", available=("2.22.0rc0", "2.22.0rc1"))]
    missing = parse_error(fixture_text("pip_not_found.txt"))
    assert missing.unavailable == [Unavailable("this-package-does-not-exist-pce", available=())]
    version = parse_error(fixture_text("pip_no_version.txt"))
    (item,) = version.unavailable
    assert item.requirement == "requests==9.9"
    assert item.available is not None and item.available[0] == "0.2.0"
    assert item.available[-4:] == ("2.34.0.dev1", "2.34.0", "2.34.1", "2.34.2")
    assert version.yanked == ["2.32.0", "2.32.1"]


def test_uv_conflicts() -> None:
    parsed = parse_error(fixture_text("uv_pandas_numpy.txt"))
    assert (parsed.tool, parsed.kind) == ("uv", "conflict")
    assert parsed.causes == [
        Cause("numpy>=1.22.4,<2; python_full_version < '3.11'", parent="pandas", parent_version="2.2.0"),
        Cause("pandas==2.2.0"),
        Cause("numpy==1.21.0"),
    ]
    assert parsed.requested == ["pandas==2.2.0", "numpy==1.21.0"]
    assert parse_error(fixture_text("uv_pandas_color.txt")).causes == parsed.causes  # ANSI colours stripped
    boto = parse_error(fixture_text("uv_boto3.txt"))
    assert boto.requested == ["boto3==1.34.0", "aiobotocore==2.5.0"]  # "you require a and b"
    assert boto.causes[:2] == [
        Cause("botocore>=1.29.76,<1.29.77", parent="aiobotocore", parent_version="2.5.0"),
        Cause("botocore>=1.34.0,<1.35.0", parent="boto3", parent_version="1.34.0"),
    ]
    constraint = parse_error(fixture_text("uv_constraint.txt"))
    assert Cause("urllib3<1.21", constraint=True) in constraint.causes


def test_uv_other_errors() -> None:
    python = parse_error(fixture_text("uv_numpy_python.txt"))
    assert (python.kind, python.python_version) == ("requires-python", "3.10")
    assert python.python_mismatches == [PythonMismatch("numpy", ">=3.11", version="2.3.0")]
    wheel = parse_error(fixture_text("uv_tensorflow.txt"))
    assert wheel.kind == "no-matching-distribution"
    assert wheel.unavailable == [Unavailable("tensorflow==2.15.0", "no-wheel", None, ("cp39", "cp310", "cp311"))]
    assert wheel.python_version == "3.14"
    assert parse_error(fixture_text("uv_not_found.txt")).unavailable == [
        Unavailable("this-package-does-not-exist-pce", "not-found")
    ]
    assert parse_error(fixture_text("uv_no_version.txt")).unavailable == [Unavailable("requests==9.9", "no-version")]
    assert parse_error(fixture_text("uv_only_available.txt")).unavailable == [
        Unavailable("requests<=2.34.2", "only-available")
    ]


def test_success_log_and_unknown_errors() -> None:
    ok = parse_error("Collecting requests\n  Using cached requests-2.32.5-py3-none-any.whl\nWould install requests-2.32.5\n")
    assert ok.kind == "none"
    other = parse_error("ERROR: Could not install packages due to an OSError: [Errno 13] Permission denied\n")
    assert other.kind == "unrecognized"


def test_windows_powershell_pipe() -> None:
    # Real "pip ... 2>&1 | ..." from Windows PowerShell 5.1: stderr lines are wrapped at the console width.
    parsed = parse_error(fixture_text("pip_powershell.txt"))
    assert (parsed.tool, parsed.kind) == ("pip", "conflict")
    assert parsed.requested == ["requests==2.31.0", "urllib3==1.20"]
    assert parsed.causes == parse_error(fixture_text("pip_requests_urllib3.txt")).causes


def test_helpers() -> None:
    assert _pip_requirement('numpy<2 and >=1.22.4; python_version < "3.11"') == 'numpy<2,>=1.22.4; python_version < "3.11"'
    assert _pip_requirement("requests[security, socks]<3 and >=2") == "requests[security,socks]<3,>=2"
    assert _split_triggers("a==1, b<2 and >=1 and c[x, y]==3") == ["a==1", "b<2,>=1", "c[x,y]==3"]
    assert exact_version("numpy==1.21.0") == "1.21.0"
    assert exact_version("numpy==1.*") is None and exact_version("numpy>=1") is None
    assert name_of("Django_Rest-framework>=3") == "django-rest-framework"


def test_installed_package_conflicts() -> None:
    expected = [
        Cause("urllib3<3,>=1.21.1", parent="requests", parent_version="2.31.0"),
        Cause("urllib3==1.20", installed=True),
    ]
    for name in ("pip_installed.txt", "pip_check.txt"):  # after "pip install", and "pip check"
        parsed = parse_error(fixture_text(name))
        assert (parsed.tool, parsed.kind, parsed.causes) == ("pip", "conflict", expected)


def test_build_failure_is_not_a_conflict() -> None:
    parsed = parse_error(fixture_text("pip_build_failed.txt"))
    assert parsed.kind == "unrecognized"
    assert parsed.error_lines[1] == "Cannot import build backend 'setuptools.build_meta:__legacy__'."
