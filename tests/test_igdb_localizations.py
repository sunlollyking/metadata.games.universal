"""A game's names and covers in other regions reach Kodi."""
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

CONTRA = {"id": 1, "name": "Contra", "cover": {"image_id": "us"}, "game_localizations": [
    {"name": "Probotector", "region": {"name": "Europe"}, "cover": {"image_id": "eu"}},
    {"name": "Gryzor", "region": {"identifier": "worldwide"}},
    {"name": "Nameless", "region": {"name": "Atlantis"}}]}


class LocalizationTest(unittest.TestCase):
    def test_igdbs_own_cover_names_no_region(self):
        art = igdb.game_details(CONTRA, "18")["art"]["boxfront"]
        self.assertEqual(art, [{"url": igdb.IMAGE_URL.format("cover_big", "us")}])

    def test_regional_names_are_names_of_the_game(self):
        names = igdb.game_details(CONTRA, "18")["names"]
        self.assertIn("Probotector", names)
        self.assertIn("Gryzor", names)
        self.assertNotIn("Nameless", names)

    def test_the_name_and_cover_in_the_players_first_region(self):
        self.assertEqual(igdb.regional_localization(CONTRA, ["united kingdom", "europe", "world"]),
                         ("Europe", "Probotector", igdb.IMAGE_URL.format("cover_big", "eu")))
        self.assertEqual(igdb.regional_localization(CONTRA, ["world", "europe"]), ("World", "Gryzor", ""))
        self.assertIsNone(igdb.regional_localization(CONTRA, ["japan"]))

    def test_a_region_further_down_the_list_changes_nothing(self):
        sonic = {"id": 2, "name": "Sonic the Hedgehog 2", "cover": {"image_id": "main"}, "game_localizations": [
            {"name": "Sonic the Hedgehog 2", "region": {"name": "Japan"}, "cover": {"image_id": "jp"}}]}
        self.assertIsNone(igdb.regional_localization(sonic, ["united kingdom", "europe", "usa", "japan"]))


if __name__ == "__main__":
    unittest.main()
