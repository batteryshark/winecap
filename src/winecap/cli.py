"""Command-line interface for Wine prefix capture."""

from __future__ import annotations

import argparse
from pathlib import Path

from .export import export_diff
from .registry import registry_change_count
from .review import CATEGORY_ORDER, categorize_changes, interactive_review
from .snapshots import DEFAULT_PREFIX, create_snapshot, diff_snapshots, list_snapshots, load_snapshot
from .wine import PrefixInitOptions, initialize_prefix, run_wine, wait_for_wineserver


def main(argv: list[str] | None = None) -> int:
    """Run the ``winecap`` CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    return args.handler(args)


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        description="Capture and review installer changes in a Wine prefix.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    init_parser = subparsers.add_parser("init", help="Initialize a new Wine prefix")
    add_prefix_argument(init_parser)
    init_parser.add_argument("--arch", default="win64", choices=("win64", "win32"))
    init_parser.add_argument(
        "--winver",
        default="win10",
        choices=("win10", "win81", "win8", "win7", "vista", "winxp"),
    )
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(handler=cmd_init)

    snapshot_parser = subparsers.add_parser("snapshot", help="Take a named snapshot")
    snapshot_parser.add_argument("name")
    add_prefix_argument(snapshot_parser)
    snapshot_parser.set_defaults(handler=cmd_snapshot)

    list_parser = subparsers.add_parser("list", help="List snapshots")
    add_prefix_argument(list_parser)
    list_parser.set_defaults(handler=cmd_list)

    diff_parser = subparsers.add_parser("diff", help="Compare two snapshots")
    diff_parser.add_argument("snapshot_a")
    diff_parser.add_argument("snapshot_b")
    add_prefix_argument(diff_parser)
    diff_parser.set_defaults(handler=cmd_diff)

    export_parser = subparsers.add_parser("export", help="Export a reviewed diff")
    export_parser.add_argument("snapshot_a")
    export_parser.add_argument("snapshot_b")
    export_parser.add_argument("output_dir")
    add_prefix_argument(export_parser)
    export_parser.add_argument("--no-review", action="store_true", help="Skip interactive review")
    export_parser.set_defaults(handler=cmd_export)

    run_parser = subparsers.add_parser("run", help="Run an executable inside the prefix")
    add_prefix_argument(run_parser)
    run_parser.add_argument("executable")
    run_parser.add_argument("args", nargs=argparse.REMAINDER)
    run_parser.set_defaults(handler=cmd_run)

    return parser


def add_prefix_argument(parser: argparse.ArgumentParser) -> None:
    """Add the shared Wine prefix option to a subparser."""
    parser.add_argument("--prefix", default=str(DEFAULT_PREFIX), help="Wine prefix path")


def cmd_init(args: argparse.Namespace) -> int:
    """Handle ``winecap init``."""
    prefix = Path(args.prefix).expanduser()
    options = PrefixInitOptions(
        arch=args.arch,
        windows_version=args.winver,
        force=args.force,
    )
    return initialize_prefix(prefix, options)


def cmd_snapshot(args: argparse.Namespace) -> int:
    """Handle ``winecap snapshot``."""
    prefix = Path(args.prefix).resolve()
    if not prefix.exists():
        print(f"Error: Prefix not found: {prefix}")
        return 1

    wait_for_wineserver(prefix)
    print(f"Scanning files in {prefix / 'drive_c'}...")
    try:
        result = create_snapshot(prefix, args.name)
    except ValueError as error:
        print(f"Error: {error}")
        return 1
    print(f"  Found {result.file_count} files")
    print(f"  Found {result.registry_key_count} registry keys")
    print(f"Snapshot saved: {result.path}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """Handle ``winecap list``."""
    prefix = Path(args.prefix).resolve()
    if not prefix.exists():
        print(f"Error: Prefix not found: {prefix}")
        return 1

    try:
        snapshots = list_snapshots(prefix)
    except ValueError as error:
        print(f"Error: {error}")
        return 1
    if not snapshots:
        print("No snapshots found")
        return 0

    print(f"Snapshots in {prefix}:\n")
    print(f"{'Name':<20} {'Timestamp':<25} {'Files':<10} {'Reg Keys':<10}")
    print("-" * 65)
    for snapshot in snapshots:
        print(
            f"{snapshot['name']:<20} "
            f"{snapshot['timestamp']:<25} "
            f"{snapshot['files']:<10} "
            f"{snapshot['keys']:<10}"
        )
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    """Handle ``winecap diff``."""
    prefix = Path(args.prefix).resolve()
    snapshots = load_snapshot_pair(prefix, args.snapshot_a, args.snapshot_b)
    if snapshots is None:
        return 1

    diff = diff_snapshots(*snapshots)
    print(f"Diff: {args.snapshot_a} -> {args.snapshot_b}\n")
    print_diff_summary(diff)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Handle ``winecap export``."""
    prefix = Path(args.prefix).resolve()
    snapshots = load_snapshot_pair(prefix, args.snapshot_a, args.snapshot_b)
    if snapshots is None:
        return 1

    diff = diff_snapshots(*snapshots)
    if not args.no_review:
        diff = interactive_review(diff)

    output_dir = Path(args.output_dir).resolve()
    print(f"\nExporting to: {output_dir}")
    result = export_diff(prefix, diff, output_dir)
    print(f"Exported {result.files_exported} files")

    if result.registry_keys_exported:
        print(f"Exported {result.registry_keys_exported} registry keys to registry.reg")
    else:
        print("No registry changes to export")

    print("\nExport complete.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Handle ``winecap run``."""
    prefix = Path(args.prefix).resolve()
    if not prefix.exists():
        print(f"Error: Prefix not found: {prefix}")
        return 1

    executable = Path(args.executable).resolve()
    if not executable.exists():
        print(f"Error: Executable not found: {executable}")
        return 1

    return run_wine(prefix, [str(executable), *args.args], wait=True)


def load_snapshot_pair(prefix: Path, before_name: str, after_name: str) -> tuple[dict, dict] | None:
    """Load two snapshots, printing CLI-friendly errors."""
    if not prefix.exists():
        print(f"Error: Prefix not found: {prefix}")
        return None

    try:
        return load_snapshot(prefix, before_name), load_snapshot(prefix, after_name)
    except (FileNotFoundError, ValueError) as error:
        print(f"Error: {error}")
        return None


def print_diff_summary(diff: dict) -> None:
    """Print category and total counts for a diff."""
    categories = categorize_changes(diff)

    print("Summary by category:")
    for category_key in CATEGORY_ORDER:
        category = categories[category_key]
        file_count = len(category.files)
        registry_count = len(category.registry)
        if file_count or registry_count:
            print(f"  {category.description}: {file_count} files, {registry_count} registry keys")

    files = diff["files"]
    print(
        f"\nTotal: {len(files['added'])} files added, "
        f"{len(files['modified'])} modified, "
        f"{len(files['removed'])} removed"
    )
    print(f"       {registry_change_count(diff['registry'])} registry keys changed")


if __name__ == "__main__":
    raise SystemExit(main())
