#!/usr/bin/env python3
"""File each game as a hack, homebrew or a demo when its files say so.

A game scraped before the scraper read the file's own tags stays "retail"
although its files say "[hack]", "(Aftermarket)" or "(Demo)". A game is only
moved when every one of its files agrees, so one that holds both the original
and a hack stays where it is.

Earlier scrapes also filed a modified dump ("[h1]", "[h Vimm]") as a hack,
which hid the game itself; a hack that neither its files nor the catalogue
record it matched call a game made from another goes back to retail.

    file_categories.py DATABASE [--apply]

Stop Kodi or back the database up first. Without --apply it only counts.
"""
import collections
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from resources.lib import namer  # noqa: E402
from resources.lib.universal import file_category  # noqa: E402


def main(argv):
    apply = "--apply" in argv
    args = [a for a in argv if a != "--apply"]
    if len(args) != 1:
        print(__doc__)
        return 2

    db = sqlite3.connect(args[0], timeout=60)
    files = collections.defaultdict(list)
    for game, name in db.execute(
            "select r.idGame, f.strFilename from gamerelease r "
            "join files f on f.idRelease = r.idRelease "
            "join game g on g.idGame = r.idGame where g.category = 'retail'"):
        files[game].append(name)

    def from_files(names):
        found = {file_category("retail", name) for name in names}
        return found.pop() if len(found) == 1 else "retail"

    moves = {}
    for game, names in files.items():
        category = from_files(names)
        if category != "retail":
            moves[game] = category

    for game, record, names in db.execute(
            "select g.idGame, coalesce((select u.value from uniqueid u where u.media_id = g.idGame "
            "and u.media_type = 'game' and u.type = 'libretro'), ''), "
            "(select group_concat(f.strFilename, '|') from gamerelease r "
            "join files f on f.idRelease = r.idRelease where r.idGame = g.idGame) "
            "from game g where g.category = 'hack'"):
        names = (names or "").split("|")
        if not any(namer.parse(part, strip_extension=False)["hack"] for part in [record] + names if part):
            moves[game] = from_files(names)

    counts = collections.Counter(moves.values())
    print(("moving" if apply else "would move"), dict(counts))
    if apply:
        with db:
            db.executemany("update game set category = ? where idGame = ?",
                           [(category, game) for game, category in moves.items()])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
