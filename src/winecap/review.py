"""Interactive grouping for installer change review."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CATEGORY_ORDER = (
    "vc_runtime",
    "dotnet",
    "directx",
    "program_files",
    "windows_system",
    "fonts",
    "certificates",
    "installer_cache",
    "other",
)

CATEGORY_DESCRIPTIONS = {
    "vc_runtime": "Visual C++ Runtime",
    "dotnet": ".NET Framework",
    "directx": "DirectX/DirectSound/Direct3D",
    "windows_system": "Windows System Files",
    "fonts": "Fonts",
    "certificates": "Certificates",
    "installer_cache": "Installer Cache/Metadata",
    "program_files": "Program Files",
    "other": "Other",
}


@dataclass
class ChangeCategory:
    """Files and registry keys grouped for review."""

    description: str
    files: list[tuple[str, str]] = field(default_factory=list)
    registry: list[tuple[str, str]] = field(default_factory=list)


def categorize_changes(diff: dict[str, Any]) -> dict[str, ChangeCategory]:
    """Group file and registry changes by installer-related category."""
    categories = {
        key: ChangeCategory(description)
        for key, description in CATEGORY_DESCRIPTIONS.items()
    }

    for change_type in ("added", "modified"):
        label = "add" if change_type == "added" else "mod"
        for path in diff.get("files", {}).get(change_type, {}):
            categories[categorize_file(path)].files.append((label, path))

    for change_type in ("added", "modified"):
        for hive, keys in diff.get("registry", {}).get(change_type, {}).items():
            for key in keys:
                categories[categorize_registry_key(key)].registry.append((hive, key))

    return categories


def interactive_review(diff: dict[str, Any]) -> dict[str, Any]:
    """Ask the user which change categories to exclude from export."""
    categories = categorize_changes(diff)
    selections = print_category_review(categories)
    excluded = read_excluded_categories(selections)
    return filter_diff_by_category(diff, categories, excluded)


def print_category_review(categories: dict[str, ChangeCategory]) -> dict[str, int]:
    """Print category summary and return ``{category_key: menu_number}``."""
    print("\n" + "=" * 60)
    print("CHANGE CATEGORIES")
    print("=" * 60)

    selections = {}
    category_number = 1
    for category_key in CATEGORY_ORDER:
        category = categories[category_key]
        file_count = len(category.files)
        registry_count = len(category.registry)
        if file_count == 0 and registry_count == 0:
            continue

        print(f"\n{category_number}. {category.description}")
        print(f"   Files: {file_count}, Registry keys: {registry_count}")
        print_sample_files(category)
        print_sample_registry_keys(category)

        selections[category_key] = category_number
        category_number += 1

    print("\n" + "=" * 60)
    print("Enter category numbers to EXCLUDE, comma-separated.")
    print("Press Enter to include all categories.")
    return selections


def read_excluded_categories(selections: dict[str, int]) -> set[str]:
    """Read category numbers from stdin and return excluded category keys."""
    try:
        response = input("> ").strip()
    except EOFError:
        response = ""

    if not response:
        return set()

    excluded_numbers = {
        int(part.strip())
        for part in response.split(",")
        if part.strip().isdigit()
    }
    return {
        category_key
        for category_key, number in selections.items()
        if number in excluded_numbers
    }


def filter_diff_by_category(
    diff: dict[str, Any],
    categories: dict[str, ChangeCategory],
    excluded: set[str],
) -> dict[str, Any]:
    """Return a diff with excluded category changes removed."""
    filtered = empty_diff()

    for category_key, category in categories.items():
        if category_key in excluded:
            continue

        add_category_files(diff, filtered, category)
        add_category_registry(diff, filtered, category)

    return filtered


def empty_diff() -> dict[str, Any]:
    """Create an empty diff with the standard structure."""
    return {
        "files": {"added": {}, "modified": {}, "removed": []},
        "registry": {"added": {}, "modified": {}, "removed": []},
    }


def categorize_file(path: str) -> str:
    """Return the review category key for a changed file path."""
    normalized = path.lower()
    if any(token in normalized for token in ("msvc", "vcrun", "mfc", "atl", "vcomp", "concrt")):
        return "vc_runtime"
    if any(token in normalized for token in ("dotnet", ".net", "clr", "mscoree", "mscor")):
        return "dotnet"
    if any(token in normalized for token in ("d3d", "direct", "dinput", "dsound", "ddraw", "xaudio", "xinput", "x3daudio")):
        return "directx"
    if "fonts" in normalized or normalized.endswith((".ttf", ".otf")):
        return "fonts"
    if "program files" in normalized:
        return "program_files"
    if any(token in normalized for token in ("installer", "msi", "assembly", "winsxs")):
        return "installer_cache"
    if any(token in normalized for token in ("system32", "syswow64", "windows")):
        return "windows_system"
    return "other"


def categorize_registry_key(key: str) -> str:
    """Return the review category key for a changed registry key."""
    normalized = key.lower()
    if any(token in normalized for token in ("visualstudio", "vc\\", "vcredist", "devdiv\\vc")):
        return "vc_runtime"
    if any(token in normalized for token in ("netframework", ".netframework", "clr", "fusion")):
        return "dotnet"
    if any(token in normalized for token in ("directx", "direct3d", "directdraw", "directsound", "directmusic", "directplay")):
        return "directx"
    if any(token in normalized for token in ("fonts", "fontsubstitutes", "fontlink")):
        return "fonts"
    if any(token in normalized for token in ("certificates", "cryptography\\machinesid", "cryptography\\rng")):
        return "certificates"
    if any(token in normalized for token in ("installer", "products", "features", "components", "assembly")):
        return "installer_cache"
    return "other"


def print_sample_files(category: ChangeCategory) -> None:
    """Print up to three sample files for a category."""
    if not category.files:
        return

    print("   Sample files:")
    for _, path in category.files[:3]:
        print(f"     - {path}")
    if len(category.files) > 3:
        print(f"     ... and {len(category.files) - 3} more")


def print_sample_registry_keys(category: ChangeCategory) -> None:
    """Print up to three sample registry keys for a category."""
    if not category.registry:
        return

    print("   Sample registry:")
    for _, key in category.registry[:3]:
        print(f"     - {key}")
    if len(category.registry) > 3:
        print(f"     ... and {len(category.registry) - 3} more")


def add_category_files(
    source: dict[str, Any],
    target: dict[str, Any],
    category: ChangeCategory,
) -> None:
    """Copy selected category file changes into a filtered diff."""
    for change_label, path in category.files:
        change_type = "added" if change_label == "add" else "modified"
        if path in source.get("files", {}).get(change_type, {}):
            target["files"][change_type][path] = source["files"][change_type][path]


def add_category_registry(
    source: dict[str, Any],
    target: dict[str, Any],
    category: ChangeCategory,
) -> None:
    """Copy selected category registry changes into a filtered diff."""
    for hive, key in category.registry:
        for change_type in ("added", "modified"):
            if key not in source.get("registry", {}).get(change_type, {}).get(hive, {}):
                continue

            target["registry"][change_type].setdefault(hive, {})
            target["registry"][change_type][hive][key] = source["registry"][change_type][hive][key]
