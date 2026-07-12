# winecap

`winecap` captures what a Windows installer changes inside a Wine prefix, helps you review those changes, and exports the useful files and registry keys.

The project also includes two companion tools:

- `normalize-reg`: clean exported `.reg` files by removing WOW64 path noise and hard-coded user SIDs.
- `scan-pe`: scan DLL/EXE trees and print architecture, version, timestamp, and version-resource metadata.

## Install

From this checkout:

```bash
python -m pip install -e ".[dev]"
```

Runtime-only install:

```bash
python -m pip install .
```

## Quick Workflow

```bash
winecap init --prefix ~/.wine_capture_test
winecap run installer.exe --prefix ~/.wine_capture_test
winecap snapshot post_install --prefix ~/.wine_capture_test
winecap diff baseline post_install --prefix ~/.wine_capture_test
winecap export baseline post_install ./output --prefix ~/.wine_capture_test
```

Use `--no-review` on export when you want all non-blocklisted changes without the category prompt.

## Commands

### `winecap`

Capture and diff a Wine prefix.

```bash
winecap init [--prefix PATH] [--arch win64|win32] [--winver win10|win7|winxp] [--force]
winecap snapshot NAME [--prefix PATH]
winecap list [--prefix PATH]
winecap diff SNAPSHOT_A SNAPSHOT_B [--prefix PATH]
winecap export SNAPSHOT_A SNAPSHOT_B OUTPUT_DIR [--prefix PATH] [--no-review]
winecap run INSTALLER.exe [args...] [--prefix PATH]
```

Snapshots are stored in the prefix under `.snapshots/`. The diff logic compares file hashes and Wine registry hives, while filtering strict Wine/runtime noise such as Wine configuration and volatile hardware enumeration keys.

### `normalize-reg`

Analyze, normalize, split, or convert `.reg` files.

```bash
normalize-reg input.reg
normalize-reg input.reg --in-place
normalize-reg input.reg -o output.reg
normalize-reg input.reg --split
normalize-reg input.reg --ansi -o output.reg
```

Default normalization:

- Removes `WOW6432Node` from common 32-bit registry views.
- Converts `HKEY_USERS\S-1-5-21-...` user SID paths to `HKEY_CURRENT_USER`.
- Fixes doubled backslashes inside registry key headers.

### `scan-pe`

Scan a directory tree for PE files.

```bash
scan-pe ./some_directory
```

It reports architecture, fixed file version, product/company strings, original filename, and PE timestamp when available.

## Development

Run tests:

```bash
python -m unittest discover -s tests
```

Run a syntax/import sanity check:

```bash
python -m compileall src tests winecap.py normalize_reg.py scan_pe.py
```

The current package layout is documented in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). The first architecture decision record is [docs/adr/0001-package-layout-and-cli-boundaries.md](docs/adr/0001-package-layout-and-cli-boundaries.md).
