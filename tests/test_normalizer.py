from __future__ import annotations

import unittest

from tests import context  # noqa: F401
from winecap.normalizer import (
    analyze_reg_content,
    convert_to_ansi_format,
    convert_to_unicode_format,
    normalize_reg_content,
    split_mixed_reg_content,
)


class RegistryNormalizerTests(unittest.TestCase):
    def test_analyze_detects_mixed_wow64_and_user_sid_keys(self) -> None:
        content = "\n".join(
            [
                "Windows Registry Editor Version 5.00",
                "",
                r"[HKEY_LOCAL_MACHINE\SOFTWARE\Vendor\App]",
                r"[HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Vendor\App]",
                r"[HKEY_USERS\S-1-5-21-1-2-3-1000\Software\Vendor\App]",
            ]
        )

        stats = analyze_reg_content(content)

        self.assertEqual(stats.total_keys, 3)
        self.assertEqual(stats.native_keys, 1)
        self.assertEqual(stats.wow64_keys, 1)
        self.assertEqual(stats.user_sid_keys, 1)
        self.assertTrue(stats.is_mixed)

    def test_normalize_removes_wow64_and_replaces_user_sid(self) -> None:
        content = "\n".join(
            [
                "Windows Registry Editor Version 5.00",
                "",
                r"[HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Vendor\App]",
                '"Name"="Value"',
                r"[HKEY_USERS\S-1-5-21-1-2-3-1000\Software\Vendor\App]",
            ]
        )

        normalized = normalize_reg_content(content)

        self.assertNotIn("WOW6432Node", normalized)
        self.assertIn(r"[HKEY_LOCAL_MACHINE\SOFTWARE\Vendor\App]", normalized)
        self.assertIn(r"[HKEY_CURRENT_USER\Software\Vendor\App]", normalized)

    def test_split_keeps_native_and_normalizes_wow64_output(self) -> None:
        content = "\n".join(
            [
                "Windows Registry Editor Version 5.00",
                "",
                r"[HKEY_LOCAL_MACHINE\SOFTWARE\Vendor\App]",
                '"Name"="native"',
                "",
                r"[HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Vendor\App]",
                '"Name"="wow64"',
            ]
        )

        native_content, wow64_content = split_mixed_reg_content(content)

        self.assertIn('"Name"="native"', native_content)
        self.assertNotIn("WOW6432Node", wow64_content)
        self.assertIn('"Name"="wow64"', wow64_content)
        self.assertNotIn('"Name"="wow64"', native_content)

    def test_header_conversion_changes_only_header(self) -> None:
        ansi = convert_to_ansi_format("Windows Registry Editor Version 5.00\n\n[HKCU\\A]")
        unicode = convert_to_unicode_format("REGEDIT4\n\n[HKCU\\A]")

        self.assertEqual(ansi, "REGEDIT4\n\n[HKCU\\A]")
        self.assertEqual(unicode, "Windows Registry Editor Version 5.00\n\n[HKCU\\A]")


if __name__ == "__main__":
    unittest.main()
