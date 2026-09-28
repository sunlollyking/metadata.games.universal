#!/usr/bin/env python3
"""Give every game in a Kodi games database its genres by their one name.

Each game's genres are read from its own list, passed through the scraper's
genres.normalise(), and written back to both the game's list and the genre
links, so the two agree. Genre names no game uses any more are removed.

    normalise_genres.py DATABASE [--apply]

DATABASE is Kodi's games database (userdata/Database/Games*.db); stop Kodi or
back it up first. The rules are the scraper's own, so the library ends up as a
new scrape would leave it. Without --apply it only counts.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources", "lib"))
import genres  # noqa: E402

LIST_SEPARATOR = " / "


def main(argv):
    apply = "--apply" in argv
    args = [a for a in argv if a != "--apply"]
    if len(args) != 1:
        print(__doc__)
        return 2

    db = sqlite3.connect(args[0], timeout=60)
    before = db.execute("select count(*) from genre").fetchone()[0]
    changed = 0
    with db:
        ids = {name: gid for gid, name in db.execute("select idGenre, name from genre")}
        for game, text in db.execute("select idGame, coalesce(genres, '') from game").fetchall():
            old = [g for g in text.split(LIST_SEPARATOR) if g]
            new = genres.normalise(old)
            linked = {name for (name,) in db.execute(
                "select g.name from genre g join genre_link l on l.idGenre = g.idGenre "
                "where l.idGame = ?", (game,))}
            if new == old and linked == set(new):
                continue
            changed += 1
            if not apply:
                continue
            db.execute("update game set genres = ? where idGame = ?",
                       (LIST_SEPARATOR.join(new), game))
            db.execute("delete from genre_link where idGame = ?", (game,))
            for name in new:
                if name not in ids:
                    ids[name] = db.execute("insert into genre (name) values (?)", (name,)).lastrowid
                db.execute("insert or ignore into genre_link (idGenre, idGame) values (?, ?)",
                           (ids[name], game))
        if apply:
            db.execute("delete from genre where idGenre not in (select idGenre from genre_link)")
    after = db.execute("select count(*) from genre").fetchone()[0]
    print(f"{'changed' if apply else 'would change'} {changed} games; genres {before} -> "
          f"{after if apply else '(unchanged, dry run)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
