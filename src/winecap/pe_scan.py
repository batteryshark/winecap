"""Portable Executable scanning helpers."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PE_EXTENSIONS = {".dll", ".exe"}
RESOURCE_DIRECTORY = "IMAGE_DIRECTORY_ENTRY_RESOURCE"
MACHINE_ARCHITECTURES = {
    0x014C: "x86",
    0x8664: "x64",
    0xAA64: "ARM64",
}


def get_timestamp(pe: Any) -> tuple[int | None, str | None]:
    """Return raw and formatted COFF timestamp from a PE object."""
    timestamp = pe.FILE_HEADER.TimeDateStamp
    if timestamp == 0:
        return None, None

    try:
        parsed = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (OSError, ValueError):
        return timestamp, f"Invalid (0x{timestamp:08X})"

    return timestamp, parsed.strftime("%Y-%m-%d %H:%M:%S UTC")


def get_architecture(pe: Any) -> str:
    """Return the architecture name for a PE object."""
    machine = pe.FILE_HEADER.Machine
    return MACHINE_ARCHITECTURES.get(machine, f"Unknown (0x{machine:04x})")


def get_version_info(pe: Any) -> dict[str, str]:
    """Extract version strings from a PE object."""
    version_info = {}
    if not hasattr(pe, "FileInfo"):
        return version_info

    for file_info in pe.FileInfo:
        if not isinstance(file_info, Iterable):
            continue

        for info in file_info:
            if hasattr(info, "StringTable"):
                version_info.update(read_string_tables(info.StringTable))

    return version_info


def read_string_tables(string_tables: Iterable[Any]) -> dict[str, str]:
    """Read PE version string tables into a dictionary."""
    version_info = {}
    for string_table in string_tables:
        for raw_key, raw_value in string_table.entries.items():
            key = decode_version_string(raw_key)
            value = decode_version_string(raw_value)
            version_info[key] = value
    return version_info


def decode_version_string(value: bytes | str) -> str:
    """Decode a PE version string key or value."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return value


def get_fixed_version(pe: Any) -> str | None:
    """Return fixed file version from ``VS_FIXEDFILEINFO``."""
    if not hasattr(pe, "VS_FIXEDFILEINFO"):
        return None

    fixed_info = pe.VS_FIXEDFILEINFO[0]
    major = (fixed_info.FileVersionMS >> 16) & 0xFFFF
    minor = fixed_info.FileVersionMS & 0xFFFF
    build = (fixed_info.FileVersionLS >> 16) & 0xFFFF
    revision = fixed_info.FileVersionLS & 0xFFFF
    return f"{major}.{minor}.{build}.{revision}"


def scan_directory(path: Path) -> list[dict[str, Any]]:
    """Scan a directory tree for PE files."""
    pefile = load_pefile()
    results = []

    for file_path in sorted(pe_files(path)):
        results.append(scan_file(file_path, path, pefile))

    return results


def pe_files(path: Path) -> Iterable[Path]:
    """Yield candidate PE files under a directory."""
    for file_path in path.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in PE_EXTENSIONS:
            yield file_path


def scan_file(file_path: Path, root_path: Path, pefile_module: Any) -> dict[str, Any]:
    """Extract PE metadata from one file."""
    try:
        pe = pefile_module.PE(str(file_path), fast_load=True)
        parse_resource_directory(pe, pefile_module)
        result = build_scan_result(file_path, root_path, pe)
        pe.close()
        return result
    except Exception as error:  # pefile raises several parsing-specific exceptions.
        return {"file": str(file_path.relative_to(root_path)), "error": str(error)}


def parse_resource_directory(pe: Any, pefile_module: Any) -> None:
    """Load version resource data when the PE has it."""
    pe.parse_data_directories(
        directories=[pefile_module.DIRECTORY_ENTRY[RESOURCE_DIRECTORY]],
    )


def build_scan_result(file_path: Path, root_path: Path, pe: Any) -> dict[str, Any]:
    """Build the serializable scan result for one parsed PE file."""
    timestamp_raw, timestamp = get_timestamp(pe)
    return {
        "file": str(file_path.relative_to(root_path)),
        "arch": get_architecture(pe),
        "version": get_fixed_version(pe),
        "info": get_version_info(pe),
        "timestamp": timestamp,
        "timestamp_raw": timestamp_raw,
    }


def load_pefile() -> Any:
    """Import pefile with a CLI-friendly error if it is unavailable."""
    try:
        import pefile
    except ImportError as error:
        raise RuntimeError("pefile is required. Install this project with its dependencies.") from error
    return pefile
