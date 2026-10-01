"""tools/keep_art.py names each kept picture as Kodi's art folder does."""
import os
import sqlite3
import sys
import tempfile
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(TESTS_DIR), "tools"))
import keep_art  # noqa: E402

SS = "https://neoclone.screenscraper.fr/api2/mediaJeu.php?devid=d&jeuid={}&media={}"


def library():
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE platform (idPlatform INTEGER, slug TEXT);
        CREATE TABLE path (idPath INTEGER, strPath TEXT, idPlatform INTEGER, exclude INTEGER);
        CREATE TABLE game (idGame INTEGER, idDefaultRelease INTEGER);
        CREATE TABLE files (idFile INTEGER, idPath INTEGER, idRelease INTEGER, strFilename TEXT,
                            discNumber INTEGER);
        CREATE TABLE art (media_id INTEGER, media_type TEXT, type TEXT, url TEXT);
        INSERT INTO platform VALUES (1, 'psx');
        INSERT INTO path VALUES (1, '/games/PlayStation/', 1, 0), (2, '/games/PlayStation/Europe/', NULL, 0);
        INSERT INTO game VALUES (7, 70);
        INSERT INTO files VALUES (1, 2, 70, 'Ape Escape (Disc 2).chd', 2), (2, 2, 70, 'Ape Escape (Disc 1).chd', 1);
    """)
    front = SS.format(1, "box-2D")
    db.executemany("INSERT INTO art VALUES (7, 'game', ?, ?)", [
        ("boxfront", front), ("thumb", front), ("poster", front),
        ("fanart", SS.format(1, "fanart")), ("fanart1", SS.format(1, "fanart2")),
        ("screenshot", "https://images.igdb.com/a.jpg")])
    return db, front


class PlansTest(unittest.TestCase):
    def test_a_picture_is_filed_as_kodi_would_file_it(self):
        db, front = library()
        wanted = keep_art.plans(db)[7]

        # The first disc plays, the platform's own folders carry over, and the
        # box front names the picture its thumb and poster share
        self.assertEqual(wanted[front], ("boxfront", "psx/boxfront/Europe/Ape Escape (Disc 1)"))
        self.assertEqual(wanted[SS.format(1, "fanart")][1], "psx/fanart/Europe/Ape Escape (Disc 1)")

    def test_extras_and_other_sources_stay_links(self):
        db, _ = library()
        wanted = keep_art.plans(db)[7]
        self.assertNotIn(SS.format(1, "fanart2"), wanted)
        self.assertNotIn("https://images.igdb.com/a.jpg", wanted)

    def test_apply_points_every_row_of_a_kept_picture_at_the_file(self):
        db, front = library()
        real = tempfile.mkdtemp()
        os.makedirs(os.path.join(real, "psx/boxfront/Europe"))
        open(os.path.join(real, "psx/boxfront/Europe/Ape Escape (Disc 1).png"), "wb").close()

        keep_art.apply(db, "special://profile/library-art/", real)

        kept = "special://profile/library-art/psx/boxfront/Europe/Ape Escape (Disc 1).png"
        rows = dict(db.execute("SELECT type, url FROM art WHERE media_id = 7"))
        self.assertEqual((rows["boxfront"], rows["thumb"], rows["poster"]), (kept, kept, kept))
        self.assertEqual(rows["fanart"], SS.format(1, "fanart"))


if __name__ == "__main__":
    unittest.main()
