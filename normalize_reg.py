#!/usr/bin/env python3
"""Compatibility launcher for the ``normalize-reg`` CLI."""

from __future__ import annotations

import sys
from pathlib import Path


def _prefer_src_layout() -> None:
    src_path = Path(__file__).resolve().parent / "src"
    if src_path.exists():
        sys.path.insert(0, str(src_path))


_prefer_src_layout()

from winecap.normalizer_cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
