"""Read pip's and uv's dependency-resolution errors into a :class:`ParsedError`.

Only the text is used here; nothing is looked up on the network.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

from .models import Cause, ParsedError, PythonMismatch, Unavailable

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
# "ERROR: ..." and the "python.exe : ERROR: ..." form PowerShell gives for stderr.
_PIP_PREFIX = re.compile(r"^(?:\S+ : )?(?:ERROR|INFO|WARNING): ")
_NAME = r"[A-Za-z0-9][A-Za-z0-9._-]*"

_HEADLINE = re.compile(
    r"Cannot install (?P<what>.+?) because these package versions have conflicting dependencies"
)
_USER = re.compile(r"^The user requested (?P<constraint>\(constraint\) )?(?P<req>.+)$")
_DEPENDS = re.compile(rf"^(?P<parent>{_NAME}(?:\[[^\]]+\])?) (?P<version>\S+) depends on (?P<req>.+)$")
# "pip install" after the fact and "pip check": X 1.0 requires Y<2, but you have Y 2.1 ...
_INSTALLED = re.compile(
    rf"^(?P<parent>{_NAME}) (?P<version>\S+) (?:requires|has requirement) (?P<req>.+?), "
    rf"but you have (?P<dep>{_NAME}) (?P<have>[^\s,]+?)(?: which is incompatible)?\.$"
)
_COLLECTING = re.compile(r"^Collecting (?P<req>.+?)(?:\s+\(from (?P<src>.*)\))?$")
_ONE_PYTHON = re.compile(
    r"Package '(?P<pkg>[^']+)' requires a different Python: (?P<py>\S+) not in '(?P<spec>[^']*)'"
)
_MANY_PYTHON = re.compile(r"Packages require a different Python\. (?P<py>\S+) not in:")
_MANY_PYTHON_ITEM = re.compile(r"^'(?P<spec>[^']*)' \(required by (?P<pkg>\S+) (?P<ver>[^\s)]+)")
_IGNORED_PYTHON = re.compile(
    r"Ignored the following versions that require a different python version: (?P<items>.+)$"
)
_IGNORED_YANKED = re.compile(r"Ignored the following yanked versions: (?P<items>.+)$")
_COULD_NOT_FIND = re.compile(
    r"Could not find a (?:final )?version that satisfies the requirement (?P<req>.+?)"
    r" \(from versions: (?P<versions>[^)]*)\)"
)
_NO_MATCHING = re.compile(r"No matching distribution found for (?P<req>.+?)\s*$")
_FROM_SUFFIX = re.compile(r"\s+\(from [^()]*\)$")
_WHEEL = re.compile(r"-(?P<py>cp3\d{1,2})-(?P<abi>cp3\d{1,2}t?)-(?P<plat>[A-Za-z0-9_.]+?)\.whl")

_UV_MARKER = "No solution found when resolving dependencies"
_UV_FACTS = re.compile(r"[Bb]ecause (?P<facts>.+?), we can conclude that")
_UV_DEPENDS = re.compile(r"^(?P<parent>.+?) depends? on (?P<req>.+)$")
_UV_REQUIRE = re.compile(
    r"^(?:you require|your project (?:depends on|requires)|your workspace requires) (?P<req>.+)$"
)
_UV_NO_VERSION = re.compile(r"^there (?:is|are) no versions? of (?P<req>.+)$")
_UV_NOT_FOUND = re.compile(r"^(?P<name>\S+) was not found in the (?:package registry|provided package locations)")
_UV_ONLY = re.compile(r"^only (?P<req>.+?) (?:is|are) available$")
_UV_NO_WHEEL = re.compile(r"^(?P<req>\S+) has no (?:usable )?wheels? with a matching (?P<what>.+?)(?: \(e\.g\.,.*\))?$")
_UV_PYTHON = re.compile(r"^the (?:current|requested) Python version \((?P<py>[^)]+)\) does not satisfy Python")
_UV_ENV = re.compile(r"Using (?:C?Python )?(?P<py>3\.\d+(?:\.\d+)?) environment at")
_UV_HINT_TAGS = re.compile(
    r"only found wheels for `(?P<pkg>[^`]+)` \(v(?P<ver>[^)]+)\) with the following [^:]+: (?P<tags>.+)$"
)
_UV_HINT_PY = re.compile(r"You require (?:CPython|Python) (?P<py>3\.\d+)")


def _unwrap(text: str) -> str:
    """Re-join lines that Windows PowerShell wrapped at the console width.

    PowerShell 5.1 prints a native command's stderr (``2>&1``) as error records
    broken at the console width; the broken line keeps its trailing space.
    """
    lines: list[str] = []
    for line in text.split("\n"):
        if lines and len(lines[-1]) >= 60 and lines[-1].endswith(" ") and line.strip():
            lines[-1] += line
        else:
            lines.append(line)
    return "\n".join(lines)


def parse_error(text: str) -> ParsedError:
    """Parse pip or uv output (the whole log is fine) into a :class:`ParsedError`."""
    text = _unwrap(_ANSI.sub("", text.lstrip("﻿")).replace("\r\n", "\n").replace("\r", "\n"))
    result = ParsedError()
    if _UV_MARKER in text:
        _parse_uv(text, result)
    else:
        _parse_pip(text.split("\n"), result)
    _detect_target(text, result)
    result.error_lines = [
        re.sub(r"^[^\x00-\x7f]+\s*", "", line.strip())[:300]  # drop box-drawing prefixes such as the cross
        for line in text.split("\n")
        if re.match(r"^\s*(?:\S+ : )?(?:ERROR:|error:|×)", line)
    ][:20]
    result.kind = _decide_kind(result)
    return result


def name_of(requirement: str) -> str:
    """Canonical project name of a requirement string (best effort)."""
    try:
        return canonicalize_name(Requirement(requirement).name)
    except InvalidRequirement:
        match = re.match(_NAME, requirement.strip())
        return canonicalize_name(match.group(0)) if match else requirement.strip().lower()


def exact_version(requirement: str) -> str | None:
    """Return ``V`` if *requirement* is an exact ``name==V`` pin, else ``None``."""
    try:
        specs = list(Requirement(requirement).specifier)
    except InvalidRequirement:
        return None
    if len(specs) == 1 and specs[0].operator in ("==", "===") and "*" not in specs[0].version:
        return specs[0].version
    return None


def _pip_requirement(text: str) -> str:
    """Undo pip's "numpy<2 and >=1.22.4" formatting back into PEP 508."""
    head, sep, marker = text.partition(";")
    head = head.strip().replace(" and ", ",").replace(", ", ",")
    return f"{head}; {marker.strip()}" if sep else head


