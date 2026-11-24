"""Allow ``python -m pip_conflict_explainer``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
