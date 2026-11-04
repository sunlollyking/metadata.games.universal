"""The games IGDB says are like this one reach Kodi."""
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


class SimilarTest(unittest.TestCase):
    def test_similar_games_are_named(self):
        details = igdb.game_details({"id": 1, "name": "Super Mario World", "similar_games": [
            {"name": "Super Mario Bros. 3"}, {"name": "Yoshi's Island"}]}, "19")
        self.assertEqual(details["similar"], ["Super Mario Bros. 3", "Yoshi's Island"])

    def test_a_game_like_no_other_has_none(self):
        self.assertNotIn("similar", igdb.game_details({"id": 1, "name": "G"}, "19"))


if __name__ == "__main__":
    unittest.main()
