#!/usr/bin/env python3
"""Show each arcade game's flyer as its cover, as the scraper now does.

An arcade game came in no box: what catalogues offer as one is drawn by fans or
belongs to a home version. Its cover is the flyer it was sold to arcades with,
the best of a game's flyers by the player's regions. The cover it had moves to
a numbered box slot, so it can still be chosen from the game's information.

    arcade_flyers.py DATABASE [--regions United Kingdom,Europe,World,USA,Japan]
                     [--originals BACKUP.db ...] [--apply]

DATABASE is Kodi's games database; stop Kodi first. A picture kept in the
artwork folder no longer has its address; --originals names databases from
before it was kept, newest first, to read it from. Without --apply it only
counts.
"""
import collections
import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prefer_region_art  # noqa: E402

ARCADE_PLATFORM = "arcade"
SHOWN_AS = ("boxfront", "thumb", "poster")
DEFAULT_REGIONS = "United Kingdom,Europe,World,USA,Japan"
_FLYER = re.compile(r"^flyer\d*$")
_NUMBERED_BOX = re.compile(r"^boxfront(\d+)$")


def main(argv):
    apply = "--apply" in argv
    args = [a for a in argv if a != "--apply"]
    regions = DEFAULT_REGIONS
    if "--regions" in args:
        at = args.index("--regions")
        regions = args[at + 1]
        del args[at:at + 2]
    backups = []
    if "--originals" in args:
        at = args.index("--originals")
        backups = args[at + 1:]
        del args[at:]
    if len(args) != 1:
        print(__doc__)
        return 2
    database = args[0]
    priority = [r.strip() for r in regions.split(",") if r.strip()]
    address = prefer_region_art.originals(backups)

    db = sqlite3.connect(database, timeout=60)
    games = [g for (g,) in db.execute(
        "SELECT idGame FROM game JOIN platform USING (idPlatform) WHERE platform.slug = ?", (ARCADE_PLATFORM,))]
    art = collections.defaultdict(dict)
    for game, kind, url in db.execute("SELECT media_id, type, url FROM art WHERE media_type = 'game'"):
        art[game][kind] = url

    changes = []
    for game in games:
        pictures = art.get(game, {})

        def source(kind):
            url = pictures[kind]
            if url.startswith(prefer_region_art.KEPT):
                return address.get((game, kind), url)
            return url

        flyers = [k for k in pictures if _FLYER.match(k)]
        if not flyers:
            continue
        best = min(flyers, key=lambda k: (prefer_region_art.rank(source(k), priority), k))
        cover = "boxfront" if "boxfront" in pictures else "thumb" if "thumb" in pictures else None
        if cover and source(cover) in {source(k) for k in flyers}:
            continue
        changes.append((game, cover, best))

    print("arcade games: {}; covers to become the flyer: {}".format(len(games), len(changes)))
    if not apply:
        return 0

    backup = "{}.{}-pre-arcade-flyers".format(database, time.strftime("%Y%m%d-%H%M%S"))
    with sqlite3.connect(backup) as copy:
        db.backup(copy)
    with db:
        for game, cover, best in changes:
            pictures = art[game]
            numbered = {k: v for k, v in pictures.items() if _NUMBERED_BOX.match(k)}
            if cover and pictures[cover] not in numbered.values():
                # The cover it had stays one of its boxes
                taken = [int(_NUMBERED_BOX.match(k).group(1)) for k in numbered]
                db.execute("INSERT INTO art (media_id, media_type, type, url) VALUES (?, 'game', ?, ?)",
                           (game, "boxfront{}".format(max(taken, default=0) + 1), pictures[cover]))
            for kind in SHOWN_AS:
                db.execute("DELETE FROM art WHERE media_type = 'game' AND media_id = ? AND type = ?", (game, kind))
                db.execute("INSERT INTO art (media_id, media_type, type, url) VALUES (?, 'game', ?, ?)",
                           (game, kind, pictures[best]))
    print("written; backup {}".format(os.path.basename(backup)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
