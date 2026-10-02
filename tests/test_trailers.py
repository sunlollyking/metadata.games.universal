"""tools/trailers.py: a library's dead or missing trailers pointed at ones that play."""
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(TESTS_DIR), "tools"))

import trailers  # noqa: E402

DEAD = "https://neoclone.screenscraper.fr/api2/mediaVideoJeu.php?jeuid=1"
CLIP = "https://adb.arcadeitalia.net/download_file.php?codice=galaga"


def answer(url, data=None, headers=None):
    if "adb.arcadeitalia.net" in url:
        return {"result": [{"game_name": "galaga", "url_video_shortplay_hd": CLIP}]}
    if "oauth2" in url:
        return {"access_token": "t"}
    return [{"id": 7, "videos": [{"video_id": "yt7", "name": "Trailer"}]}]


class TrailersTest(unittest.TestCase):
    def test_dead_and_missing_trailers_are_replaced_and_the_rest_left(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = temporary.name
        database = os.path.join(folder, "Games8.db")
        settings = os.path.join(folder, "settings.xml")
        with open(settings, "w") as f:
            f.write('<settings><setting id="igdb_client_id">i</setting>'
                    '<setting id="igdb_client_secret">s</setting></settings>')
        db = sqlite3.connect(database)
        db.executescript("CREATE TABLE game (idGame INTEGER, trailer TEXT);"
                         "CREATE TABLE uniqueid (media_id INTEGER, media_type TEXT, type TEXT, value TEXT);")
        db.executemany("INSERT INTO game VALUES (?, ?)",
                       [(1, DEAD), (2, ""), (3, DEAD), (4, "plugin://kept")])
        db.executemany("INSERT INTO uniqueid VALUES (?, 'game', ?, ?)",
                       [(1, "arcade", "galaga"), (1, "igdb", "7"), (2, "igdb", "7"), (4, "igdb", "7")])
        db.commit()
        with mock.patch.object(trailers, "fetch_json", answer), mock.patch.object(trailers.time, "sleep"), \
                mock.patch.object(sys, "argv", ["trailers.py", database, settings, "--apply"]):
            trailers.main()
        got = dict(sqlite3.connect(database).execute("SELECT idGame, trailer FROM game"))
        self.assertEqual(got[1], CLIP, "an arcade set's own recording comes first")
        self.assertEqual(got[2], "plugin://plugin.video.youtube/play/?video_id=yt7")
        self.assertEqual(got[3], DEAD, "a game with nothing better is left alone")
        self.assertEqual(got[4], "plugin://kept", "a working trailer is not touched")

        with mock.patch.object(trailers, "fetch_json", answer), mock.patch.object(trailers.time, "sleep"), \
                mock.patch.object(sys, "argv", ["trailers.py", database, settings, "--apply", "--clear-dead"]):
            trailers.main()
        got = dict(sqlite3.connect(database).execute("SELECT idGame, trailer FROM game"))
        self.assertEqual(got[3], "", "asked to, a dead link with nothing better is cleared")
        self.assertEqual(got[4], "plugin://kept")


if __name__ == "__main__":
    unittest.main()
