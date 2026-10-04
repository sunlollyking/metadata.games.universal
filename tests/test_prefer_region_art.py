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


if __name__ == "__main__":
    unittest.main()
