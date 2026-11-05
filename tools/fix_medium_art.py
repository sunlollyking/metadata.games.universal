#!/usr/bin/env python3
"""Rename a medium's picture that was saved as the wrong kind.

Scrapers before 1.0.25 called the picture of every .bin or .img dump's medium a
disc, so a Mega Drive or Atari 2600 cartridge's label was saved as disc art.
On a machine that takes cartridges, each disc, disc1, disc2... becomes the
next free cartridge type of that game.

Scrapers before 1.0.73 called an arcade game's medium a cartridge, and the
picture is of its cabinet. On the arcade platform each cartridge (or disc)
picture becomes the next free cabinet type, after any cabinet it already has.

    fix_medium_art.py DATABASE [--apply]

DATABASE is Kodi's games database (userdata/Database/Games*.db); stop Kodi or
back it up first. Without --apply it only counts. Only the kind of picture
changes; the files stay where they are.
"""
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from resources.lib.providers import ARCADE_PLATFORM, DISC_MACHINE_WORDS  # noqa: E402

NUMBERED = re.compile(r"^(disc|cartridge|cabinet)(\d*)$")


def is_disc_machine(name):
    return bool(set(re.findall(r"[a-z0-9]+", (name or "").lower())) & DISC_MACHINE_WORDS)


def rename(db, platform, sources, target, apply):
    """Give each picture of the kinds in sources the next free target kind"""
    rows = db.execute(
        "select a.art_id, a.media_id, a.type from art a join game g on g.idGame = a.media_id "
        "where a.media_type = 'game' and g.idPlatform = ?", (platform,)).fetchall()
    rows = [row for row in rows if NUMBERED.match(row[2])]
    taken = {}
    for _, game, art_type in rows:
        if NUMBERED.match(art_type).group(1) == target:
            taken.setdefault(game, set()).add(art_type)
    renamed = 0
    for art_id, game, art_type in sorted(rows, key=lambda r: (r[1], r[2])):
        if NUMBERED.match(art_type).group(1) not in sources:
            continue
        used = taken.setdefault(game, set())
        index = 0
        while ("%s%s" % (target, index or "")) in used:
            index += 1
        new_type = "%s%s" % (target, index or "")
        used.add(new_type)
        renamed += 1
        if apply:
            db.execute("update art set type = ? where art_id = ?", (new_type, art_id))
    return renamed


def main(argv):
    apply = "--apply" in argv
    args = [a for a in argv if a != "--apply"]
    if len(args) != 1:
        print(__doc__)
        return 2

    db = sqlite3.connect(args[0], timeout=60)
    # A library that records each machine's medium says which take cartridges;
    # a floppy disk's picture is left as a disc
    has_media = "media" in [column[1] for column in db.execute("pragma table_info(platform)")]
    platforms = db.execute("select idPlatform, slug, name, %s from platform"
                           % ("media" if has_media else "''")).fetchall()
    discs = cabinets = 0
    with db:
        for platform, slug, name, media in platforms:
            if slug == ARCADE_PLATFORM:
                cabinets += rename(db, platform, ("cartridge", "disc"), "cabinet", apply)
            elif (media == "cartridge") if has_media else not is_disc_machine(name):
                discs += rename(db, platform, ("disc",), "cartridge", apply)
        if not apply:
            db.rollback()
    verb = "Renamed" if apply else "Would rename"
    print("%s %d disc pictures of cartridges" % (verb, discs))
    print("%s %d cartridge pictures of arcade cabinets" % (verb, cabinets))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
