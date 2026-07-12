from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests import context  # noqa: F401
from winecap.snapshots import diff_files, scan_prefix_files


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


if __name__ == "__main__":
    unittest.main()
