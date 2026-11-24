"""Explanations and fixes end to end, with PyPI answered from recorded fixtures."""

from __future__ import annotations

from helpers import FakeIndex, fixture_text, recorded_index

from pip_conflict_explainer import explain, render_text
from pip_conflict_explainer.pypi import NetworkError


def summaries(report) -> list[str]:
    return [fix.summary for fix in report.fixes]


def test_pandas_numpy_python310() -> None:
    report = explain(fixture_text("pip_pandas_numpy.txt"), platform="windows", index=recorded_index())
    assert report.target["python"] == "3.10"  # detected from the wheel names pip downloaded
    assert report.explanation == [
        'You pinned numpy==1.21.0, but pandas 2.2.0 needs numpy>=1.22.4,<2 (for python_version < "3.11").',
        "numpy 1.21.0 is too old for pandas 2.2.0.",
        "numpy 1.21.0 has no wheel for Python 3.10 on windows, so pip has to build it from source.",
    ]
    assert summaries(report) == [
        "relax your pin `numpy==1.21.0` -> `numpy>=1.22.4,<2` (newest that fits: 1.26.4)",
        "keep numpy 1.21.0 and use `pandas<=2.0.3`",
        "change `numpy==1.21.0` -> `numpy>=1.22.4` and `pandas==2.2.0` -> `pandas==2.3.3` "
        "(newest that fits: numpy 2.2.6, pandas 2.3.3)",
    ]
    assert report.fixes[0].requirements == ["numpy>=1.22.4,<2", "pandas==2.2.0"]
    assert report.fixes[1].notes == ["no wheel for Python 3.10 on windows: numpy 1.21.0 (pip would build from source)"]
    assert report.exit_code == 0
    assert 'pip install --dry-run "numpy>=1.22.4,<2" "pandas==2.2.0"' in render_text(report)


def test_requests_urllib3_and_constraint() -> None:
    report = explain(fixture_text("pip_requests_urllib3.txt"), platform="windows", index=recorded_index())
    assert summaries(report) == [
        "relax your pin `urllib3==1.20` -> `urllib3>=1.21.1,<3` (newest that fits: 2.8.0)",
        "keep urllib3 1.20 and use `requests<=2.15.1`",
        "change `urllib3==1.20` -> `urllib3>=1.26,<3` and `requests==2.31.0` -> `requests==2.34.2` "
        "(newest that fits: urllib3 2.8.0, requests 2.34.2)",
    ]
    constraint = explain(fixture_text("pip_constraint.txt"), platform="windows", index=recorded_index())
    assert summaries(constraint)[:2] == [
        "change your constraint `urllib3<1.21` -> `urllib3>=1.21.1,<3` (newest that fits: 2.8.0)",
        "keep your constraint urllib3<1.21 and use `requests<=2.15.1`",
    ]


def test_transitive_conflict_boto3() -> None:
    report = explain(fixture_text("pip_boto3.txt"), python="3.14", platform="windows", index=recorded_index())
    assert summaries(report) == [
        "upgrade your pin `aiobotocore==2.5.0` -> `aiobotocore==2.13.3`",
        "keep aiobotocore 2.5.0 and use `boto3<=1.26.76`",
        "change `boto3==1.34.0` -> `boto3==1.35.0` and `aiobotocore==2.5.0` -> `aiobotocore==2.14.0` "
        "(newest that fits: boto3 1.35.0, aiobotocore 2.14.0)",
    ]
    assert report.fixes[0].pins == {"aiobotocore": "2.13.3", "boto3": "1.34.0", "botocore": "1.34.162"}


def test_uv_output_gets_the_same_fixes() -> None:
    report = explain(fixture_text("uv_pandas_numpy.txt"), python="3.10", platform="windows", index=recorded_index())
    assert summaries(report)[:2] == [
        "relax your pin `numpy==1.21.0` -> `numpy>=1.22.4,<2` (newest that fits: 1.26.4)",
        "keep numpy 1.21.0 and use `pandas<=2.0.3`",
    ]


def test_python_version_is_the_blocker() -> None:
    report = explain(fixture_text("pip_numpy_python.txt"), platform="windows", index=recorded_index())
    assert report.target["python"] == "3.10"  # inferred from the "Ignored ... Requires-Python" line
    assert report.explanation[0] == "numpy 2.3.0 needs Python >=3.11; you have 3.10."
    assert summaries(report) == ["use `numpy<=2.2.6` instead of `numpy==2.3.0`"]
    assert report.fixes[0].notes == ["numpy 2.3.0 needs Python >=3.11; you have 3.10."]


