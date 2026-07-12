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
    if prefix.exists():
        if not options.force:
            print(f"Error: Prefix already exists: {prefix}")
            print("Use --force to remove and recreate it.")
            return 1

        print(f"Removing existing prefix: {prefix}")
        shutil.rmtree(prefix)

    print(f"Creating Wine prefix: {prefix}")
    print(f"  Architecture: {options.arch}")
    print(f"  Windows version: {options.windows_version}")

    env = wine_environment(prefix, options.arch)
    print("\nInitializing prefix. This may take a moment...")
    subprocess.run(["wineboot", "--init"], env=env, check=False)
    wait_for_wineserver(prefix)

    print(f"\nSetting Windows version to {options.windows_version}...")
    subprocess.run(["wine", "winecfg", "/v", options.windows_version], env=env, check=False)
    wait_for_wineserver(prefix)

    print("\nTaking baseline snapshot...")
    result = create_snapshot(prefix, "baseline")
    print(f"  Found {result.file_count} files")
    print(f"  Found {result.registry_key_count} registry keys")
    print(f"Snapshot saved: {result.path}")

    print("\nPrefix initialized.")
    print(f"Next: winecap run installer.exe --prefix {prefix}")
    print(f"Then: winecap snapshot post_install --prefix {prefix}")
    print(f"Then: winecap export baseline post_install ./output --prefix {prefix}")
    return 0
