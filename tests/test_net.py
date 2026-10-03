"""net: credential-free logging, error reporting, throttling retries and pacing."""
import http.client
import os
import sys
import unittest
from unittest import mock

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, os.path.dirname(TESTS_DIR))

from fakenet import FakeNet  # noqa: E402
from resources.lib import net  # noqa: E402


class SafeUrlTest(unittest.TestCase):
    def test_query_with_a_credential_is_dropped(self):
        self.assertEqual(net.safe_url("https://retroachievements.org/API/API_GetGameList.php?y=SECRET&i=1"),
                         "https://retroachievements.org/API/API_GetGameList.php")
        self.assertEqual(net.safe_url("https://api.thegamesdb.net/v1/Games/ByGameHash?hash=abc&apikey=SECRET"),
                         "https://api.thegamesdb.net/v1/Games/ByGameHash")
        self.assertEqual(net.safe_url("https://id.twitch.tv/oauth2/token?client_id=c&client_secret=s"),
                         "https://id.twitch.tv/oauth2/token")

    def test_harmless_query_is_kept(self):
        url = "https://api.igdb.com/v4/games?limit=5"
        self.assertEqual(net.safe_url(url), url)

    def test_error_text_never_shows_the_credential(self):
        err = net.Error("https://x.test/a?y=SECRET&i=1", 401, "bad key")
        self.assertNotIn("SECRET", str(err))
        self.assertIn("HTTP 401", str(err))


class FetchTest(unittest.TestCase):
    def test_a_download_cut_short_is_a_failure_like_any_other(self):
        with mock.patch("urllib.request.urlopen", side_effect=http.client.IncompleteRead(b"")):
            with self.assertRaises(net.Error):
                net.fetch("GET", "https://x.test/a.png", None, {}, 5)

    def test_a_link_with_a_space_is_sent_encoded(self):
        sent = []

        def urlopen(req, timeout=None):
            sent.append(req.full_url)
            raise OSError("no network in tests")

        with mock.patch("urllib.request.urlopen", side_effect=urlopen):
            with self.assertRaises(net.Error):
                net.fetch("GET", "https://x.test/m.php?media=maps(world map)&crc=1%2B&n=Pokémon", None, {}, 5)
        self.assertEqual(sent, ["https://x.test/m.php?media=maps(world%20map)&crc=1%2B&n=Pok%C3%A9mon"])


class RequestTest(unittest.TestCase):
    def setUp(self):
        self.net = FakeNet().install(self)
        self.logged = []

    def log(self, msg, error=False):
        self.logged.append((error, msg))

    def test_json_answer_and_user_agent(self):
        self.net.route("x.test/ok", {"a": 1})
        self.assertEqual(net.get_json("https://x.test/ok", {"q": "1"}, log=self.log), {"a": 1})
        self.assertEqual(self.net.headers("x.test")["User-Agent"], "Kodi game scraper")
        self.assertEqual(self.net.query("x.test"), {"q": "1"})
        self.assertEqual(self.logged, [(False, "GET https://x.test/ok?q=1 -> 200")])

    def test_error_status_raises(self):
        self.net.route("x.test/missing", "Erreur : Rom/Iso/Dossier non trouvée !", status=404)
        with self.assertRaises(net.Error) as ctx:
            net.get_text("https://x.test/missing", {"apikey": "SECRET"})
        self.assertEqual(ctx.exception.status, 404)
        self.assertIn("non trouv", ctx.exception.body)
        self.assertNotIn("SECRET", str(ctx.exception))

    def test_throttled_is_retried_once(self):
        self.net.route("x.test/busy", "slow down", status=429, once=True)
        self.net.route("x.test/busy", {"ok": True})
        self.assertEqual(net.get_json("https://x.test/busy"), {"ok": True})
        self.assertEqual(len(self.net.calls), 2)
        self.assertEqual(self.net.sleeps, [net.RETRY_AFTER])

    def test_retry_after_header_and_second_throttle_gives_up(self):
        self.net.route("x.test/busy", "slow down", status=430, headers={"retry-after": "7"})
        with self.assertRaises(net.Error) as ctx:
            net.get_json("https://x.test/busy", throttled=(429, 430))
        self.assertEqual(ctx.exception.status, 430)
        self.assertEqual(len(self.net.calls), 2)
        self.assertEqual(self.net.sleeps, [7.0])

    def test_pacing_per_host(self):
        self.net.route("fast.test", {})
        self.net.route("other.test", {})
        net.get_json("https://fast.test/a", min_interval=0.25)
        net.get_json("https://other.test/a", min_interval=0.25)
        self.assertEqual(self.net.sleeps, [])
        net.get_json("https://fast.test/b", min_interval=0.25)
        self.assertEqual(len(self.net.sleeps), 1)
        self.assertTrue(0 < self.net.sleeps[0] <= 0.25)

    def test_post_sends_body(self):
        self.net.route("x.test/post", [])
        net.post_json("https://x.test/post", 'fields id; limit 1;', headers={"Client-ID": "c"})
        method, url, body, headers = self.net.calls[0]
        self.assertEqual((method, body, headers["Client-ID"]), ("POST", 'fields id; limit 1;', "c"))


if __name__ == "__main__":
    unittest.main()
