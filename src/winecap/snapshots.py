"""Prefix file snapshots and file/registry diffing."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .registry import diff_registry_snapshots, read_registry_hives

DEFAULT_PREFIX = Path.home() / ".wine_capture"
SNAPSHOTS_DIR = ".snapshots"
HASH_CHUNK_SIZE = 1024 * 64
FILE_BLOCKLIST = (".update-timestamp", ".windows-serial", SNAPSHOTS_DIR)
SNAPSHOT_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")

FileSnapshot = dict[str, dict[str, float | int | str]]
Snapshot = dict[str, Any]
SnapshotDiff = dict[str, Any]


@dataclass(frozen=True)
class SnapshotResult:
    """Metadata about a snapshot that was just written."""

    path: Path
    file_count: int
    registry_key_count: int


def create_snapshot(prefix: Path, name: str) -> SnapshotResult:
    """Capture files and registry hives from a Wine prefix."""
    snapshot_path = snapshot_path_for(prefix, name, create_directory=True)

    files = scan_prefix_files(prefix)
    registry = read_registry_hives(prefix)
    snapshot = {
        "name": name,
        "timestamp": datetime.now().isoformat(),
        "prefix": str(prefix),
        "files": files,
        "registry": registry,
    }

    snapshot_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return SnapshotResult(
        path=snapshot_path,
        file_count=len(files),
        registry_key_count=sum(len(hive) for hive in registry.values()),
    )


def scan_prefix_files(prefix: Path) -> FileSnapshot:
    """Scan ``drive_c`` and return metadata keyed by relative path."""
    drive_c = prefix / "drive_c"
    files: FileSnapshot = {}

    if not drive_c.exists():
        return files

    for file_path in drive_c.rglob("*"):
        if not file_path.is_file():
            continue

        relative_path = file_path.relative_to(drive_c)
        if is_ignored_prefix_file(relative_path):
            continue

        try:
            stat = file_path.stat()
        except OSError:
            continue

        files[str(relative_path)] = {
            "mtime": stat.st_mtime,
            "size": stat.st_size,
            "hash": file_hash(file_path),
        }

    return files


def file_hash(file_path: Path) -> str:
    """Return a SHA-256 hash, or ``error`` when the file cannot be read."""
    sha256 = hashlib.sha256()
    try:
        with file_path.open("rb") as source:
            for chunk in iter(lambda: source.read(HASH_CHUNK_SIZE), b""):
                sha256.update(chunk)
    except OSError:
        return "error"
    return sha256.hexdigest()


def is_ignored_prefix_file(relative_path: Path) -> bool:
    """Return whether a prefix-relative path is internal noise."""
    path_text = relative_path.as_posix()
    return any(blocked in path_text for blocked in FILE_BLOCKLIST)


def load_snapshot(prefix: Path, name: str) -> Snapshot:
    """Load a named snapshot from a prefix."""
    snapshot_path = snapshot_path_for(prefix, name)
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {name}")
    return json.loads(snapshot_path.read_text(encoding="utf-8"))


def list_snapshots(prefix: Path) -> list[dict[str, Any]]:
    """Return summary rows for every snapshot in a prefix."""
    prefix = prefix.expanduser().resolve()
    snapshots_dir = prefix / SNAPSHOTS_DIR
    if snapshots_dir.is_symlink():
        raise ValueError(f"Snapshot directory must not be a symbolic link: {snapshots_dir}")
    if not snapshots_dir.exists():
        return []
    snapshots_dir = snapshots_dir.resolve()
    if snapshots_dir.parent != prefix:
        raise ValueError(f"Snapshot directory escapes the Wine prefix: {snapshots_dir}")

    snapshots = []
    for snapshot_file in sorted(snapshots_dir.glob("*.json")):
        if snapshot_file.is_symlink():
            continue
        snapshots.append(_snapshot_summary(snapshot_file))
    return snapshots


def snapshot_path_for(prefix: Path, name: str, *, create_directory: bool = False) -> Path:
    """Return a contained snapshot path for a safe leaf name."""
    if not SNAPSHOT_NAME_PATTERN.fullmatch(name):
        raise ValueError(
            "Snapshot names must be 1-64 characters and contain only letters, "
            "numbers, dots, underscores, or hyphens."
        )

    prefix = prefix.expanduser().resolve()
    snapshots_dir = prefix / SNAPSHOTS_DIR
    if snapshots_dir.is_symlink():
        raise ValueError(f"Snapshot directory must not be a symbolic link: {snapshots_dir}")
    if create_directory:
        snapshots_dir.mkdir(exist_ok=True)

    resolved_dir = snapshots_dir.resolve()
    if resolved_dir.parent != prefix:
        raise ValueError(f"Snapshot directory escapes the Wine prefix: {snapshots_dir}")

    snapshot_path = resolved_dir / f"{name}.json"
    if snapshot_path.is_symlink():
        raise ValueError(f"Snapshot file must not be a symbolic link: {snapshot_path}")
    resolved_path = snapshot_path.resolve()
    if resolved_path.parent != resolved_dir:
        raise ValueError(f"Snapshot path escapes the snapshot directory: {name}")
    return resolved_path


def diff_snapshots(before: Snapshot, after: Snapshot) -> SnapshotDiff:
    """Compare two snapshots."""
    before_files = before.get("files", {})
    after_files = after.get("files", {})
    file_diff = diff_files(before_files, after_files)
    registry_diff = diff_registry_snapshots(
        before.get("registry", {}),
        after.get("registry", {}),
    )

    return {"files": file_diff, "registry": registry_diff}


def diff_files(before: FileSnapshot, after: FileSnapshot) -> dict[str, Any]:
    """Compare file metadata by relative path and content hash."""
    added = {}
    modified = {}
    removed = []

    for path, info in after.items():
        if path not in before:
            added[path] = info
        elif before[path].get("hash") != info.get("hash"):
            modified[path] = info

    for path in before:
        if path not in after:
            removed.append(path)

    return {"added": added, "modified": modified, "removed": removed}


def _snapshot_summary(snapshot_file: Path) -> dict[str, Any]:
    try:
        data = json.loads(snapshot_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"name": snapshot_file.stem, "timestamp": "error", "files": 0, "keys": 0}

    return {
        "name": data.get("name", snapshot_file.stem),
        "timestamp": data.get("timestamp", "unknown"),
        "files": len(data.get("files", {})),
        "keys": sum(len(hive) for hive in data.get("registry", {}).values()),
    }
