"""ArcadeDB: asked by MAME set name, last, for what the other catalogues lack."""
import os
import sys
import tempfile
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, ADDON_DIR)

from fakenet import FakeNet, no_log  # noqa: E402
from resources.lib.providers import Request, arcadedb  # noqa: E402

HISTORY = ("Arcade Video game published 39 years ago:\r\n\r\n"
           "House Mannequin - Roppongi Live hen (c) 1987 Nichibutsu.\r\n\r\n"
           "A mahjong game in which the player faces a series of opponents in Roppongi.\r\n\r\n"
           "- TECHNICAL -\r\n\r\nMain CPU: Zilog Z80 (@ 5 Mhz)\r\n\r\n"
           "- TRIVIA -\r\n\r\nReleased in April 1987.\r\n\r\n"
           "- CONTRIBUTE -\r\n\r\nEdit this entry: https://www.arcade-history.com/game/1150/?o=2")
ROW = {"game_name": "housemn2", "title": "House Mannequin Roppongi Live hen (Japan 870418)",
       "history": HISTORY,
       "url_image_title": "https://adb.arcadeitalia.net/?mame=housemn2&type=title&resize=0",
       "url_image_ingame": "https://adb.arcadeitalia.net/?mame=housemn2&type=ingame&resize=0",
       "url_image_flyer": "", "url_image_marquee": "", "url_image_cabinet": ""}


def request(**query):
    return Request(dict({"platform": "arcade", "title": "House Mannequin"}, **query), {})


class OverviewTest(unittest.TestCase):
    def test_keeps_the_description_only(self):
        self.assertEqual(arcadedb.overview(HISTORY),
                         "A mahjong game in which the player faces a series of opponents in "
                         "Roppongi.")

    def test_a_label_is_not_a_description(self):
        self.assertEqual(arcadedb.overview("Redemption game published 23 years ago:\r\n\r\n"
                                           "Pac-Man Ball (c) 2003 Namco, Limited.\r\n\r\n"
                                           "Pusher game.\r\n\r\n- CONTRIBUTE -\r\n\r\nEdit"), "")

    def test_an_entry_that_points_at_its_original_says_nothing(self):
        self.assertEqual(arcadedb.overview(
            "Arcade Video game:\r\n\r\nAirline Pilots Deluxe (c) 1999 Sega.\r\n\r\n"
            "See the original standard model for more information about the game itself."), "")


class ArcadeDbTest(unittest.TestCase):
    def setUp(self):
        self.net = FakeNet().install(self)
        cache = tempfile.TemporaryDirectory()
        self.addCleanup(cache.cleanup)
        self.provider = arcadedb.ArcadeDbProvider(no_log, cache.name)

    def test_only_a_set_already_identified_is_asked_about(self):
        self.assertEqual(self.provider.find(request()), [])
        self.assertEqual(self.net.calls, [])

    def test_pictures_and_description(self):
        self.net.route("service_scraper.php", {"result": [ROW]})
        found = self.provider.find(request(romset="housemn2"))
        self.assertEqual(found[0]["id"], "housemn2")
        self.assertEqual(self.net.query("service_scraper.php")["game_name"], "housemn2")
        details = self.provider.details("housemn2", request(romset="housemn2"))
        self.assertEqual(sorted(details["art"]), ["screenshot", "titlescreen"])
        self.assertEqual(details["art"]["titlescreen"][0]["url"], ROW["url_image_title"])
        self.assertTrue(details["overview"].startswith("A mahjong game"))
        self.assertEqual(len(self.net.calls), 1, "the second call must come from the cache")

    def test_a_set_it_does_not_know_is_not_asked_about_again(self):
        self.net.route("service_scraper.php", {"result": []})
        self.assertEqual(self.provider.find(request(romset="nosuchset")), [])
        self.assertIsNone(self.provider.details("nosuchset", request(romset="nosuchset")))
        self.assertEqual(len(self.net.calls), 1)

    def test_a_pause_is_honoured(self):
        self.net.route("service_scraper.php", "busy", status=429)
        self.assertEqual(self.provider.find(request(romset="housemn2")), [])
        self.assertTrue(self.provider.exhausted)


if __name__ == "__main__":
    unittest.main()
