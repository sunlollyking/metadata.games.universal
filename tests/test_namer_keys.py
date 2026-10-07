"""Titles in any script compare by their own letters, not only the ASCII in them."""
import os
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, ADDON_DIR)
import kodistubs  # noqa: E402

kodistubs.install()

from resources.lib import namer  # noqa: E402
from resources.lib.providers import igdb  # noqa: E402


class TestNormalise(unittest.TestCase):
    def test_two_japanese_titles_ending_in_the_same_number_differ(self):
        self.assertNotEqual(namer.normalise("あすか2"), namer.normalise("人形使い2"))

    def test_a_japanese_title_is_not_just_its_number(self):
        self.assertEqual(namer.normalise("あすか2"), "あすか2")

    def test_a_japanese_title_is_not_its_latin_letters_alone(self):
        self.assertNotEqual(namer.normalise("Xガール"), namer.normalise("X"))

    def test_full_and_half_width_forms_match(self):
        self.assertEqual(namer.normalise("Ｘ２"), namer.normalise("X2"))
        self.assertEqual(namer.normalise("ﾄﾞﾗｺﾞﾝ"), namer.normalise("ドラゴン"))

    def test_kana_keep_their_voicing(self):
        self.assertNotEqual(namer.normalise("ガール"), namer.normalise("カール"))

    def test_an_accented_latin_title_matches_the_plain_one(self):
        self.assertEqual(namer.normalise("Pokémon Red"), namer.normalise("Pokemon Red"))

    def test_latin_titles_are_unchanged(self):
        self.assertEqual(namer.normalise("Legend of Zelda, The"), "legendofzelda")
        self.assertEqual(namer.normalise("Street Fighter II: The World Warrior"), "streetfighteriiworldwarrior")


class TestIgdbTitleKeys(unittest.TestCase):
    def test_a_japanese_alternative_name_is_not_reduced_to_its_number(self):
        game = {"name": "Ningyou Tsukai 2", "alternative_names": [{"name": "人形使い2"}]}
        keys = igdb.title_keys(game)
        self.assertNotIn("2", keys)
        self.assertNotIn(namer.normalise("あすか2"), keys)
        self.assertIn(namer.normalise("人形使い2"), keys)


if __name__ == "__main__":
    unittest.main()
