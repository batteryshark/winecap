"""Command-line interface for PE metadata scanning."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .pe_scan import scan_directory

IMPORTANT_VERSION_KEYS = (
    "ProductName",
    "ProductVersion",
    "FileDescription",
    "FileVersion",
    "CompanyName",
    "OriginalFilename",
)


def main(argv: list[str] | None = None) -> int:
    """Run the ``scan-pe`` CLI."""
    parser = argparse.ArgumentParser(description="Scan a directory for DLL/EXE metadata.")
    parser.add_argument("directory", help="Directory to scan")
    args = parser.parse_args(argv)

    target_dir = Path(args.directory)
    if not target_dir.is_dir():
        print(f"Error: {target_dir} is not a directory")
        return 1

    try:
        results = scan_directory(target_dir)
    except RuntimeError as error:
        print(f"Error: {error}")
        return 1

    print_results(target_dir, results)
    return 0


def print_results(target_dir: Path, results: list[dict[str, Any]]) -> None:
    """Print scan results in the historical human-readable format."""
    print(f"Scanning: {target_dir}\n")
    print("=" * 80)

    for result in results:
        print_result(result)

    print("\n" + "=" * 80)
    print(f"Total files scanned: {len(results)}")


def print_result(result: dict[str, Any]) -> None:
    """Print one PE scan result."""
    print(f"\nFile: {result['file']}")
    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return

    print(f"  Architecture: {result['arch']}")
    if result.get("timestamp"):
        print(f"  PE Timestamp: {result['timestamp']} (0x{result['timestamp_raw']:08X})")
    if result.get("version"):
        print(f"  File Version: {result['version']}")
    print_version_info(result.get("info", {}))


def print_version_info(version_info: dict[str, str]) -> None:
    """Print version strings with stable ordering."""
    for key in IMPORTANT_VERSION_KEYS:
        if version_info.get(key):
            print(f"  {key}: {version_info[key]}")

    for key, value in version_info.items():
        if key not in IMPORTANT_VERSION_KEYS and value:
            print(f"  {key}: {value}")


if __name__ == "__main__":
    raise SystemExit(main())
