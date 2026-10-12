"""Make the independently developed integration packages importable in tests."""

from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
for distribution in (
    "standard-fastapi",
    "standard-aws",
    "standard-http",
    "standard-cache",
    "standard-rdbms",
):
    source_root = REPOSITORY / "packages" / distribution / "src"
    sys.path.insert(0, str(source_root))
