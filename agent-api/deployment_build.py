#!/usr/bin/env python3
"""Compatibility wrapper for edition-based deployment builds.

Prefer calling `tools/build_edition.py` directly:

    python tools/build_edition.py personal
    python tools/build_edition.py sentero
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_EDITION = "personal"


def main() -> int:
    edition = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EDITION
    if len(sys.argv) > 2:
        print("Usage: python deployment_build.py [personal|sentero]", file=sys.stderr)
        return 2
    print(f"deployment_build.py ist ein Compatibility Wrapper. Baue Edition: {edition}")
    return subprocess.call([sys.executable, str(ROOT / "tools" / "build_edition.py"), edition], cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
