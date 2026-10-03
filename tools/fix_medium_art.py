#!/usr/bin/env python3
"""Rename a cartridge's label that was saved as a disc.

Scrapers before 1.0.25 called the picture of every .bin or .img dump's medium a
disc, so a Mega Drive or Atari 2600 cartridge's label was saved as disc art.
On a machine whose name has none of the scraper's disc words, each disc,
disc1, disc2... becomes the next free cartridge type of that game.

    fix_medium_art.py DATABASE [--apply]

DATABASE is Kodi's games database (userdata/Database/Games*.db); stop Kodi or
back it up first. Without --apply it only counts.
"""
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from resources.lib.providers import DISC_MACHINE_WORDS  # noqa: E402

NUMBERED = re.compile(r"^(disc|cartridge)(\d*)$")


def is_disc_machine(name):
    return bool(set(re.findall(r"[a-z0-9]+", (name or "").lower())) & DISC_MACHINE_WORDS)


def main(argv):
    apply = "--apply" in argv
    args = [a for a in argv if a != "--apply"]
    if len(args) != 1:
        print(__doc__)
        return 2

    db = sqlite3.connect(args[0], timeout=60)
    cartridge_machines = [pid for pid, name in db.execute("select idPlatform, name from platform")
                          if not is_disc_machine(name)]
    renamed = 0
    with db:
        for pid in cartridge_machines:
            rows = db.execute(
                "select a.art_id, a.media_id, a.type from art a join game g on g.idGame = a.media_id "
                "where a.media_type = 'game' and g.idPlatform = ? and "
                "(a.type like 'disc%' or a.type like 'cartridge%')", (pid,)).fetchall()
            taken = {}
            for _, game, art_type in rows:
                if NUMBERED.match(art_type) and art_type.startswith("cartridge"):
                    taken.setdefault(game, set()).add(art_type)
            for art_id, game, art_type in sorted(rows, key=lambda r: (r[1], r[2])):
                if not NUMBERED.match(art_type) or not art_type.startswith("disc"):
                    continue
                used = taken.setdefault(game, set())
                index = 0
                while ("cartridge%s" % (index or "")) in used:
                    index += 1
                target = "cartridge%s" % (index or "")
                used.add(target)
                renamed += 1
                if apply:
                    db.execute("update art set type = ? where art_id = ?", (target, art_id))
        if not apply:
            db.rollback()
    print("%s %d disc pictures of cartridges" % ("Renamed" if apply else "Would rename", renamed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
