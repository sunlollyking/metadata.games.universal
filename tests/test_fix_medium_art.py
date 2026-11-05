"""The repair names each medium's picture as the scraper now does."""
import os
import sqlite3
import sys
import tempfile
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, ADDON_DIR)

from tools import fix_medium_art  # noqa: E402


class FixMediumArtTest(unittest.TestCase):

    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        db = sqlite3.connect(self.path)
        db.executescript("""
            create table platform (idPlatform integer primary key, slug text, name text, media text);
            create table game (idGame integer primary key, idPlatform integer);
            create table art (art_id integer primary key, media_id integer, media_type text, type text,
                              url text);
            insert into platform values (1, 'arcade', 'Arcade', 'other'), (2, 'megadrive', 'Sega Mega Drive',
                                         'cartridge'), (3, 'pc98', 'NEC PC-9801', 'disk');
            insert into game values (10, 1), (11, 1), (20, 2), (30, 3);
            insert into art (media_id, media_type, type) values
                (10, 'game', 'cabinet'), (10, 'game', 'cartridge'), (10, 'game', 'cartridge1'),
                (11, 'game', 'cartridge'), (11, 'game', 'boxfront'),
                (20, 'game', 'disc'), (20, 'game', 'cartridge'),
                (30, 'game', 'disc');
        """)
        db.commit()
        db.close()

    def tearDown(self):
        os.remove(self.path)

    def types(self, game):
        db = sqlite3.connect(self.path)
        try:
            return sorted(t for (t,) in db.execute("select type from art where media_id = ?", (game,)))
        finally:
            db.close()

    def test_without_apply_nothing_changes(self):
        fix_medium_art.main([self.path])
        self.assertEqual(self.types(10), ["cabinet", "cartridge", "cartridge1"])

    def test_an_arcade_cartridge_becomes_a_cabinet_after_the_ones_it_has(self):
        fix_medium_art.main([self.path, "--apply"])
        self.assertEqual(self.types(10), ["cabinet", "cabinet1", "cabinet2"])
        self.assertEqual(self.types(11), ["boxfront", "cabinet"])

    def test_a_cartridge_machine_disc_becomes_a_cartridge(self):
        fix_medium_art.main([self.path, "--apply"])
        self.assertEqual(self.types(20), ["cartridge", "cartridge1"])

    def test_a_floppy_disk_stays_a_disc(self):
        fix_medium_art.main([self.path, "--apply"])
        self.assertEqual(self.types(30), ["disc"])


if __name__ == "__main__":
    unittest.main()
