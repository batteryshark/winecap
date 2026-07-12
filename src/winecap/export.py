"""Export changed prefix files and registry keys."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .registry import RegistryDiff, write_registry_export


@dataclass(frozen=True)
class ExportResult:
    """Counts from an export operation."""

    files_exported: int
    registry_keys_exported: int


def export_diff(prefix: Path, diff: dict[str, Any], output_dir: Path) -> ExportResult:
    """Export changed files plus added/modified registry keys."""
    output_dir.mkdir(parents=True, exist_ok=True)
    files_exported = export_changed_files(prefix, diff, output_dir)
    registry_diff: RegistryDiff = diff.get("registry", {})
    keys_exported = write_registry_export(output_dir, registry_diff)
    return ExportResult(files_exported, keys_exported)


def export_changed_files(prefix: Path, diff: dict[str, Any], output_dir: Path) -> int:
    """Copy added and modified files from ``drive_c`` into an output tree."""
    drive_c = prefix / "drive_c"
    files_exported = 0

    for change_type in ("added", "modified"):
        for relative_path in diff.get("files", {}).get(change_type, {}):
            source = drive_c / relative_path
            destination = output_dir / relative_path

            if not source.exists():
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            files_exported += 1

    return files_exported
