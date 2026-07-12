"""Command-line interface for .reg normalization."""

from __future__ import annotations

import argparse
from pathlib import Path

from .normalizer import (
    RegistryStats,
    analyze_reg_content,
    convert_to_ansi_format,
    convert_to_unicode_format,
    normalize_reg_content,
    normalize_registry_path,
    normalize_user_sid,
    read_reg_file,
    split_mixed_reg_content,
)


def main(argv: list[str] | None = None) -> int:
    """Run the ``normalize-reg`` CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        return 1

    content, encoding = read_reg_file(input_path)
    stats = analyze_reg_content(content)
    print_analysis(input_path, encoding, stats)

    if args.split:
        return split_file(input_path, content, encoding, args.force, stats)
    if args.output or args.in_place:
        return normalize_file(input_path, content, encoding, args, stats)

    print_preview(input_path, stats)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Create the normalizer argument parser."""
    parser = argparse.ArgumentParser(description="Normalize .reg files for Wine dependency captures.")
    parser.add_argument("input", help="Input .reg file")
    parser.add_argument("-o", "--output", help="Output file. Default mode only prints analysis.")
    parser.add_argument("--in-place", action="store_true", help="Modify file in place")
    parser.add_argument("--split", action="store_true", help="Split mixed files into _x64.reg and _x86.reg")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output files")
    parser.add_argument("--ansi", action="store_true", help="Convert to REGEDIT4 format")
    parser.add_argument("--unicode", action="store_true", help="Convert to Windows Registry Editor 5.00 format")
    parser.add_argument("--no-sid", action="store_true", help="Skip user SID normalization")
    parser.add_argument("--no-wow64", action="store_true", help="Skip WOW64 path normalization")
    return parser


def print_analysis(input_path: Path, encoding: str, stats: RegistryStats) -> None:
    """Print registry file statistics."""
    format_description = "REGEDIT4 - Win9x compatible" if stats.format == "ansi" else "Windows Registry Editor 5.00"

    print("\n" + "=" * 60)
    print("REGISTRY FILE ANALYSIS")
    print("=" * 60)
    print(f"File:     {input_path}")
    print(f"Encoding: {encoding}")
    print(f"Format:   {stats.format.upper()} ({format_description})")
    print(f"Keys:     {stats.total_keys} total")
    print(f"          {stats.native_keys} native HKLM (64-bit view)")
    print(f"          {stats.wow64_keys} WOW64 (32-bit view)")
    print(f"          {stats.hkcu_keys} HKEY_CURRENT_USER")
    if stats.user_sid_keys:
        print(f"          {stats.user_sid_keys} HKEY_USERS with SID")
    print(f"          {stats.other_keys} other")

    print_patterns(stats)
    print_samples("Sample WOW64 keys", stats.sample_wow64)
    print_samples("Sample User SID keys", stats.sample_user_sid)
    print_issues(stats)


def print_patterns(stats: RegistryStats) -> None:
    """Print WOW64 patterns found in the file."""
    if not stats.wow64_patterns_found:
        return

    print("\nWOW64 patterns found:")
    for pattern in sorted(stats.wow64_patterns_found):
        print(f"  - {pattern}")


def print_samples(title: str, samples: list[str]) -> None:
    """Print sample key paths."""
    if not samples:
        return

    print(f"\n{title}:")
    for sample in samples:
        print(f"  [{truncate(sample)}]")


def print_issues(stats: RegistryStats) -> None:
    """Print normalization issues and clean status."""
    issues = []
    if stats.is_mixed:
        issues.append("MIXED: contains both native 64-bit and WOW64 32-bit HKLM keys")
    if stats.wow64_keys and not stats.is_mixed:
        issues.append("WOW64: contains 32-bit paths that can be normalized")
    if stats.user_sid_keys:
        issues.append(f"USER SID: {stats.user_sid_keys} keys with hardcoded user SIDs")

    if not issues:
        print("\nOK: File is clean; no WOW64 or SID issues found.")
        return

    print("\nIssues found:")
    for issue in issues:
        print(f"   - {issue}")


def split_file(
    input_path: Path,
    content: str,
    encoding: str,
    force: bool,
    stats: RegistryStats,
) -> int:
    """Write native and WOW64 registry files for mixed content."""
    if not stats.is_mixed:
        print("\nWarning: File is not mixed, so --split has no effect.")
        if stats.wow64_keys:
            print("Use -o or --in-place to normalize WOW64 paths.")
        return 0

    native_content, wow64_content = split_mixed_reg_content(content)
    native_path, wow64_path = split_output_paths(input_path)

    if not force and (native_path.exists() or wow64_path.exists()):
        print("\nError: Output files exist. Use --force to overwrite.")
        return 1

    native_path.write_text(native_content, encoding=encoding)
    wow64_path.write_text(wow64_content, encoding=encoding)

    native_stats = analyze_reg_content(native_content)
    wow64_stats = analyze_reg_content(wow64_content)

    print("\n" + "=" * 60)
    print("SPLITTING FILE")
    print("=" * 60)
    print(f"Created: {native_path} ({native_stats.total_keys} keys)")
    print(f"Created: {wow64_path} ({wow64_stats.total_keys} keys)")
    print_manifest_hint(native_path, wow64_path)
    return 0


