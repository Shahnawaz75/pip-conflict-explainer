"""pip-conflict-explainer: understand pip/uv dependency conflicts and get versions that work.

>>> from pip_conflict_explainer import explain, check
>>> report = explain(open("error.txt").read())      # doctest: +SKIP
>>> print(report.fixes[0].summary)                   # doctest: +SKIP
"""

__version__ = "0.1.0"

from .checker import check  # noqa: E402
from .core import explain  # noqa: E402
from .models import Cause, Change, Fix, ParsedError, Report, UsageError  # noqa: E402
from .parser import parse_error  # noqa: E402
from .render import render_text  # noqa: E402

__all__ = [
    "Cause",
    "Change",
    "Fix",
    "ParsedError",
    "Report",
    "UsageError",
    "__version__",
    "check",
    "explain",
    "parse_error",
    "render_text",
]
