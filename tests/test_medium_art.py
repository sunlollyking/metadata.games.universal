"""A picture of the medium is named by the dump, not by the platform."""
import os
import sys
import unittest
import xml.etree.ElementTree as ET

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, ADDON_DIR)

from resources.lib.providers import Request, medium_art_type, screenscraper  # noqa: E402


def request(filename, platform=""):
    return Request({"filename": filename, "platform": platform}, {})


JEU = """<jeu>
  <noms><nom region="us">Sonic CD</nom></noms>
  <medias>
    <media type="box-2D" region="us">http://x/box.png</media>
    <media type="support-2D" region="us">http://x/medium.png</media>
    <media type="wheel-carbon" region="us">http://x/logo.png</media>
    <media type="steamgrid" region="us">http://x/grid.png</media>
  </medias>
</jeu>"""


class MediumTest(unittest.TestCase):

    def test_disc_dumps_are_discs(self):
        for name in ("Sonic CD (USA).cue", "game.chd", "Rayman.ISO", "a.gdi", "b.m3u"):
            self.assertEqual(medium_art_type(request(name)), "disc", name)

    def test_everything_else_is_a_cartridge(self):
        for name in ("Sonic (USA).md", "game.sfc", "tape.tzx", "", "no-extension"):
            self.assertEqual(medium_art_type(request(name)), "cartridge", name)

    def test_a_raw_dump_is_named_by_its_machine(self):
        for name, platform, expected in (("Sonic (USA).bin", "Sega Mega Drive", "cartridge"),
                                         ("Pitfall.bin", "Atari 2600", "cartridge"),
                                         ("Crash (USA).bin", "Sony PlayStation", "disc"),
                                         ("Snatcher.img", "Sega Mega-CD", "disc"),
                                         ("Ys.bin", "NEC PC Engine CD", "disc"),
                                         ("unknown.bin", "", "cartridge")):
            self.assertEqual(medium_art_type(request(name, platform)), expected, (name, platform))

    def test_screenscraper_names_the_medium_after_the_dump(self):
        for name, expected in (("Sonic CD (USA).cue", "disc"), ("Sonic (USA).md", "cartridge")):
            art = screenscraper.game_details(ET.fromstring(JEU), request(name))["art"]
            self.assertIn(expected, art)
            self.assertEqual(art[expected][0]["url"], "http://x/medium.png")

    def test_screenscraper_takes_the_less_usual_pictures(self):
        art = screenscraper.game_details(ET.fromstring(JEU), request("a.md"))["art"]
        self.assertEqual(art["clearlogo"][0]["url"], "http://x/logo.png")
        self.assertEqual(art["banner"][0]["url"], "http://x/grid.png")


if __name__ == "__main__":
    unittest.main()
