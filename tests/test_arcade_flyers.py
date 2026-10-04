"""arcade_flyers.py shows an arcade game's flyer as its cover and keeps the box it had."""
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

import arcade_flyers  # noqa: E402

BOX = "https://images.launchbox-app.com/box.png"
FLYER = "https://images.launchbox-app.com/flyer.png"


class ArcadeFlyersTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "Games.db")
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TABLE platform (idPlatform INTEGER, slug TEXT)")
            db.execute("CREATE TABLE game (idGame INTEGER, idPlatform INTEGER)")
            db.execute("CREATE TABLE art (media_id INTEGER, media_type TEXT, type TEXT, url TEXT)")
            db.executemany("INSERT INTO platform VALUES (?, ?)", [(1, "arcade"), (2, "neogeo")])
            db.executemany("INSERT INTO game VALUES (?, ?)", [(10, 1), (20, 2), (30, 1)])
            for game in (10, 20):
                db.executemany("INSERT INTO art VALUES (?, 'game', ?, ?)",
                               [(game, k, BOX) for k in ("boxfront", "thumb", "poster")] + [(game, "flyer", FLYER)])
            db.executemany("INSERT INTO art VALUES (30, 'game', ?, ?)",
                           [(k, FLYER) for k in ("boxfront", "thumb", "poster", "flyer")])

    def art(self, game):
        with sqlite3.connect(self.db) as db:
            return dict(db.execute("SELECT type, url FROM art WHERE media_id = ?", (game,)))

    def test_the_flyer_becomes_the_cover_and_the_box_is_kept(self):
        arcade_flyers.main([self.db, "--apply"])
        self.assertEqual(self.art(10), {"boxfront": FLYER, "thumb": FLYER, "poster": FLYER,
                                        "flyer": FLYER, "boxfront1": BOX})

    def test_another_platform_keeps_its_box(self):
        arcade_flyers.main([self.db, "--apply"])
        self.assertEqual(self.art(20)["boxfront"], BOX)

    def test_a_game_already_showing_its_flyer_is_left_alone(self):
        arcade_flyers.main([self.db, "--apply"])
        self.assertNotIn("boxfront1", self.art(30))


if __name__ == "__main__":
    unittest.main()
