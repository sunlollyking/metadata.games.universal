"""A catalogue entry often names one game twice, and a set names it once."""
import os
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, ADDON_DIR)

from resources.lib.providers.libretro import Catalogue  # noqa: E402


class AlternateTitleTest(unittest.TestCase):
    def catalogue(self, *names):
        cat = Catalogue("SNK - Neo Geo")
        for name in names:
            cat.add({"name": name})
        return cat

    def test_either_half_of_a_double_name_finds_the_game(self):
        # The set calls it bluesjourney; the catalogue carries both names
        cat = self.catalogue("Blue's Journey / Raguy (ALM-001)")
        self.assertEqual([c["title"] for c in cat.find({"title": "bluesjourney"})],
                         ["Blue's Journey / Raguy"])
        self.assertEqual([c["title"] for c in cat.find({"title": "Raguy"})],
                         ["Blue's Journey / Raguy"])

    def test_the_pair_run_together_still_finds_it(self):
        cat = self.catalogue("Blue's Journey / Raguy (ALM-001)")
        self.assertTrue(cat.find({"title": "Blue's Journey / Raguy"}))

    def test_a_name_without_its_subtitle_finds_the_game(self):
        cat = self.catalogue("Galaxy Fight - Universal Warriors")
        self.assertEqual([c["title"] for c in cat.find({"title": "galaxyfight"})],
                         ["Galaxy Fight - Universal Warriors"])

    def test_a_subtitle_several_games_share_matches_none_of_them(self):
        # Picking one of four Zelda II records would be a wrong match dressed
        # up as a right one
        cat = self.catalogue("Zelda II - The Adventure of Link (USA)",
                             "Zelda II - Link no Bouken (Japan)")
        self.assertEqual(cat.find({"title": "Zelda II"}), [])

    def test_an_exact_title_beats_a_head_of_the_same_spelling(self):
        cat = self.catalogue("Ganryu / Musashi Ganryuki", "Ganryu - Something Else")
        self.assertEqual([c["title"] for c in cat.find({"title": "Ganryu"})],
                         ["Ganryu / Musashi Ganryuki"])

    def test_an_ordinary_name_is_unaffected(self):
        cat = self.catalogue("Metal Slug (NGM-201)")
        self.assertEqual([c["title"] for c in cat.find({"title": "Metal Slug"})], ["Metal Slug"])
