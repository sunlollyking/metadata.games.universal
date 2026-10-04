"""prefer_region_art.py puts a real marquee before one ScreenScraper drew."""
import os
import sqlite3
import sys
import tempfile
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, os.path.join(os.path.dirname(TESTS_DIR), "tools"))
import kodistubs  # noqa: E402

kodistubs.install()

import prefer_region_art  # noqa: E402
from resources.lib.providers.screenscraper import SS_OWN_ART_REGION  # noqa: E402

SS = "https://neoclone.screenscraper.fr/api2/mediaJeu.php?jeuid=1&media={}(wor)"
LAUNCHBOX = "https://images.launchbox-app.com/0b0a.png"


class MarqueeTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "Games.db")
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TABLE art (media_id INTEGER, media_type TEXT, type TEXT, url TEXT)")
            db.executemany("INSERT INTO art VALUES (1, 'game', ?, ?)",
                           [("marquee", SS.format("screenmarquee")), ("marquee1", LAUNCHBOX)])

    def art(self):
        with sqlite3.connect(self.db) as db:
            return dict(db.execute("SELECT type, url FROM art"))

    def test_a_drawn_marquee_names_the_services_own_region(self):
        self.assertEqual(prefer_region_art.region(SS.format("screenmarquee")), SS_OWN_ART_REGION)
        self.assertEqual(prefer_region_art.region(SS.format("screenmarqueesmall")), SS_OWN_ART_REGION)
        self.assertEqual(prefer_region_art.region(SS.format("marquee")), "World")

    def test_the_cabinets_marquee_takes_the_drawn_ones_place(self):
        prefer_region_art.main([self.db, "--apply"])
        self.assertEqual(self.art(), {"marquee": LAUNCHBOX, "marquee1": SS.format("screenmarquee")})


class LogoTest(unittest.TestCase):
    PRIORITY = ["United Kingdom", "Europe", "World", "USA", "Japan"]

    def tearDown(self):
        prefer_region_art.launchbox_regions.clear()

    def test_an_english_logo_comes_before_a_japanese_one(self):
        self.assertLess(prefer_region_art.rank(SS.format("wheel").replace("(wor)", "(eu)"), self.PRIORITY, "clearlogo"),
                        prefer_region_art.rank(SS.format("wheel").replace("(wor)", "(jp)"), self.PRIORITY, "clearlogo"))

    def test_an_american_logo_comes_before_a_european_one(self):
        self.assertLess(prefer_region_art.rank(SS.format("wheel").replace("(wor)", "(us)"), self.PRIORITY, "clearlogo"),
                        prefer_region_art.rank(SS.format("wheel").replace("(wor)", "(eu)"), self.PRIORITY, "clearlogo"))

    def test_a_logo_of_unknown_region_comes_before_a_japanese_one(self):
        self.assertLess(prefer_region_art.rank(LAUNCHBOX, self.PRIORITY, "clearlogo"),
                        prefer_region_art.rank(SS.format("wheel").replace("(wor)", "(jp)"), self.PRIORITY, "clearlogo"))

    def test_a_box_still_follows_the_players_order(self):
        self.assertLess(prefer_region_art.rank(SS.format("box-2D").replace("(wor)", "(jp)"), self.PRIORITY, "boxfront"),
                        prefer_region_art.rank(LAUNCHBOX, self.PRIORITY, "boxfront"))

    def test_a_logo_rendered_by_the_service_comes_last(self):
        self.assertEqual(prefer_region_art.region(SS.format("wheel-carbon")), SS_OWN_ART_REGION)
        self.assertEqual(prefer_region_art.region(SS.format("wheel-steel")), SS_OWN_ART_REGION)

    def test_a_launchbox_picture_takes_its_region_from_the_catalogue(self):
        prefer_region_art.launchbox_regions.update({"0b0a.png": "North America"})
        self.assertEqual(prefer_region_art.region(LAUNCHBOX), "USA")


if __name__ == "__main__":
    unittest.main()
