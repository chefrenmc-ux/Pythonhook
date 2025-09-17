#!/usr/bin/env python3
# Aurora Polaris 2025. All rights reserved.
"""Convenience test runner for the project."""
from __future__ import annotations

import subprocess
import sys


def main() -> int:
    args = [sys.executable, "-m", "pytest", "-q"]
    return subprocess.call(args)


if __name__ == "__main__":
    raise SystemExit(main())
