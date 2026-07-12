from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests import context  # noqa: F401
from winecap.registry import (
    diff_registry_snapshots,
    format_wine_registry_value,
    parse_wine_registry,
    registry_change_count,
    write_registry_export,
)


class WineRegistryTests(unittest.TestCase):
    def test_parse_wine_registry_reads_keys_values_and_continuations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry_path = Path(temp_dir) / "user.reg"
            registry_path.write_text(
                "\n".join(
                    [
                        r"[Software\\Vendor\\App] 123",
                        "#time=1d9abcdef",
                        '"Name"="str:Example"',
                        '"Bytes"=hex:01,\\',
                        "  02,03",
                        '@="dword:00000001"',
                    ]
                ),
                encoding="utf-8",
            )

            registry = parse_wine_registry(registry_path)

        self.assertEqual(registry[r"Software\\Vendor\\App"]["Name"], '"str:Example"')
        self.assertEqual(registry[r"Software\\Vendor\\App"]["Bytes"], "hex:01,02,03")
        self.assertEqual(registry[r"Software\\Vendor\\App"]["@"], '"dword:00000001"')

    def test_diff_filters_wine_noise_and_counts_changes(self) -> None:
        before = {
            "user.reg": {
                r"Software\\Vendor\\App": {"Name": '"old"'},
            }
        }
        after = {
            "user.reg": {
                r"Software\\Vendor\\App": {"Name": '"new"'},
                r"Software\\Vendor\\New": {"Name": '"added"'},
                r"Software\\Wine\\DllOverrides": {"mscoree": '"disabled"'},
            }
        }

        diff = diff_registry_snapshots(before, after)

        self.assertEqual(registry_change_count(diff), 2)
        self.assertIn(r"Software\\Vendor\\New", diff["added"]["user.reg"])
        self.assertNotIn(r"Software\\Wine\\DllOverrides", diff["added"].get("user.reg", {}))

    def test_write_registry_export_formats_values(self) -> None:
        diff = {
            "added": {
                "user.reg": {
                    r"Software\\Vendor\\App": {
                        "@": "str:Default",
                        "Enabled": "dword:00000001",
                    }
                }
            },
            "modified": {},
            "removed": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            count = write_registry_export(output_dir, diff)
            exported = (output_dir / "registry.reg").read_text(encoding="utf-8")

        self.assertEqual(count, 1)
        self.assertIn(r"[HKEY_CURRENT_USER\Software\\Vendor\\App]", exported)
        self.assertIn('@="Default"', exported)
        self.assertIn('"Enabled"=dword:00000001', exported)

    def test_format_wine_registry_value_preserves_non_string_types(self) -> None:
        self.assertEqual(format_wine_registry_value("dword:00000001"), "dword:00000001")
        self.assertEqual(format_wine_registry_value("hex:01,02"), "hex:01,02")
        self.assertEqual(format_wine_registry_value("str:Value"), '"Value"')


if __name__ == "__main__":
    unittest.main()
