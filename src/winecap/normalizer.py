"""Utilities for normalizing exported Windows registry files."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

WOW64_PATTERNS = (
    (r"(HKEY_LOCAL_MACHINE\\SOFTWARE)\\WOW6432Node\\", r"\1\\", r"HKLM\SOFTWARE\WOW6432Node"),
    (r"(HKEY_LOCAL_MACHINE\\Software)\\Wow6432Node\\", r"\1\\", r"HKLM\Software\Wow6432Node"),
    (
        r"(HKEY_LOCAL_MACHINE\\Software\\Classes)\\Wow6432Node\\",
        r"\1\\",
        r"HKLM\Software\Classes\Wow6432Node",
    ),
    (
        r"(HKEY_LOCAL_MACHINE\\SOFTWARE\\Classes)\\WOW6432Node\\",
        r"\1\\",
        r"HKLM\SOFTWARE\Classes\WOW6432Node",
    ),
    (r"(HKEY_CLASSES_ROOT)\\WOW6432Node\\", r"\1\\", r"HKCR\WOW6432Node"),
    (r"(HKEY_CLASSES_ROOT)\\Wow6432Node\\", r"\1\\", r"HKCR\Wow6432Node"),
    (r"(HKEY_CURRENT_USER\\SOFTWARE)\\WOW6432Node\\", r"\1\\", r"HKCU\SOFTWARE\WOW6432Node"),
    (r"(HKEY_CURRENT_USER\\Software)\\Wow6432Node\\", r"\1\\", r"HKCU\Software\Wow6432Node"),
)

WOW64_COMPILED = tuple(
    (re.compile(pattern, re.IGNORECASE), replacement, description)
    for pattern, replacement, description in WOW64_PATTERNS
)

USER_SID_PATTERN = re.compile(
    r"HKEY_USERS\\S-1-5-21-\d+-\d+-\d+-\d+\\",
    re.IGNORECASE,
)

UNICODE_HEADER = "Windows Registry Editor Version 5.00"
ANSI_HEADER = "REGEDIT4"


@dataclass
class RegistryStats:
    """Summary of registry file shape and normalization needs."""

    total_keys: int = 0
    native_keys: int = 0
    wow64_keys: int = 0
    hkcu_keys: int = 0
    user_sid_keys: int = 0
    other_keys: int = 0
    format: str = "unicode"
    wow64_patterns_found: set[str] = field(default_factory=set)
    sample_wow64: list[str] = field(default_factory=list)
    sample_native: list[str] = field(default_factory=list)
    sample_user_sid: list[str] = field(default_factory=list)

    @property
    def is_mixed(self) -> bool:
        """Return whether native HKLM and WOW64 keys appear together."""
        return self.native_keys > 0 and self.wow64_keys > 0

    @property
    def has_changes(self) -> bool:
        """Return whether default normalization would alter this file."""
        return self.wow64_keys > 0 or self.user_sid_keys > 0


def detect_encoding(file_path: Path) -> str:
    """Detect UTF-16LE BOM, UTF-8 BOM, or assume UTF-8-compatible text."""
    bom = file_path.read_bytes()[:3]
    if bom[:2] == b"\xff\xfe":
        return "utf-16-le"
    if bom == b"\xef\xbb\xbf":
        return "utf-8-sig"
    return "utf-8"


def read_reg_file(file_path: Path) -> tuple[str, str]:
    """Read a .reg file and return ``(content, encoding)``."""
    encoding = detect_encoding(file_path)
    return file_path.read_text(encoding=encoding, errors="replace"), encoding


def is_key_line(line: str) -> bool:
    """Return whether a line is a registry key header."""
    stripped = line.strip()
    return stripped.startswith("[") and stripped.endswith("]")


def extract_key_path(line: str) -> str | None:
    """Extract the key path from a registry key header."""
    match = re.match(r"\[([^\]]+)\]", line.strip())
    return match.group(1) if match else None


def is_wow64_path(path: str) -> bool:
    """Return whether a registry path is from the WOW64 registry view."""
    return "wow6432node" in path.lower()


def is_user_sid_path(path: str) -> bool:
    """Return whether a path includes a hard-coded Windows user SID."""
    return bool(USER_SID_PATTERN.search(path))


def normalize_registry_path(path: str) -> str:
    """Remove doubled path separators and WOW6432Node path components."""
    result = re.sub(r"\\\\+", r"\\", path)
    for pattern, replacement, _ in WOW64_COMPILED:
        result = pattern.sub(replacement, result)
    return result


def normalize_user_sid(path: str) -> str:
    """Convert ``HKEY_USERS\\S-1-5-21-...`` paths to ``HKEY_CURRENT_USER``."""
    return USER_SID_PATTERN.sub(r"HKEY_CURRENT_USER\\", path)


def registry_format(content: str) -> str:
    """Detect ``ansi`` or ``unicode`` .reg header format."""
    first_line = content.split("\n", 1)[0].strip()
    if first_line.startswith(ANSI_HEADER):
        return "ansi"
    return "unicode"


def convert_to_ansi_format(content: str) -> str:
    """Convert the registry file header to REGEDIT4."""
    return replace_header(content, UNICODE_HEADER, ANSI_HEADER)


def convert_to_unicode_format(content: str) -> str:
    """Convert the registry file header to Windows Registry Editor 5.00."""
    return replace_header(content, ANSI_HEADER, UNICODE_HEADER)


def replace_header(content: str, old_header: str, new_header: str) -> str:
    """Replace one registry header line without touching other content."""
    lines = content.splitlines()
    return "\n".join(new_header if line.strip() == old_header else line for line in lines)


def analyze_reg_content(content: str) -> RegistryStats:
    """Analyze registry content and return normalization statistics."""
    stats = RegistryStats(format=registry_format(content))

    for line in content.splitlines():
        if not is_key_line(line):
            continue

        stats.total_keys += 1
        key_path = extract_key_path(line)
        if key_path is not None:
            classify_key_path(stats, key_path)

    return stats


def classify_key_path(stats: RegistryStats, key_path: str) -> None:
    """Update stats for a single registry key path."""
    path_upper = key_path.upper()

    if is_user_sid_path(key_path):
        stats.user_sid_keys += 1
        append_sample(stats.sample_user_sid, key_path)
        return

    if is_wow64_path(key_path):
        stats.wow64_keys += 1
        append_sample(stats.sample_wow64, key_path)
        for pattern, _, description in WOW64_COMPILED:
            if pattern.search(key_path):
                stats.wow64_patterns_found.add(description)
        return

    if "HKEY_LOCAL_MACHINE" in path_upper:
        stats.native_keys += 1
        append_sample(stats.sample_native, key_path)
        return

    if "HKEY_CURRENT_USER" in path_upper:
        stats.hkcu_keys += 1
        return

    stats.other_keys += 1


def append_sample(samples: list[str], value: str) -> None:
    """Store up to three representative examples."""
    if len(samples) < 3:
        samples.append(value)


def fix_doubled_key_backslashes(content: str) -> str:
    """Collapse doubled separators inside registry key headers only."""
    fixed_lines = []
    for line in content.splitlines(keepends=True):
        fixed_lines.append(fix_key_line_backslashes(line))
    return "".join(fixed_lines)


def fix_key_line_backslashes(line: str) -> str:
    """Collapse repeated backslashes in one key header line."""
    if not is_key_line(line):
        return line

    stripped = line.strip()
    key_path = stripped[1:-1]
    fixed_path = re.sub(r"\\\\+", r"\\", key_path)
    leading = line[: len(line) - len(line.lstrip())]
    trailing = line[len(line.rstrip()) :]
    return f"{leading}[{fixed_path}]{trailing}"


def normalize_reg_content(
    content: str,
    normalize_wow64: bool = True,
    normalize_sids: bool = True,
) -> str:
    """Normalize WOW64 and user SID paths in .reg content."""
    result = fix_doubled_key_backslashes(content)

    if normalize_wow64:
        for pattern, replacement, _ in WOW64_COMPILED:
            result = pattern.sub(replacement, result)

    if normalize_sids:
        result = USER_SID_PATTERN.sub(r"HKEY_CURRENT_USER\\", result)

    return result


def split_mixed_reg_content(content: str) -> tuple[str, str]:
    """Split mixed native/WOW64 registry content into native and 32-bit parts."""
    lines = content.splitlines(keepends=True)
    header, content_start = extract_header_block(lines)
    native_parts = [header]
    wow64_parts = [header]

    current_block: list[str] = []
    current_is_wow64: bool | None = None

    for line in lines[content_start:]:
        if is_key_line(line):
            append_split_block(current_block, current_is_wow64, native_parts, wow64_parts)
            current_block = [line]
            key_path = extract_key_path(line)
            current_is_wow64 = is_wow64_path(key_path) if key_path else False
            continue

        current_block.append(line)

    append_split_block(current_block, current_is_wow64, native_parts, wow64_parts)
    return "".join(native_parts), "".join(wow64_parts)


def extract_header_block(lines: list[str]) -> tuple[str, int]:
    """Return the .reg header block and index where key content starts."""
    for index, line in enumerate(lines):
        if not line.strip().startswith(("Windows Registry Editor", ANSI_HEADER)):
            continue

        header_lines = [line]
        content_start = index + 1
        if content_start < len(lines) and not lines[content_start].strip():
            header_lines.append(lines[content_start])
            content_start += 1
        return "".join(header_lines), content_start

    return "", 0


def append_split_block(
    block: list[str],
    is_wow64: bool | None,
    native_parts: list[str],
    wow64_parts: list[str],
) -> None:
    """Append one registry key block to the native or WOW64 output."""
    if not block or is_wow64 is None:
        return

    block_text = "".join(block)
    if is_wow64:
        wow64_parts.append(normalize_reg_content(block_text))
    else:
        native_parts.append(block_text)
