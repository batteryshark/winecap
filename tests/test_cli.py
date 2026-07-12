from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from tests import context  # noqa: F401
from winecap.cli import build_parser, main
from winecap.wine import WINECAP_PREFIX_MARKER, WINECAP_PREFIX_MARKER_CONTENT


class CliTests(unittest.TestCase):
    def test_run_preserves_installer_options(self) -> None:
        args = build_parser().parse_args(
            ["run", "--prefix", "/tmp/test-prefix", "installer.exe", "--silent", "/S"]
        )

        self.assertEqual(args.prefix, "/tmp/test-prefix")
        self.assertEqual(args.executable, "installer.exe")
        self.assertEqual(args.args, ["--silent", "/S"])

    @patch("winecap.wine.shutil.rmtree")
    def test_init_force_rejects_symlinked_prefix_before_removal(self, rmtree_mock) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            prefix = root / "real-prefix"
            prefix.mkdir()
            (prefix / WINECAP_PREFIX_MARKER).write_text(
                WINECAP_PREFIX_MARKER_CONTENT,
                encoding="utf-8",
            )
            alias = root / "prefix-alias"
            alias.symlink_to(prefix, target_is_directory=True)

            result = main(["init", "--force", "--prefix", str(alias)])

            self.assertEqual(result, 1)
            rmtree_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
