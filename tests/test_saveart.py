"""saveart: pictures fetched for Kodi's art folder, signed in where ScreenScraper wants it."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlencode

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, os.path.dirname(TESTS_DIR))
import kodistubs  # noqa: E402

kodistubs.install()

import scraper  # noqa: E402
from fakenet import FakeNet  # noqa: E402
from resources.lib import saveart  # noqa: E402
from resources.lib.providers import screenscraper as ss  # noqa: E402

LOGIN = {"ss_user": "player", "ss_password": "secret"}
SS_FRONT = ("https://neoclone.screenscraper.fr/api2/mediaJeu.php?devid=dev&devpassword=devpass"
            "&softname=kodi&systemeid=4&jeuid=2267&media=box-2D(eu)")
SS_MISSING = SS_FRONT.replace("jeuid=2267", "jeuid=2772")
IGDB_LOGO = "https://images.igdb.com/igdb/image/upload/t_original/abc.png"
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 32


class SignedInTest(unittest.TestCase):
    def test_a_screenscraper_picture_gets_the_login_back(self):
        url = ss.signed_in(SS_FRONT, LOGIN)
        self.assertTrue(url.startswith(SS_FRONT + "&"))
        self.assertIn("ssid=player", url)
        self.assertIn("sspassword=secret", url)

    def test_a_login_already_there_is_not_doubled(self):
        url = ss.signed_in(SS_FRONT + "&ssid=old&sspassword=stale", LOGIN)
        self.assertEqual(url.count("ssid="), 1)
        self.assertNotIn("stale", url)

    def test_other_sites_and_missing_logins_leave_the_url_alone(self):
        self.assertEqual(ss.signed_in(IGDB_LOGO, LOGIN), IGDB_LOGO)
        self.assertEqual(ss.signed_in(SS_FRONT, {"ss_user": "", "ss_password": ""}), SS_FRONT)


class SaveTest(unittest.TestCase):
    def setUp(self):
        self.net = FakeNet().install(self)
        self.folder = tempfile.mkdtemp()
        self.logged = []

    def log(self, msg, error=False):
        self.logged.append(msg)

    def test_each_picture_is_written_under_its_own_kind(self):
        self.net.route("jeuid=2267", PNG, headers={"content-type": "image/png"})
        self.net.route("igdb.com", JPEG, headers={"content-type": "image/jpeg; charset=binary"})
        files = saveart.save([SS_FRONT, IGDB_LOGO], self.folder, LOGIN, self.log)

        self.assertEqual(set(files), {SS_FRONT, IGDB_LOGO})
        self.assertTrue(files[SS_FRONT].endswith(".png"))
        self.assertTrue(files[IGDB_LOGO].endswith(".jpg"))
        with open(files[SS_FRONT], "rb") as f:
            self.assertEqual(f.read(), PNG)
        self.assertTrue(all(os.path.dirname(p) == self.folder for p in files.values()))

    def test_only_screenscraper_is_sent_the_login(self):
        self.net.route("jeuid=2267", PNG, headers={"content-type": "image/png"})
        self.net.route("igdb.com", JPEG, headers={"content-type": "image/jpeg"})
        saveart.save([SS_FRONT, IGDB_LOGO], self.folder, LOGIN, self.log)

        sent = {url.split("?")[0]: url for _, url, _, _ in self.net.calls}
        self.assertIn("sspassword=secret", sent[SS_FRONT.split("?")[0]])
        self.assertNotIn("secret", sent[IGDB_LOGO])

    def test_a_refusal_or_a_missing_picture_saves_nothing(self):
        self.net.route("jeuid=2267", PNG, status=430, headers={"content-type": "image/png"})
        self.net.route("jeuid=2772", "NOMEDIA", headers={"content-type": "text/html"})
        files = saveart.save([SS_FRONT, SS_MISSING], self.folder, LOGIN, self.log)

        self.assertEqual(files, {})
        self.assertEqual(os.listdir(self.folder), [])
        self.assertTrue(self.logged)
        self.assertFalse(any("secret" in line for line in self.logged))

    def test_a_missing_picture_is_told_apart_from_a_refusal(self):
        self.net.route("jeuid=2267", PNG, status=430, headers={"content-type": "image/png"})
        self.net.route("jeuid=2772", "NOMEDIA", headers={"content-type": "text/html"})
        self.assertEqual(saveart.save_one(SS_FRONT, self.folder, LOGIN, self.log), (None, saveart.REFUSED))
        self.assertEqual(saveart.save_one(SS_MISSING, self.folder, LOGIN, self.log), (None, saveart.MISSING))


class ActionTest(unittest.TestCase):
    def setUp(self):
        kodistubs.reset()
        self.net = FakeNet().install(self)
        self.folder = tempfile.mkdtemp()
        patch = mock.patch.object(scraper.xbmcvfs, "translatePath",
                                  lambda path: os.path.join(self.folder, "saved") + "/")
        patch.start()
        self.addCleanup(patch.stop)

    def test_kodi_is_told_which_file_holds_each_picture(self):
        self.net.route("igdb.com", PNG, headers={"content-type": "image/png"})
        batch = os.path.join(self.folder, "batch.json")
        with open(batch, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "art": [IGDB_LOGO]}, f)

        query = {"action": "saveart", "protocol": "1", "batch": batch, "pathSettings": "{}"}
        scraper.main(["plugin://metadata.games.universal/", "3", "?" + urlencode(query)])

        succeeded, item = kodistubs.resolved[3]
        self.assertTrue(succeeded)
        payload = json.loads(item.getProperty("gamelibrary.saved"))
        self.assertEqual(payload["version"], 1)
        self.assertTrue(os.path.isfile(payload["files"][IGDB_LOGO]))


if __name__ == "__main__":
    unittest.main()
