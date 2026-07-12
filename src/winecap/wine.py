"""Boundary around Wine and wineserver subprocess calls."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence

from .snapshots import create_snapshot

WINESERVER_TIMEOUT_SECONDS = 30
WINECAP_PREFIX_MARKER = ".winecap-prefix"
WINECAP_PREFIX_MARKER_CONTENT = "managed by winecap\n"
WINE_PREFIX_REGISTRY_FILES = ("system.reg", "user.reg")


@dataclass(frozen=True)
class PrefixInitOptions:
    """Options for creating a Wine prefix."""

    arch: str
    windows_version: str
    force: bool = False


def wine_environment(prefix: Path, arch: str | None = None) -> dict[str, str]:
    """Return environment variables for Wine commands in a prefix."""
    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix)
    if arch is not None:
        env["WINEARCH"] = arch
    return env


def wait_for_wineserver(prefix: Path, timeout: int = WINESERVER_TIMEOUT_SECONDS) -> None:
    """Wait for Wine to flush pending prefix writes."""
    env = wine_environment(prefix)
    print("Waiting for wineserver to flush...")
    try:
        subprocess.run(["wineserver", "-w"], env=env, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        print(f"Warning: wineserver did not exit within {timeout}s, killing it...")
        subprocess.run(["wineserver", "-k"], env=env, check=False)
        time.sleep(2)


def run_wine(prefix: Path, wine_args: Sequence[str], wait: bool = True) -> int:
    """Run ``wine`` with the provided arguments."""
    command = ["wine", *wine_args]
    print(f"Running: {' '.join(command)}")
    result = subprocess.run(command, env=wine_environment(prefix), check=False)
    if wait:
        wait_for_wineserver(prefix)
    return result.returncode


def initialize_prefix(prefix: Path, options: PrefixInitOptions) -> int:
    """Create a Wine prefix, configure Windows version, and capture baseline."""
    prefix = prefix.expanduser()
    if prefix.is_symlink():
        print(f"Error: Refusing to initialize through a symbolic link: {prefix}")
        return 1
    prefix = prefix.resolve()
    if prefix.exists():
        if not options.force:
            print(f"Error: Prefix already exists: {prefix}")
            print("Use --force to remove and recreate it.")
            return 1

        removal_error = prefix_removal_error(prefix)
        if removal_error is not None:
            print(f"Error: Refusing to remove {prefix}: {removal_error}")
            return 1

        print(f"Removing existing prefix: {prefix}")
        shutil.rmtree(prefix)

    print(f"Creating Wine prefix: {prefix}")
    print(f"  Architecture: {options.arch}")
    print(f"  Windows version: {options.windows_version}")

    env = wine_environment(prefix, options.arch)
    print("\nInitializing prefix. This may take a moment...")
    wineboot_result = subprocess.run(["wineboot", "--init"], env=env, check=False)
    if wineboot_result.returncode != 0:
        print(f"Error: wineboot failed with exit code {wineboot_result.returncode}")
        return wineboot_result.returncode or 1
    if not prefix.is_dir():
        print(f"Error: wineboot did not create the prefix directory: {prefix}")
        return 1
    wait_for_wineserver(prefix)

    print(f"\nSetting Windows version to {options.windows_version}...")
    winecfg_result = subprocess.run(
        ["wine", "winecfg", "/v", options.windows_version],
        env=env,
        check=False,
    )
    if winecfg_result.returncode != 0:
        print(f"Error: winecfg failed with exit code {winecfg_result.returncode}")
        return winecfg_result.returncode or 1
    wait_for_wineserver(prefix)

    (prefix / WINECAP_PREFIX_MARKER).write_text(
        WINECAP_PREFIX_MARKER_CONTENT,
        encoding="utf-8",
    )

    print("\nTaking baseline snapshot...")
    result = create_snapshot(prefix, "baseline")
    print(f"  Found {result.file_count} files")
    print(f"  Found {result.registry_key_count} registry keys")
    print(f"Snapshot saved: {result.path}")

    print("\nPrefix initialized.")
    print(f"Next: winecap run --prefix {prefix} installer.exe")
    print(f"Then: winecap snapshot post_install --prefix {prefix}")
    print(f"Then: winecap export baseline post_install ./output --prefix {prefix}")
    return 0


def prefix_removal_error(prefix: Path) -> str | None:
    """Explain why an existing path cannot safely be removed, if applicable."""
    prefix = prefix.expanduser()
    if prefix.is_symlink():
        return "the path is a symbolic link"
    prefix = prefix.resolve()
    home = Path.home().resolve()
    cwd = Path.cwd().resolve()
    protected = {Path(prefix.anchor), home, cwd, *home.parents, *cwd.parents}
    if prefix in protected:
        return "the path is a filesystem root, home directory, working directory, or parent"
    if not prefix.is_dir():
        return "the path is not a directory"
    if not is_recognized_wine_prefix(prefix):
        return (
            f"the directory is not marked by {WINECAP_PREFIX_MARKER} and does not "
            "contain drive_c, system.reg, and user.reg"
        )
    return None


def is_recognized_wine_prefix(prefix: Path) -> bool:
    """Return whether a directory has positive Wine-prefix identity."""
    marker = prefix / WINECAP_PREFIX_MARKER
    if not marker.is_symlink() and marker.is_file():
        try:
            if marker.read_text(encoding="utf-8") == WINECAP_PREFIX_MARKER_CONTENT:
                return True
        except OSError:
            return False

    drive_c = prefix / "drive_c"
    if drive_c.is_symlink() or not drive_c.is_dir():
        return False
    for registry_file in WINE_PREFIX_REGISTRY_FILES:
        registry_path = prefix / registry_file
        if registry_path.is_symlink() or not registry_path.is_file():
            return False
        try:
            with registry_path.open(encoding="utf-8", errors="replace") as registry:
                if not registry.readline(64).startswith("WINE REGISTRY Version "):
                    return False
        except OSError:
            return False
    return True
