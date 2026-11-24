"""Record the trimmed PyPI JSON responses that the offline tests use.

    python scripts/record_pypi_fixtures.py

Read-only: it only downloads ``https://pypi.org/pypi/<name>/json`` and
``/pypi/<name>/<version>/json`` and keeps a few versions and files of each.
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "pypi"
KEEP = {
    "pandas": ["1.5.3", "2.0.3", "2.1.0", "2.1.4", "2.2.0", "2.2.3", "2.3.3"],
    "numpy": ["1.21.0", "1.21.6", "1.22.4", "1.24.4", "1.26.4", "2.0.2", "2.2.6", "2.3.0", "2.3.5"],
    "requests": ["2.15.1", "2.16.0", "2.20.0", "2.28.2", "2.31.0", "2.32.5", "2.34.2"],
    "urllib3": ["1.20", "1.21.1", "1.26.20", "2.0.7", "2.5.0", "2.8.0"],
    "boto3": ["1.26.75", "1.26.76", "1.26.77", "1.34.0", "1.35.0"],
    "botocore": ["1.29.75", "1.29.76", "1.29.77", "1.34.0", "1.34.70", "1.34.162", "1.35.0"],
    "aiobotocore": ["2.5.0", "2.13.3", "2.14.0"],
    "tensorflow": ["2.15.0", "2.20.0", "2.22.0rc1"],
}
FILES = re.compile(r"(win_amd64|manylinux[^-]*x86_64|none-any)\.whl$|\.tar\.gz$|\.zip$")
FILE_KEYS = ("filename", "packagetype", "requires_python", "yanked")
INFO_KEYS = ("name", "version", "requires_python", "requires_dist")


def get(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "pip-conflict-explainer fixture recorder"})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return json.load(response)


def write(name: str, data: dict) -> None:
    (OUT / f"{name}.json").write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, versions in KEEP.items():
        doc = get(f"https://pypi.org/pypi/{name}/json")
        releases = {
            version: [{key: f.get(key) for key in FILE_KEYS} for f in doc["releases"][version] if FILES.search(f["filename"])]
            for version in versions
        }
        write(name, {"info": {"name": doc["info"]["name"]}, "releases": releases})
        for version in versions:
            info = get(f"https://pypi.org/pypi/{name}/{version}/json")["info"]
            write(f"{name}-{version}", {"info": {key: info.get(key) for key in INFO_KEYS}})
        print(f"recorded {name}: {', '.join(versions)}")


if __name__ == "__main__":
    main()
