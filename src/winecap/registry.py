"""Wine registry parsing, comparison, and Windows .reg export helpers."""

from __future__ import annotations

import re
from pathlib import Path

REGISTRY_HIVES = ("system.reg", "user.reg", "userdef.reg")

REGISTRY_BLOCKLIST_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^Software\\\\Wine\\\\",
        r"^Software\\\\Wow6432Node\\\\Wine\\\\",
        r"^Volatile Environment$",
        r"\\\\Enum\\\\",
        r"^System\\\\CurrentControlSet\\\\Enum",
        r"^System\\\\ControlSet\d*\\\\Enum",
        r"\\\\Wintrust\\\\",
        r"^Console$",
        r"\\\\SQMClient\\\\",
        r"\\\\IdentityCRL\\\\Dynamic Salt",
        r"\\\\IdentityCRL\\\\StoredIdentities",
        r"\\\\Control\\\\Class\\\\",
        r"\\\\WindowsUpdate\\\\",
        r"^Environment$",
        r"\\\\Session Manager\\\\Environment",
    )
)

HIVE_ROOTS = {
    "system.reg": "HKEY_LOCAL_MACHINE",
    "user.reg": "HKEY_CURRENT_USER",
    "userdef.reg": r"HKEY_USERS\.Default",
}

RegistryValues = dict[str, str]
RegistryHive = dict[str, RegistryValues]
RegistrySnapshot = dict[str, RegistryHive]
RegistryDiff = dict[str, dict[str, RegistryHive] | list[str]]


def parse_wine_registry(registry_path: Path) -> RegistryHive:
    """Parse a Wine hive file into ``{key: {value_name: value}}``."""
    if not registry_path.exists():
        return {}

    try:
        content = registry_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    registry: RegistryHive = {}
    current_key: str | None = None
    lines = content.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index].strip()

        if line.startswith("[") and "]" in line:
            bracket_end = line.index("]")
            current_key = line[1:bracket_end]
            registry[current_key] = {}

            if _next_line_is_timestamp(lines, index):
                index += 1
        elif current_key and _is_value_line(line):
            name, value = _parse_value_line(lines, index)
            if name is not None and value is not None:
                registry[current_key][name] = value
                index = _continued_line_end(lines, index)

        index += 1

    return registry


def read_registry_hives(prefix: Path) -> RegistrySnapshot:
    """Read all known Wine hives from a prefix."""
    registry: RegistrySnapshot = {}
    for hive in REGISTRY_HIVES:
        hive_path = prefix / hive
        if hive_path.exists():
            registry[hive] = parse_wine_registry(hive_path)
    return registry


def diff_registry_snapshots(before: RegistrySnapshot, after: RegistrySnapshot) -> RegistryDiff:
    """Compare registry snapshots while ignoring strict Wine/runtime noise."""
    diff: RegistryDiff = {"added": {}, "modified": {}, "removed": []}

    for hive in REGISTRY_HIVES:
        before_hive = before.get(hive, {})
        after_hive = after.get(hive, {})

        for key, values in after_hive.items():
            if is_blocked_registry_key(key):
                continue

            if key not in before_hive:
                _registry_change_bucket(diff, "added", hive)[key] = values
                continue

            changed_values = {
                name: value
                for name, value in values.items()
                if before_hive[key].get(name) != value
            }
            if changed_values:
                _registry_change_bucket(diff, "modified", hive)[key] = changed_values

        for key in before_hive:
            if key not in after_hive and not is_blocked_registry_key(key):
                removed = diff["removed"]
                if isinstance(removed, list):
                    removed.append(f"{hive}:{key}")

    return diff


def is_blocked_registry_key(key_path: str) -> bool:
    """Return whether a key is known Wine/runtime noise."""
    return any(pattern.search(key_path) for pattern in REGISTRY_BLOCKLIST_PATTERNS)


def registry_change_count(diff: RegistryDiff) -> int:
    """Count changed registry keys in an added/modified registry diff."""
    count = 0
    for change_type in ("added", "modified"):
        change_set = diff.get(change_type, {})
        if isinstance(change_set, dict):
            count += sum(len(keys) for keys in change_set.values())
    return count


def write_registry_export(output_dir: Path, diff: RegistryDiff) -> int:
    """Write changed registry keys to ``registry.reg`` and return key count."""
    lines = ["Windows Registry Editor Version 5.00", ""]
    keys_exported = 0

    for change_type in ("added", "modified"):
        change_set = diff.get(change_type, {})
        if not isinstance(change_set, dict):
            continue

        for hive, keys in change_set.items():
            for key, values in keys.items():
                windows_key = windows_key_for_hive(hive, key)
                if windows_key is None:
                    continue

                lines.append(f"[{windows_key}]")
                for value_name, value_data in values.items():
                    lines.append(format_registry_assignment(value_name, value_data))
                lines.append("")
                keys_exported += 1

    if keys_exported:
        registry_path = output_dir / "registry.reg"
        registry_path.write_text("\n".join(lines), encoding="utf-8")

    return keys_exported


def format_registry_assignment(value_name: str, value_data: str) -> str:
    """Format one Wine registry value assignment for a Windows .reg file."""
    if value_name == "@":
        return f"@={format_wine_registry_value(value_data)}"
    return f'"{value_name}"={format_wine_registry_value(value_data)}'


def format_wine_registry_value(value: str) -> str:
    """Convert Wine registry value syntax to Windows .reg value syntax."""
    if value.startswith(("dword:", "hex")):
        return value
    if value.startswith("str:"):
        return quote_reg_string(value[4:])
    if value.startswith('"'):
        return value
    return quote_reg_string(value)


def quote_reg_string(value: str) -> str:
    """Quote a string for a .reg value."""
    escaped = value.replace("\\", "\\\\").replace('"', r"\"")
    return f'"{escaped}"'


def windows_key_for_hive(hive: str, key: str) -> str | None:
    """Convert a Wine hive/key pair to a Windows registry key path."""
    root = HIVE_ROOTS.get(hive)
    if root is None:
        return None
    return f"{root}\\{key}"


def _next_line_is_timestamp(lines: list[str], index: int) -> bool:
    return index + 1 < len(lines) and lines[index + 1].strip().startswith("#time=")


def _is_value_line(line: str) -> bool:
    return "=" in line and not line.startswith(("#", ";"))


def _parse_value_line(lines: list[str], index: int) -> tuple[str | None, str | None]:
    full_line = _join_continued_value(lines, index)
    match = re.match(r'^(?:"([^"]*)"|([@]))=(.*)$', full_line)
    if match is None:
        return None, None

    name = match.group(1) if match.group(1) is not None else "@"
    return name, match.group(3)


def _join_continued_value(lines: list[str], index: int) -> str:
    full_line = lines[index].strip()
    while full_line.endswith("\\") and index + 1 < len(lines):
        index += 1
        full_line = full_line[:-1] + lines[index].strip()
    return full_line


def _continued_line_end(lines: list[str], index: int) -> int:
    full_line = lines[index].strip()
    while full_line.endswith("\\") and index + 1 < len(lines):
        index += 1
        full_line = full_line[:-1] + lines[index].strip()
    return index


def _registry_change_bucket(diff: RegistryDiff, change_type: str, hive: str) -> RegistryHive:
    change_set = diff[change_type]
    if not isinstance(change_set, dict):
        raise TypeError(f"{change_type} registry bucket must be a dictionary")
    return change_set.setdefault(hive, {})
