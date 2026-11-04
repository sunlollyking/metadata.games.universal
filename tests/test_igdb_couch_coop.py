"""How a game is played together on one screen reaches Kodi."""
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


class CouchCoopTest(unittest.TestCase):
    def test_drop_in_split_screen_and_co_op_players(self):
        details = igdb.game_details({"id": 1, "name": "G", "multiplayer_modes": [
            {"platform": 19, "offlinemax": 4, "offlinecoop": True, "offlinecoopmax": 2,
             "dropin": True, "splitscreen": False}]}, "19")
        self.assertTrue(details["dropin"])
        self.assertFalse(details["splitscreen"])
        self.assertEqual(details["coopplayers"], 2)

    def test_what_igdb_does_not_say_is_left_out(self):
        details = igdb.game_details({"id": 1, "name": "G", "multiplayer_modes": [
            {"platform": 19, "offlinemax": 2}]}, "19")
        for key in ("dropin", "splitscreen", "coopplayers"):
            self.assertNotIn(key, details)

    def test_the_platform_s_own_mode_is_used(self):
        details = igdb.game_details({"id": 1, "name": "G", "multiplayer_modes": [
            {"platform": 6, "splitscreen": True},
            {"platform": 19, "splitscreen": False}]}, "19")
        self.assertFalse(details["splitscreen"])


if __name__ == "__main__":
    unittest.main()
