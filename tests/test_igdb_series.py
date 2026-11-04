"""A game's series reaches Kodi apart from its wider franchise."""
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


class SeriesTest(unittest.TestCase):
    def test_the_collection_is_the_series_and_the_franchise_is_not(self):
        details = igdb.game_details({"id": 1, "name": "Mario Kart 64",
                                     "franchises": [{"name": "Mario"}],
                                     "collections": [{"name": "Mario Kart"}]}, "4")
        self.assertEqual(details["series"], "Mario Kart")
        self.assertEqual(details["collections"], ["Mario", "Mario Kart"])

    def test_the_older_single_collection_is_read_too(self):
        details = igdb.game_details({"id": 1, "name": "G", "collection": {"name": "Zelda"}}, "4")
        self.assertEqual(details["series"], "Zelda")

    def test_a_game_in_no_series_has_none(self):
        details = igdb.game_details({"id": 1, "name": "G", "franchises": [{"name": "Mario"}]}, "4")
        self.assertNotIn("series", details)


if __name__ == "__main__":
    unittest.main()
