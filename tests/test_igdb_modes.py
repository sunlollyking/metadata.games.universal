"""The ways a game can be played reach Kodi."""
import os
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, ADDON_DIR)
import kodistubs  # noqa: E402

kodistubs.install()

from resources.lib.providers import igdb  # noqa: E402


class ModesTest(unittest.TestCase):
    def test_game_modes_are_named(self):
        details = igdb.game_details({"id": 1, "name": "G", "game_modes": [
            {"name": "Single player"}, {"name": "Split screen"}]}, "19")
        self.assertEqual(details["modes"], ["Single player", "Split screen"])

    def test_a_game_with_no_modes_listed_has_none(self):
        self.assertNotIn("modes", igdb.game_details({"id": 1, "name": "G"}, "19"))


if __name__ == "__main__":
    unittest.main()
