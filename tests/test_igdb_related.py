"""The games IGDB relates to this one reach Kodi with what each is to it."""
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


class RelatedTest(unittest.TestCase):
    def test_remakes_ports_and_add_ons_say_what_they_are(self):
        details = igdb.game_details({
            "id": 1, "name": "The Legend of Zelda: Link's Awakening",
            "remakes": [{"name": "The Legend of Zelda: Link's Awakening (2019)"}],
            "ports": [{"name": "The Legend of Zelda: Link's Awakening DX"}],
            "expansions": [{"name": "Extra"}], "standalone_expansions": [{"name": "Alone"}]}, "33")
        self.assertEqual(details["related"], [
            {"kind": "remake", "title": "The Legend of Zelda: Link's Awakening (2019)"},
            {"kind": "port", "title": "The Legend of Zelda: Link's Awakening DX"},
            {"kind": "expansion", "title": "Extra"},
            {"kind": "expansion", "title": "Alone"}])

    def test_an_add_on_names_the_game_it_belongs_to(self):
        details = igdb.game_details({"id": 1, "name": "DLC", "parent_game": {"name": "Base"}}, "6")
        self.assertEqual(details["related"], [{"kind": "original", "title": "Base"}])

    def test_a_game_on_its_own_has_none(self):
        self.assertNotIn("related", igdb.game_details({"id": 1, "name": "G"}, "19"))


if __name__ == "__main__":
    unittest.main()