def test_no_wheel_for_python_and_pre_releases() -> None:
    text = fixture_text("pip_tensorflow.txt")
    report = explain(text, python="3.14", platform="windows", index=recorded_index())
    assert report.fixes == [] and report.exit_code == 1
    assert report.explanation[1:] == [
        "tensorflow 2.15.0 has no wheel for Python 3.14 on windows (its wheels are for Python 3.9, 3.10 and 3.11).",
        "Only pre-releases of tensorflow support Python 3.14 on windows so far (newest: 2.22.0rc1); "
        "add --pre to consider them.",
        "To keep tensorflow 2.15.0, use Python 3.9, 3.10 or 3.11.",
    ]
    pre = explain(text, python="3.14", platform="windows", pre=True, index=recorded_index())
    assert summaries(pre) == ["upgrade your pin `tensorflow==2.15.0` -> `tensorflow==2.22.0rc1`"]


def test_missing_package_and_missing_version() -> None:
    missing = explain(fixture_text("pip_not_found.txt"), python="3.14", platform="windows", index=recorded_index())
    assert missing.explanation[-1].startswith("this-package-does-not-exist-pce does not exist on PyPI.")
    assert missing.exit_code == 1 and missing.notes == []
    version = explain(fixture_text("pip_no_version.txt"), python="3.14", platform="windows", index=recorded_index())
    assert version.explanation == ["No requests release matches `requests==9.9`. The newest version pip could see is 2.34.2."]
    assert summaries(version) == ["use `requests==2.34.2` instead of `requests==9.9`"]


def test_offline_mode_explains_only() -> None:
    report = explain(fixture_text("pip_pandas_numpy.txt"), offline=True, index=FakeIndex({}))
    assert report.fixes == [] and report.exit_code == 1
    assert report.notes[-1].startswith("Offline mode: explanation only.")
    assert report.notes[0].startswith('pip also listed numpy under "no matching distributions')


def test_budget_stops_the_search_gracefully() -> None:
    report = explain(fixture_text("pip_pandas_numpy.txt"), platform="windows", index=recorded_index(max_requests=3))
    assert report.exit_code == 1
    assert any("PyPI requests" in note for note in report.notes)


def test_conflict_that_cannot_be_reproduced() -> None:
    index = FakeIndex({"numpy": {"1.21.0": {}}, "pandas": {"2.2.0": {"deps": ["numpy>=1.20"]}}})
    report = explain(fixture_text("pip_pandas_numpy.txt"), platform="windows", index=index)
    assert report.fixes == []
    assert report.notes[-1].startswith("With PyPI data for Python 3.10 on windows these requirements look compatible")


def test_no_combination_works() -> None:
    index = FakeIndex(
        {
            "numpy": {"1.21.0": {}, "1.26.4": {}},
            "pandas": {"2.2.0": {"deps": ["numpy>=1.22.4,<2", "numpy<1.22"]}, "2.1.0": {"deps": ["numpy>=3"]}},
        }
    )
    report = explain(fixture_text("pip_pandas_numpy.txt"), platform="windows", index=index)
    assert report.fixes == [] and report.exit_code == 1
    assert report.notes[-1] == "No combination of versions of numpy and pandas works for Python 3.10 on windows (checked on PyPI)."


def test_installed_conflict_and_build_failure() -> None:
    report = explain(fixture_text("pip_check.txt"), python="3.14", platform="windows", index=recorded_index())
    assert report.explanation[0] == "You have urllib3 1.20 installed, but requests 2.31.0 needs urllib3>=1.21.1,<3."
    assert summaries(report)[0] == "use `urllib3>=1.21.1,<3` instead of urllib3 1.20 (newest that fits: 2.8.0)"
    build = explain(fixture_text("pip_build_failed.txt"), offline=True)
    assert build.exit_code == 2
    assert build.explanation[0].startswith("pip failed while building numpy from source.")


def test_network_failure_still_explains() -> None:
    class Down(FakeIndex):
        def releases(self, name: str):
            raise NetworkError("could not fetch https://pypi.org/pypi/numpy/json: timed out")

    report = explain(fixture_text("pip_pandas_numpy.txt"), platform="windows", index=Down({}))
    assert report.explanation[0].startswith("You pinned numpy==1.21.0")
    assert report.notes[-1].startswith("Could not look up versions on PyPI")
    assert report.exit_code == 1
