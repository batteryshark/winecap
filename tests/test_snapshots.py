from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests import context  # noqa: F401
from winecap.snapshots import (
    create_snapshot,
    diff_files,
    list_snapshots,
    load_snapshot,
    scan_prefix_files,
)


class SnapshotTests(unittest.TestCase):
    def test_diff_files_reports_added_modified_and_removed(self) -> None:
        before = {
            "same.txt": {"hash": "same"},
            "changed.txt": {"hash": "old"},
            "removed.txt": {"hash": "gone"},
        }
        after = {
            "same.txt": {"hash": "same"},
            "changed.txt": {"hash": "new"},
            "added.txt": {"hash": "fresh"},
        }

        diff = diff_files(before, after)

        self.assertIn("added.txt", diff["added"])
        self.assertIn("changed.txt", diff["modified"])
        self.assertEqual(diff["removed"], ["removed.txt"])

    def test_scan_prefix_files_hashes_drive_c_and_skips_internal_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prefix = Path(temp_dir)
            drive_c = prefix / "drive_c"
            drive_c.mkdir()
            (drive_c / "app.exe").write_bytes(b"hello")
            snapshots_dir = drive_c / ".snapshots"
            snapshots_dir.mkdir()
            (snapshots_dir / "internal.json").write_text("{}", encoding="utf-8")

            files = scan_prefix_files(prefix)

        self.assertIn("app.exe", files)
        self.assertNotIn(".snapshots/internal.json", files)
        self.assertEqual(files["app.exe"]["size"], 5)

    def test_snapshot_names_cannot_escape_snapshot_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prefix = Path(temp_dir) / "prefix"
            prefix.mkdir()

            for name in ("../../escape", "nested/name", "..", "", "name.json/child"):
                with self.subTest(name=name):
                    with self.assertRaises(ValueError):
                        create_snapshot(prefix, name)
                    with self.assertRaises(ValueError):
                        load_snapshot(prefix, name)

            self.assertFalse((Path(temp_dir) / "escape.json").exists())

    def test_snapshot_round_trip_uses_safe_leaf_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prefix = Path(temp_dir) / "prefix"
            prefix.mkdir()

            result = create_snapshot(prefix, "post-install_1.0")
            loaded = load_snapshot(prefix, "post-install_1.0")

            self.assertEqual(result.path.parent, prefix.resolve() / ".snapshots")
            self.assertEqual(loaded["name"], "post-install_1.0")

    def test_snapshot_file_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prefix = Path(temp_dir) / "prefix"
            prefix.mkdir()
            target = create_snapshot(prefix, "target")
            original = target.path.read_text(encoding="utf-8")
            (prefix / ".snapshots" / "alias.json").symlink_to(target.path)

            with self.assertRaises(ValueError):
                create_snapshot(prefix, "alias")
            with self.assertRaises(ValueError):
                load_snapshot(prefix, "alias")

            self.assertEqual(target.path.read_text(encoding="utf-8"), original)

    def test_snapshot_directory_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prefix = Path(temp_dir) / "prefix"
            outside = Path(temp_dir) / "outside"
            prefix.mkdir()
            outside.mkdir()
            (prefix / ".snapshots").symlink_to(outside, target_is_directory=True)

            with self.assertRaises(ValueError):
                create_snapshot(prefix, "baseline")
            with self.assertRaises(ValueError):
                load_snapshot(prefix, "baseline")
            with self.assertRaises(ValueError):
                list_snapshots(prefix)


if __name__ == "__main__":
    unittest.main()