def normalize_file(
    input_path: Path,
    content: str,
    encoding: str,
    args: argparse.Namespace,
    stats: RegistryStats,
) -> int:
    """Write normalized registry content."""
    if not needs_normalization(args, stats):
        print("\nNo changes needed.")
        return 0

    if stats.is_mixed and not args.no_wow64:
        print("\nWarning: Mixed file will have WOW64 paths normalized in place.")
        print("Consider --split if native and 32-bit views should stay separate.")

    normalized = normalize_reg_content(
        content,
        normalize_wow64=not args.no_wow64,
        normalize_sids=not args.no_sid,
    )
    normalized = apply_format_conversion(normalized, args, stats)

    output_path = Path(args.output) if args.output else input_path
    if output_path.exists() and not args.force and not args.in_place:
        print("\nError: Output file exists. Use --force to overwrite.")
        return 1

    output_encoding = "utf-8" if args.ansi else encoding
    output_path.write_text(normalized, encoding=output_encoding)

    print("\n" + "=" * 60)
    print("NORMALIZED")
    print("=" * 60)
    print(f"Output: {output_path}")
    print_changes(args, stats)
    print_output_manifest_hint(args, stats)
    return 0


def needs_normalization(args: argparse.Namespace, stats: RegistryStats) -> bool:
    """Return whether requested options require writing content."""
    return (
        (stats.wow64_keys > 0 and not args.no_wow64)
        or (stats.user_sid_keys > 0 and not args.no_sid)
        or args.ansi
        or args.unicode
    )


def apply_format_conversion(content: str, args: argparse.Namespace, stats: RegistryStats) -> str:
    """Apply requested registry header conversion."""
    if args.ansi and stats.format != "ansi":
        return convert_to_ansi_format(content)
    if args.unicode and stats.format != "unicode":
        return convert_to_unicode_format(content)
    return content


def print_changes(args: argparse.Namespace, stats: RegistryStats) -> None:
    """Print changes applied during normalization."""
    if stats.wow64_keys and not args.no_wow64:
        print(f"  - {stats.wow64_keys} WOW64 paths cleaned")
    if stats.user_sid_keys and not args.no_sid:
        print(f"  - {stats.user_sid_keys} user SID paths converted to HKCU")
    if args.ansi and stats.format != "ansi":
        print("  - Converted to ANSI (REGEDIT4) format")
    if args.unicode and stats.format != "unicode":
        print("  - Converted to Unicode format")


def print_output_manifest_hint(args: argparse.Namespace, stats: RegistryStats) -> None:
    """Print import manifest hints after normalization."""
    print("\nManifest hints:")
    if stats.wow64_keys and stats.native_keys == 0:
        print("  registry:")
        print("    arch: 32")
    if args.ansi:
        print("  # ANSI format required for Win9x compatibility")
        print("  # Import with: wine regedit /s registry.reg")


def print_preview(input_path: Path, stats: RegistryStats) -> None:
    """Print dry-run normalization preview."""
    if not stats.has_changes:
        return

    print("\n" + "=" * 60)
    print("PREVIEW (no changes made)")
    print("=" * 60)
    print_wow64_preview(stats)
    print_user_sid_preview(stats)

    print("To normalize, run with:")
    if stats.is_mixed:
        print(f'  normalize-reg "{input_path}" --split')
    else:
        print(f'  normalize-reg "{input_path}" --in-place')
        print(f'  normalize-reg "{input_path}" -o output.reg')

    if stats.format == "unicode":
        print("\nFor Win9x compatibility:")
        print(f'  normalize-reg "{input_path}" --ansi -o output.reg')


def print_wow64_preview(stats: RegistryStats) -> None:
    """Print sample WOW64 normalization preview."""
    if not stats.sample_wow64:
        return

    print("Sample WOW64 normalizations:")
    for path in stats.sample_wow64[:2]:
        print(f"  Before: [{truncate(path, 55)}]")
        print(f"  After:  [{truncate(normalize_registry_path(path), 55)}]")
    print()


def print_user_sid_preview(stats: RegistryStats) -> None:
    """Print sample user SID normalization preview."""
    if not stats.sample_user_sid:
        return

    print("Sample User SID conversions:")
    for path in stats.sample_user_sid[:2]:
        print(f"  Before: [{truncate(path, 55)}]")
        print(f"  After:  [{truncate(normalize_user_sid(path), 55)}]")
    print()


def split_output_paths(input_path: Path) -> tuple[Path, Path]:
    """Return ``(_x64.reg, _x86.reg)`` output paths for a split."""
    base = input_path.stem
    if base.endswith(("_x64", "_x86")):
        base = base[:-4]
    return input_path.parent / f"{base}_x64.reg", input_path.parent / f"{base}_x86.reg"


def print_manifest_hint(native_path: Path, wow64_path: Path) -> None:
    """Print registry manifest hint for split files."""
    print("\nManifest hint:")
    print("  registry:")
    print("    files:")
    print(f"      - file: {native_path.name}")
    print("        arch: 64")
    print(f"      - file: {wow64_path.name}")
    print("        arch: 32")


def truncate(value: str, max_length: int = 70) -> str:
    """Return a shortened path preview."""
    if len(value) <= max_length:
        return value
    return f"{value[:max_length]}..."


if __name__ == "__main__":
    raise SystemExit(main())
