"""RetroAchievements provider against canned API answers."""
import json
import os
import shutil
import sys
import tempfile
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, os.path.dirname(TESTS_DIR))

from fakenet import FakeNet, fixture_json, no_log  # noqa: E402
from resources.lib import net  # noqa: E402
from resources.lib.providers import Request  # noqa: E402
from resources.lib.providers import retroachievements as ra  # noqa: E402

KEYS = {"ra_username": "someone", "ra_api_key": "SECRETKEY"}
MEGADRIVE = {"screenscraper": "1", "libretro": "Sega - Mega Drive - Genesis", "retroachievements": "1"}
NES = {"screenscraper": "3", "libretro": "Nintendo - Nintendo Entertainment System", "retroachievements": "7"}
SONIC2_MD5 = "8e2c29a1e65111fe2078359e685e7943"


def request(platformids=MEGADRIVE, settings=None, **query):
    conf = dict(KEYS)
    conf.update(settings or {})
    q = {"platform": "megadrive", "platformids": json.dumps(platformids)}
    q.update(query)
    return Request(q, conf)


class RetroAchievementsTest(unittest.TestCase):
    def setUp(self):
        self.net = FakeNet().install(self)
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.logged = []
        self.provider = ra.RetroAchievementsProvider(self.log, self.tmp)
        self.net.route(ra.GAME_LIST, fixture_json("ra_gamelist.json"))
        self.net.route(ra.GAME_EXTENDED, fixture_json("ra_game_extended.json"))

    def log(self, msg, error=False):
        self.logged.append((error, msg))

    def test_unavailable_without_keys(self):
        self.assertFalse(self.provider.available({}))
        self.assertFalse(self.provider.available({"ra_username": "someone"}))
        self.assertTrue(self.provider.available(KEYS))

    def test_find_by_rahash(self):
        found = self.provider.find(request(rahash="9FEEB724052C39982D432A7851C98D3E", title="Whatever"))
        self.assertEqual(found, [{"id": "3", "title": "Sonic the Hedgehog 2", "score": 1.0, "matchedby": "hash"}])
        query = self.net.query(ra.GAME_LIST)
        self.assertEqual(query, {"y": "SECRETKEY", "i": "1", "h": "1", "f": "0"})

    def test_md5_stands_in_only_where_it_is_the_ra_hash(self):
        found = self.provider.find(request(md5=SONIC2_MD5, title="Whatever"))
        self.assertEqual([(c["id"], c["matchedby"]) for c in found], [("3", "hash")])
        self.assertEqual(self.provider.find(request(NES, md5=SONIC2_MD5, title="Whatever")), [])
        found = self.provider.find(request(NES, md5=SONIC2_MD5, title="Sonic the Hedgehog 2"))
        self.assertEqual([(c["id"], c["matchedby"]) for c in found], [("3", "name")])

    def test_name_match_only_when_exact(self):
        found = self.provider.find(request(title="Sonic the Hedgehog 2"))
        self.assertEqual(found, [{"id": "3", "title": "Sonic the Hedgehog 2", "score": 0.9, "matchedby": "name"}])
        self.assertEqual([c["id"] for c in self.provider.find(request(title="sonic - the hedgehog"))], ["1"])
        self.assertEqual(self.provider.find(request(title="Sonic")), [])
        self.assertEqual(self.provider.find(request(title="Sonic the Hedgehog 2 Extended")), [])
        self.assertEqual([c["id"] for c in self.provider.find(request(filename="Streets of Rage (USA).md"))], ["44"])

    def test_no_console_id_asks_nothing(self):
        self.assertEqual(self.provider.find(request({"libretro": "x"}, rahash="abc")), [])
        self.assertEqual(self.net.calls, [])

    def test_game_list_cached_per_console(self):
        self.provider.find(request(rahash="9feeb724052c39982d432a7851c98d3e"))
        self.provider.find(request(title="Streets of Rage"))
        self.assertEqual(len(self.net.urls(ra.GAME_LIST)), 1)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "ra", "console_1.json")))
        fresh = ra.RetroAchievementsProvider(no_log, self.tmp)
        self.assertEqual([c["id"] for c in fresh.find(request(title="Streets of Rage"))], ["44"])
        self.assertEqual(len(self.net.urls(ra.GAME_LIST)), 1)

    def test_details(self):
        details = self.provider.details("3", request())
        self.assertEqual(self.net.query(ra.GAME_EXTENDED), {"y": "SECRETKEY", "i": "3"})
        self.assertEqual(details["version"], 1)
        self.assertEqual(details["title"], "Sonic the Hedgehog 2")
        self.assertNotIn("overview", details)
        self.assertEqual(details["developers"], ["Sega Technical Institute"])
        self.assertEqual(details["publishers"], ["Sega"])
        self.assertEqual(details["genres"], ["2D Platforming", "Action"])
        self.assertEqual(details["releasedate"], "1992-11-21")
        self.assertEqual(details["year"], 1992)
        self.assertEqual(details["uniqueids"], {"retroachievements": "3"})
        self.assertEqual(details["art"], {
            "boxfront": [{"url": "https://media.retroachievements.org/Images/032236.png"}],
            "titlescreen": [{"url": "https://media.retroachievements.org/Images/032234.png"}],
            "screenshot": [{"url": "https://media.retroachievements.org/Images/032235.png"}],
            "icon": [{"url": "https://media.retroachievements.org/Images/085574.png"}],
        })
        self.assertEqual(details["achievements"], {"total": 3, "points": 40})
        self.provider.details("3", request())
        self.assertEqual(len(self.net.urls(ra.GAME_EXTENDED)), 1)

    def test_details_placeholder_art_is_left_out(self):
        game = fixture_json("ra_game_extended.json")
        game.update({"ImageBoxArt": "/Images/000002.png", "ImageIcon": "/Images/000001.png",
                     "Released": "1992-11-01", "ReleasedAtGranularity": "month", "Genre": ""})
        self.net.routes = [r for r in self.net.routes if r[0] != ra.GAME_EXTENDED]
        self.net.route(ra.GAME_EXTENDED, game)
        details = self.provider.details("3", request())
        self.assertEqual(sorted(details["art"]), ["screenshot", "titlescreen"])
        self.assertEqual(details["releasedate"], "1992-11")
        self.assertEqual(details["genres"], [])

    def test_release_granularity(self):
        self.assertEqual(ra.release_date("1992-11-21 00:00:00", "day"), "1992-11-21")
        self.assertEqual(ra.release_date("1992-11-21", "month"), "1992-11")
        self.assertEqual(ra.release_date("1992-11-21", "year"), "1992")
        self.assertEqual(ra.release_date("1992-11-21", None), "1992-11-21")
        self.assertEqual(ra.release_date(None, "day"), "")

    def test_details_unknown_game(self):
        self.net.routes = [r for r in self.net.routes if r[0] != ra.GAME_EXTENDED]
        self.net.route(ra.GAME_EXTENDED, [])
        self.assertIsNone(self.provider.details("99999", request()))

    def test_throttled_is_retried_once_then_given_up(self):
        self.net.routes.insert(0, [ra.GAME_LIST, "Too Many Requests", 429, {}, True])
        found = self.provider.find(request(rahash="9feeb724052c39982d432a7851c98d3e"))
        self.assertEqual([c["id"] for c in found], ["3"])
        self.assertEqual(len(self.net.urls(ra.GAME_LIST)), 2)
        # The retry waits; anything after it is the rate limiter pacing calls
        self.assertEqual(self.net.sleeps[0], net.RETRY_AFTER)
        self.assertTrue(all(s < net.RETRY_AFTER for s in self.net.sleeps[1:]))
        self.net.routes.insert(0, [ra.GAME_EXTENDED, "Too Many Requests", 429, {}, False])
        self.assertIsNone(self.provider.details("3", request()))
        self.assertEqual(len(self.net.urls(ra.GAME_EXTENDED)), 2)
        self.assertTrue(any(error for error, _ in self.logged))

    def test_rate_limit_paces_calls(self):
        self.provider.find(request(rahash="deadbeefdeadbeefdeadbeefdeadbeef"))
        self.provider.details("3", request())
        self.assertEqual(len(self.net.sleeps), 1)
        self.assertTrue(0 < self.net.sleeps[0] <= ra.MIN_INTERVAL)

    def test_network_failure_is_logged_without_the_key(self):
        self.net.routes = []
        self.net.route(ra.GAME_LIST, "Unauthorized", status=401)
        self.assertEqual(self.provider.find(request(rahash="9feeb724052c39982d432a7851c98d3e")), [])
        self.assertTrue(any(error and "401" in msg for error, msg in self.logged))
        self.assertFalse(any("SECRETKEY" in msg for _, msg in self.logged))

    def test_platform_is_not_described(self):
        self.assertIsNone(self.provider.platform(request()))


if __name__ == "__main__":
    unittest.main()
