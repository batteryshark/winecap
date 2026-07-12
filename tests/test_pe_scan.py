from __future__ import annotations

import unittest
from types import SimpleNamespace

from tests import context  # noqa: F401
from winecap.pe_scan import get_architecture, get_fixed_version, get_timestamp


class PeScanTests(unittest.TestCase):
    def test_get_architecture_names_known_machine_types(self) -> None:
        pe = SimpleNamespace(FILE_HEADER=SimpleNamespace(Machine=0x8664))

        self.assertEqual(get_architecture(pe), "x64")

    def test_get_timestamp_handles_zero_timestamp(self) -> None:
        pe = SimpleNamespace(FILE_HEADER=SimpleNamespace(TimeDateStamp=0))

        self.assertEqual(get_timestamp(pe), (None, None))

    def test_get_fixed_version_formats_four_part_version(self) -> None:
        fixed_info = SimpleNamespace(
            FileVersionMS=(1 << 16) | 2,
            FileVersionLS=(3 << 16) | 4,
        )
        pe = SimpleNamespace(VS_FIXEDFILEINFO=[fixed_info])

        self.assertEqual(get_fixed_version(pe), "1.2.3.4")


if __name__ == "__main__":
    unittest.main()
