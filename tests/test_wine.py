from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import Mock, patch

from tests import context  # noqa: F401
from winecap.wine import (
    PrefixInitOptions,
    WINECAP_PREFIX_MARKER,
    WINECAP_PREFIX_MARKER_CONTENT,
    initialize_prefix,
    prefix_removal_error,
)


class WineSafetyTests(unittest.TestCase):
    def test_force_rejects_unrecognized_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "ordinary-directory"
            candidate.mkdir()

            error = prefix_removal_error(candidate)

            self.assertIsNotNone(error)
            self.assertIn("does not contain", error or "")

    def test_force_accepts_recognized_wine_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prefix = Path(temp_dir) / "wine-prefix"
            (prefix / "drive_c").mkdir(parents=True)
            (prefix / "system.reg").write_text("WINE REGISTRY Version 2\n", encoding="utf-8")
            (prefix / "user.reg").write_text("WINE REGISTRY Version 2\n", encoding="utf-8")

            self.assertIsNone(prefix_removal_error(prefix))

    def test_force_accepts_winecap_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prefix = Path(temp_dir) / "wine-prefix"
            prefix.mkdir()
            (prefix / WINECAP_PREFIX_MARKER).write_text(
                WINECAP_PREFIX_MARKER_CONTENT,
                encoding="utf-8",
            )

            self.assertIsNone(prefix_removal_error(prefix))

    def test_force_rejects_symlinked_identity_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ordinary = root / "ordinary"
            ordinary.mkdir()
            target_file = root / "target"
            target_file.write_text(WINECAP_PREFIX_MARKER_CONTENT, encoding="utf-8")
            (ordinary / WINECAP_PREFIX_MARKER).symlink_to(target_file)

            self.assertIsNotNone(prefix_removal_error(ordinary))

            (ordinary / WINECAP_PREFIX_MARKER).unlink()
            real_drive = root / "real-drive"
            real_drive.mkdir()
            (ordinary / "drive_c").symlink_to(real_drive, target_is_directory=True)
            for registry_name in ("system.reg", "user.reg"):
                (ordinary / registry_name).symlink_to(target_file)

            self.assertIsNotNone(prefix_removal_error(ordinary))

    def test_force_rejects_symlinked_prefix_path(self) -> None:
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

            self.assertIsNotNone(prefix_removal_error(alias))

    def test_force_rejects_home_and_working_directory(self) -> None:
        self.assertIsNotNone(prefix_removal_error(Path.home()))
        self.assertIsNotNone(prefix_removal_error(Path.cwd()))

    @patch("winecap.wine.shutil.rmtree")
    @patch("winecap.wine.subprocess.run")
    def test_force_does_not_remove_unrecognized_directory(
        self,
        run_mock: Mock,
        rmtree_mock: Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "ordinary-directory"
            candidate.mkdir()

            result = initialize_prefix(
                candidate,
                PrefixInitOptions(arch="win64", windows_version="win10", force=True),
            )

            self.assertEqual(result, 1)
            rmtree_mock.assert_not_called()
            run_mock.assert_not_called()


    @patch("winecap.wine.subprocess.run")
    def test_initialize_propagates_wineboot_failure(self, run_mock: Mock) -> None:
        run_mock.return_value = CompletedProcess(["wineboot", "--init"], 17)
        with tempfile.TemporaryDirectory() as temp_dir:
            prefix = Path(temp_dir) / "new-prefix"

            result = initialize_prefix(
                prefix,
                PrefixInitOptions(arch="win64", windows_version="win10"),
            )

        self.assertEqual(result, 17)

    @patch("winecap.wine.wait_for_wineserver")
    @patch("winecap.wine.subprocess.run")
    def test_initialize_propagates_winecfg_failure(
        self,
        run_mock: Mock,
        wait_mock: Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prefix = Path(temp_dir) / "new-prefix"

            def run_side_effect(command: list[str], **_: object) -> CompletedProcess:
                if command[0] == "wineboot":
                    prefix.mkdir()
                    return CompletedProcess(command, 0)
                return CompletedProcess(command, 9)

            run_mock.side_effect = run_side_effect
            result = initialize_prefix(
                prefix,
                PrefixInitOptions(arch="win64", windows_version="win10"),
            )

            self.assertFalse((prefix / WINECAP_PREFIX_MARKER).exists())

        self.assertEqual(result, 9)
        wait_mock.assert_called_once_with(prefix.resolve())


if __name__ == "__main__":
    unittest.main()
