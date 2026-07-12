# ADR 0001: Use a src Package Layout and Keep CLIs Thin

## Status

Accepted.

## Context

The historical project had three useful command-line tools implemented as top-level scripts:

- `winecap.py`
- `normalize_reg.py`
- `scan_pe.py`

That made the tools easy to run directly, but it mixed CLI parsing, terminal output, domain logic, subprocess calls, file IO, and parsing in the same modules. The project is being prepared for a private git repository where future navigation and safe change matter more than preserving the exact script shape.

## Decision

Move the implementation into `src/winecap/` and expose public command entrypoints through `pyproject.toml`:

- `winecap.cli:main`
- `winecap.normalizer_cli:main`
- `winecap.pe_cli:main`

Keep tiny compatibility launchers at the old top-level paths so direct checkout usage still works.

Split responsibilities by behavior:

- Wine subprocess calls live in `wine.py`.
- Snapshot and file diff behavior lives in `snapshots.py`.
- Wine registry parsing, filtering, diffing, and export formatting live in `registry.py`.
- Interactive grouping lives in `review.py`.
- `.reg` cleanup logic lives in `normalizer.py`.
- PE metadata extraction lives in `pe_scan.py`.

## Consequences

Positive:

- Domain behavior can be tested without invoking Wine.
- Importing normalizer and scanner helpers no longer requires running CLI code.
- `pefile` is imported lazily, so non-PE workflows remain easier to test.
- The old script names still work as compatibility entrypoints.

Tradeoffs:

- There are more files than before.
- Directly editing a single large script is no longer the main workflow.
- Real Wine integration still needs host-level validation beyond unit tests.

## Reconsider If

- The project becomes a single-purpose script again.
- The compatibility launchers start accumulating logic.
- A new packaging target requires a different import layout.