def _split_triggers(text: str) -> list[str]:
    """Split "a, b and c" from pip's "Cannot install a, b and c" headline."""
    items: list[str] = []
    for part in re.split(r", | and ", text):
        if items and part and (part[0] in "<>=!~" or items[-1].count("[") > items[-1].count("]")):
            items[-1] += "," + part
        elif part:
            items.append(part)
    return items


def _add_unique(target: list[str], values: Iterable[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def _add_cause(result: ParsedError, cause: Cause) -> None:
    if cause not in result.causes:
        result.causes.append(cause)


def _add_unavailable(result: ParsedError, item: Unavailable) -> None:
    for i, old in enumerate(result.unavailable):
        if old.requirement == item.requirement:
            if old.available is None and item.available is not None:
                result.unavailable[i] = item
            return
    result.unavailable.append(item)


def _parse_pip(lines: list[str], result: ParsedError) -> None:
    section: str | None = None
    pending_python: list[tuple[str, str]] = []
    pending_yanked: list[str] = []
    many_python: str | None = None
    for raw in lines:
        line = _PIP_PREFIX.sub("", raw.strip())
        if not line:
            section = None
            continue
        if match := _HEADLINE.search(line):
            result.tool = "pip"
            _add_unique(result.requested, _split_triggers(match["what"]))
            continue
        if line.startswith("The conflict is caused by"):
            section = "causes"
            continue
        if line.startswith("Additionally, some packages in these conflicts"):
            section = "extra"
            continue
        if section == "causes":
            if match := _USER.match(line):
                _add_cause(result, Cause(_pip_requirement(match["req"]), constraint=bool(match["constraint"])))
            elif match := _DEPENDS.match(line):
                cause = Cause(_pip_requirement(match["req"]), parent=match["parent"], parent_version=match["version"])
                _add_cause(result, cause)
            continue
        if section == "extra":
            _add_unique(result.no_candidates, [line])
            continue
        if match := _INSTALLED.match(line):
            result.tool = "pip"
            _add_cause(result, Cause(match["req"], parent=match["parent"], parent_version=match["version"]))
            _add_cause(result, Cause(f"{match['dep']}=={match['have']}", installed=True))
            continue
        if match := _COLLECTING.match(line):
            if match["src"] is None or match["src"].startswith(("-r ", "--requirement")):
                _add_unique(result.requested, [match["req"]])
            continue
        if match := _ONE_PYTHON.search(line):
            result.tool = "pip"
            result.python_mismatches.append(PythonMismatch(match["pkg"], match["spec"], python=match["py"]))
            result.python_version = match["py"]
        elif match := _MANY_PYTHON.search(line):
            result.tool = "pip"
            many_python = result.python_version = match["py"]
        elif many_python and (match := _MANY_PYTHON_ITEM.match(line)):
            mismatch = PythonMismatch(match["pkg"], match["spec"], version=match["ver"], python=many_python)
            result.python_mismatches.append(mismatch)
        elif match := _IGNORED_PYTHON.search(line):
            for item in match["items"].split("; "):
                version, _, spec = item.partition(" Requires-Python ")
                if spec:
                    pending_python.append((version.strip(), spec.strip()))
        elif match := _IGNORED_YANKED.search(line):
            pending_yanked = [v.strip() for v in match["items"].split(",") if v.strip() not in ("", "none")]
        elif match := _COULD_NOT_FIND.search(line):
            result.tool = "pip"
            requirement = _FROM_SUFFIX.sub("", match["req"].strip())
            versions = tuple(v.strip() for v in match["versions"].split(",") if v.strip() not in ("", "none"))
            _add_unavailable(result, Unavailable(requirement, available=versions))
            if not _FROM_SUFFIX.search(match["req"].strip()):
                _add_unique(result.requested, [requirement])
            name = name_of(requirement)
            for version, spec in pending_python:
                result.python_mismatches.append(PythonMismatch(name, spec, version=version))
            _add_unique(result.yanked, pending_yanked)
            pending_python, pending_yanked = [], []
        elif match := _NO_MATCHING.search(line):
            result.tool = "pip"
            _add_unavailable(result, Unavailable(_FROM_SUFFIX.sub("", match["req"].strip())))


def _parse_uv(text: str, result: ParsedError) -> None:
    result.tool = "uv"
    body: list[str] = []
    hints: list[str] = []
    for line in text[text.find(_UV_MARKER) :].split("\n")[1:]:
        # Drop box-drawing characters (and their mangled forms) and the labels.
        clean = re.sub(r"^[^A-Za-z0-9(]+", "", line.strip())
        clean = re.sub(r"^(?:cause|error|Caused by):\s*", "", clean)
        if clean.lower().startswith("hint:"):
            hints.append(clean[5:].strip())
        elif hints:
            if clean:
                hints[-1] += " " + clean
        else:
            body.append(clean)
    flat = " ".join(" ".join(body).split())
    markers: list[str] = []

    def keep_marker(match: re.Match[str]) -> str:
        markers.append(match.group(1))
        return f"@@{len(markers) - 1}@@"

    flat = re.sub(r"\{([^{}]*)\}", keep_marker, flat)
    for match in _UV_FACTS.finditer(flat):
        previous: str | None = None
        for token in match["facts"].split(" and "):
            token = re.sub(r"^we know (?:from \(\d+\) )?that ", "", token.strip()).rstrip(".,")
            previous = _uv_fact(token, previous, markers, result)
    for hint in hints:
        if found := _UV_HINT_TAGS.search(hint):
            tags = tuple(re.findall(r"`([^`]+)`", found["tags"]))
            for i, item in enumerate(result.unavailable):
                if name_of(item.requirement) == canonicalize_name(found["pkg"]):
                    result.unavailable[i] = Unavailable(item.requirement, item.reason, item.available, tags)
        if found := _UV_HINT_PY.search(hint):
            result.python_version = result.python_version or found["py"]


def _uv_requirement(text: str, markers: list[str]) -> str:
    text = text.strip().strip("`'\"").rstrip(".,;:")
    found = [markers[int(i)] for i in re.findall(r"@@(\d+)@@", text)]
    text = re.sub(r"@@\d+@@", "", text)
    return f"{text}; {found[0]}" if found else text


def _uv_parent(text: str) -> tuple[str, str | None, str | None]:
    text = re.sub(r"@@\d+@@", "", text).strip()
    if text.startswith("all versions of "):
        return text[len("all versions of ") :], None, None
    match = re.match(rf"^(?P<name>{_NAME}(?:\[[^\]]*\])?)(?P<spec>.*)$", text)
    if not match:
        return text, None, None
    spec = match["spec"].strip()
    if re.fullmatch(r"==[^,*|\s]+", spec):
        return match["name"], spec[2:], None
    return match["name"], None, spec or None


def _is_requirement(text: str) -> bool:
    try:
        return canonicalize_name(Requirement(text).name) != "python"
    except InvalidRequirement:
        return False


def _uv_fact(token: str, previous: str | None, markers: list[str], result: ParsedError) -> str | None:
    """Record one uv fact; return its type so "you require a and b" can continue."""
    if match := _UV_PYTHON.match(token):
        result.python_version = _short_python(match["py"])
        return "python"
    if match := _UV_REQUIRE.match(token):
        requirement = _uv_requirement(match["req"], markers)
        _add_cause(result, Cause(requirement))
        _add_unique(result.requested, [requirement])
        return "root"
    if match := _UV_DEPENDS.match(token):
        name, version, spec = _uv_parent(match["parent"])
        requirement = _uv_requirement(match["req"], markers)
        if name_of(requirement) == "python":
            result.python_mismatches.append(PythonMismatch(name, requirement[len("Python") :].strip(), version=version))
        else:
            _add_cause(result, Cause(requirement, parent=name, parent_version=version, parent_spec=spec))
        return "depends"
    for pattern, reason in ((_UV_NO_VERSION, "no-version"), (_UV_ONLY, "only-available"), (_UV_NO_WHEEL, "no-wheel")):
        if match := pattern.match(token):
            _add_unavailable(result, Unavailable(_uv_requirement(match["req"], markers), reason=reason))
            return "other"
    if match := _UV_NOT_FOUND.match(token):
        _add_unavailable(result, Unavailable(match["name"].strip("`"), reason="not-found"))
        return "other"
    requirement = _uv_requirement(token, markers)
    if _is_requirement(requirement):
        # A bare range after "you require x and" is another requirement; after
        # anything else it is a constraint (that is how uv prints -c entries).
        _add_cause(result, Cause(requirement, constraint=previous != "root"))
        if previous == "root":
            _add_unique(result.requested, [requirement])
    return previous


def _short_python(value: str) -> str:
    match = re.search(r"3\.\d+(?:\.\d+)?", value)
    return match.group(0) if match else value


def _detect_target(text: str, result: ParsedError) -> None:
    """Guess the Python version and wheel platform the error came from."""
    if match := _UV_ENV.search(text):
        result.python_version = result.python_version or match["py"]
    wheels = [(m["py"], m["plat"]) for m in _WHEEL.finditer(text) if m["py"] == m["abi"]]
    if wheels:
        python, _ = Counter(w[0] for w in wheels).most_common(1)[0]
        result.python_version = result.python_version or f"3.{python[3:]}"
        result.platform_tag = Counter(w[1] for w in wheels).most_common(1)[0][0]


def _decide_kind(result: ParsedError) -> str:
    if result.tool == "unknown" and not (result.causes or result.unavailable or result.python_mismatches):
        return "unrecognized" if result.error_lines else "none"
    if any(cause.parent for cause in result.causes) or (result.tool == "pip" and result.causes):
        return "conflict"
    pinned = {(name_of(u.requirement), exact_version(u.requirement)) for u in result.unavailable}
    direct = [m for m in result.python_mismatches if m.python or result.tool == "uv"]
    if direct or any((canonicalize_name(m.package or ""), m.version) in pinned for m in result.python_mismatches):
        return "requires-python"
    if result.unavailable:
        return "no-matching-distribution"
    return "unrecognized" if result.error_lines else "none"
