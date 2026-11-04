"""The languages a game can be played in reach Kodi."""
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


def support(language, kind):
    return {"language": {"name": language}, "language_support_type": {"name": kind}}


class LanguageTest(unittest.TestCase):
    def test_each_language_says_how_it_is_supported(self):
        details = igdb.game_details({"id": 1, "name": "G", "language_supports": [
            support("English", "Audio"), support("English", "Interface"),
            support("Japanese", "Audio"), support("English", "Subtitles")]}, "19")
        self.assertEqual(details["languagesupport"], [
            {"language": "English", "audio": True, "interface": True, "subtitles": True},
            {"language": "Japanese", "audio": True}])

    def test_a_game_with_no_languages_listed_has_none(self):
        self.assertNotIn("languagesupport", igdb.game_details({"id": 1, "name": "G"}, "19"))


if __name__ == "__main__":
    unittest.main()
