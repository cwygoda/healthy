from __future__ import annotations

import unittest

from healthy.adapters.power import GRAPHICS_CAPABILITY, parse_system_capabilities

FULL_WAKE_OUTPUT = """Current System Capabilities are: CPU Graphics Audio Network
Current Power State: 4
"""

DARK_WAKE_OUTPUT = """Current System Capabilities are: CPU Network
Current Power State: 1
"""


class SystemCapabilityTests(unittest.TestCase):
    def test_full_wake_advertises_graphics(self) -> None:
        capabilities = parse_system_capabilities(FULL_WAKE_OUTPUT)

        self.assertIsNotNone(capabilities)
        self.assertIn(GRAPHICS_CAPABILITY, capabilities)

    def test_dark_wake_does_not_advertise_graphics(self) -> None:
        capabilities = parse_system_capabilities(DARK_WAKE_OUTPUT)

        self.assertIsNotNone(capabilities)
        self.assertNotIn(GRAPHICS_CAPABILITY, capabilities)

    def test_missing_capabilities_line_is_unknown(self) -> None:
        self.assertIsNone(parse_system_capabilities("Current Power State: 4\n"))

    def test_empty_capabilities_list_is_unknown(self) -> None:
        self.assertIsNone(parse_system_capabilities("Current System Capabilities are:\n"))

    def test_empty_output_is_unknown(self) -> None:
        self.assertIsNone(parse_system_capabilities(""))


if __name__ == "__main__":
    unittest.main()
