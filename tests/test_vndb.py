"""VNDB names a Japanese computer's visual novels from that machine's own list."""
import json
import os
import sys
import tempfile
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, ADDON_DIR)
import kodistubs  # noqa: E402

kodistubs.install()

from fakenet import FakeNet, no_log  # noqa: E402
from resources.lib.providers import Request  # noqa: E402
from resources.lib.providers import vndb  # noqa: E402

KOKUU = {
    "id": "v6994", "title": "38-man Kilo no Kokuu", "alttitle": "38万キロの虚空",
    "titles": [{"title": "38万キロの虚空", "latin": "38-man Kilo no Kokuu"}],
    "released": "1989-10-21", "developers": [{"name": "Tokyo Shoseki"}],
    "image": {"url": "https://t.vndb.org/cv/94/6994.jpg", "sexual": 0, "violence": 0},
    "description": "A [url=/c123]detective[/url] story on the Moon.[spoiler]The end.[/spoiler]\n\n"
                   "[From [url=https://example.org]the box[/url]]",
}
KNIGHT = {
    "id": "v2385", "title": "Dragon Knight", "alttitle": "ドラゴンナイト",
    "titles": [], "released": "1989-11-29", "developers": [], "image": None, "description": "",
}
KNIGHT_3 = {
    "id": "v2387", "title": "Dragon Knight III", "alttitle": "ドラゴンナイトIII",
    "titles": [], "released": "1991-07-26", "developers": [], "image": None, "description": "",
}
NEGAI = {
    "id": "v29124", "title": "Mittsu no Negai", "alttitle": "3つの願い", "titles": [],
    "released": "1995", "developers": [],
    "image": {"url": "https://t.vndb.org/cv/24/29124.jpg", "sexual": 2, "violence": 0},
    "description": "",
}


def request(title, platform="pc98", **settings):
    return Request({"title": title, "platform": platform}, dict({"cache_days": 30}, **settings))


class VndbTest(unittest.TestCase):
    def setUp(self):
        self.net = FakeNet().install(self)
        pages = [{"results": [KOKUU, KNIGHT, KNIGHT_3], "more": True}, {"results": [NEGAI], "more": False}]
        self.net.route(lambda method, url, body: "vndb" in url and json.loads(body).get("page") == 1, pages[0])
        self.net.route(lambda method, url, body: "vndb" in url and json.loads(body).get("page") == 2, pages[1])
        self.provider = vndb.VndbProvider(no_log, tempfile.mkdtemp())

    def test_finds_a_game_by_its_japanese_title(self):
        found = self.provider.find(request("38万キロの虚空"))
        self.assertEqual([c["id"] for c in found], ["v6994"])
        self.assertEqual(found[0]["year"], 1989)

    def test_reads_the_whole_list_for_the_machine_once(self):
        self.provider.find(request("38万キロの虚空"))
        self.provider.find(request("Mittsu no Negai"))
        self.assertEqual(len(self.net.urls("vndb")), 2)
        self.assertEqual(json.loads(self.net.bodies("vndb")[0])["filters"], ["platform", "=", "p98"])

    def test_a_sequel_number_reads_the_same_in_roman_numerals(self):
        self.assertEqual([c["id"] for c in self.provider.find(request("ドラゴンナイト3"))], ["v2387"])
        self.assertEqual([c["id"] for c in self.provider.find(request("Dragon Knight III"))], ["v2387"])

    def test_a_near_name_must_agree_on_its_numbers(self):
        self.assertEqual(self.provider.find(request("Dragon Knight 4")), [])
        self.assertEqual([c["id"] for c in self.provider.find(request("38 Man Kiro no Kokuu"))], ["v6994"])

    def test_a_machine_vndb_has_no_list_for_is_not_asked(self):
        self.assertEqual(self.provider.find(request("38万キロの虚空", platform="nes")), [])
        self.assertEqual(self.net.urls("vndb"), [])

    def test_describes_the_game(self):
        out = self.provider.details("v6994", request("38万キロの虚空"))
        self.assertEqual(out["title"], "38-man Kilo no Kokuu")
        self.assertEqual(out["originaltitle"], "38万キロの虚空")
        self.assertEqual(out["overview"], "A detective story on the Moon.")
        self.assertEqual((out["year"], out["releasedate"]), (1989, "1989-10-21"))
        self.assertEqual(out["developers"], ["Tokyo Shoseki"])
        self.assertEqual(out["uniqueids"], {"vndb": "v6994"})
        self.assertEqual(out["art"]["boxfront"], [{"url": "https://t.vndb.org/cv/94/6994.jpg"}])

    def test_an_adult_cover_is_used_only_when_the_setting_allows_it(self):
        self.assertNotIn("art", self.provider.details("v29124", request("3つの願い")))
        allowed = self.provider.details("v29124", request("3つの願い", vndb_adult_covers=True))
        self.assertEqual(allowed["art"]["boxfront"], [{"url": "https://t.vndb.org/cv/24/29124.jpg"}])
        self.assertNotIn("releasedate", allowed)


if __name__ == "__main__":
    unittest.main()
