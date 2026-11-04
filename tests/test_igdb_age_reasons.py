"""What a board rated a game for reaches Kodi with the rating."""
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


class AgeReasonsTest(unittest.TestCase):
    def test_the_reasons_come_with_the_rating(self):
        board, category = next(iter(igdb.BOARDS.items())), next(iter(igdb.RATING_CATEGORIES))
        ratings = igdb.age_ratings({"age_ratings": [{
            "organization": board[0], "rating_category": category,
            "rating_content_descriptions": [{"description": "Violence"},
                                            {"description": "Bad Language"}]}]})
        self.assertEqual(ratings[0]["descriptors"], "Violence, Bad Language")

    def test_a_rating_without_reasons_has_none(self):
        board, category = next(iter(igdb.BOARDS.items())), next(iter(igdb.RATING_CATEGORIES))
        ratings = igdb.age_ratings({"age_ratings": [{"organization": board[0],
                                                      "rating_category": category}]})
        self.assertEqual(ratings[0]["descriptors"], "")


if __name__ == "__main__":
    unittest.main()
