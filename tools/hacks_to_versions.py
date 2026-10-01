#!/usr/bin/env python3
"""Make hacks and fan translations versions of their game in an existing library.

A library scanned before Kodi kept hacks and fan translations as versions put
"Mod" or "Fan Translation" on the game, filed a hack it could not place as a
game of its own, and gave a hack the catalogue's name for the dump. Now:

- what a dump is made from its game as goes on the version, from its file's
  tags, and a game keeps it only where it is a hack of nothing the library has;
- a hack named as a game of its own is labelled by that name;
- a hack game whose title is exactly one other game's on its platform becomes
  a version of that game.

    hacks_to_versions.py DATABASE [--apply]

DATABASE is Kodi's games database from schema 8 on (userdata/Database/Games8.db
or later); stop Kodi or back it up first. Without --apply it only counts.
"""
import collections
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources", "lib"))
import namer  # noqa: E402

DERIVED = ("Mod", "Fan Translation")


def key(title):
    return namer.normalise(namer.without_revision(title))


def edition_of(names):
    """What the names of a version's files and of the version say it is made as."""
    for name in names:
        tags = namer.parse(name or "")
        if tags["hack"] or tags["modified"]:
            return "Mod"
        if tags["translation"]:
            return "Fan Translation"
    return ""


def main(argv):
    apply = "--apply" in argv
    args = [a for a in argv if a != "--apply"]
    if len(args) != 1:
        print(__doc__)
        return 2

    db = sqlite3.connect(args[0], timeout=60)
    if "edition" not in {row[1] for row in db.execute("pragma table_info(gamerelease)")}:
        print("this database has no version editions; start the Kodi that upgrades it first")
        return 2

    games = {gid: {"platform": platform, "title": title, "category": category or "retail",
                   "edition": edition or ""}
             for gid, platform, title, category, edition in db.execute(
                 "select idGame, idPlatform, title, category, edition from game")}
    versions = collections.defaultdict(list)
    for rid, gid, title, edition, licence in db.execute(
            "select idRelease, idGame, title, coalesce(edition, ''), coalesce(licence, '') "
            "from gamerelease"):
        versions[gid].append({"id": rid, "title": title or "", "edition": edition,
                              "licence": licence})
    files = collections.defaultdict(list)
    for rid, name in db.execute("select idRelease, strFilename from files"):
        files[rid].append(name)

    by_title = collections.defaultdict(list)
    for gid, game in games.items():
        if game["category"] != "hack":
            by_title[(game["platform"], key(game["title"]))].append(gid)

    marked = renamed = moved = folded = 0
    release_updates, licence_updates, game_updates, moves, drops = [], [], [], [], []
    for gid, game in games.items():
        own = versions.get(gid, [])
        parent = None
        if game["category"] == "hack":
            matches = by_title.get((game["platform"], key(game["title"])), [])
            parent = matches[0] if len(matches) == 1 else None

        for version in own:
            # A bootleg, as an arcade list names one, is a pirate copy
            if version["licence"] in ("", "licensed") and \
                    namer.parse(version["title"], strip_extension=False)["licence"] == "pirate":
                licence_updates.append(version["id"])
            tagged = edition_of(files[version["id"]] + [version["title"]])
            edition = version["edition"] or tagged
            if not edition and (parent or (game["edition"] in DERIVED and len(own) == 1)):
                edition = game["edition"] if game["edition"] in DERIVED else "Mod"
            if not edition:
                continue
            title = version["title"]
            # Only a dump whose tags call it a hack is named as one
            if edition == "Mod" and tagged == "Mod":
                target = games[parent]["title"] if parent else game["title"]
                named = namer.hack_name(title, (files[version["id"]] or [""])[0], target)
                if named and named != title:
                    title = named
                    renamed += 1
            if edition != version["edition"] or title != version["title"]:
                if edition != version["edition"]:
                    marked += 1
                release_updates.append((edition, title, version["id"]))

        if parent:
            folded += 1
            moved += len(own)
            moves.append((parent, gid))
            drops.append(gid)
        elif game["edition"] in DERIVED and game["category"] != "hack":
            # The game is the one it was made from; the dump says what it is
            game_updates.append(gid)

    if apply:
        with db:
            db.executemany("update gamerelease set edition = ?, title = ? where idRelease = ?",
                           release_updates)
            db.executemany("update gamerelease set licence = 'pirate' where idRelease = ?",
                           [(rid,) for rid in licence_updates])
            db.executemany("update game set edition = '' where idGame = ?",
                           [(gid,) for gid in game_updates])
            db.executemany("update gamerelease set idGame = ? where idGame = ?", moves)
            db.executemany("delete from game where idGame = ?", [(gid,) for gid in drops])
    verb = "" if apply else "would "
    print(f"{verb}mark {marked} versions as hacks or fan translations and {len(licence_updates)} "
          f"as bootlegs, name {renamed} hacks by "
          f"their own title, take the edition off {len(game_updates)} games, and fold {folded} "
          f"hack games ({moved} versions) into their game")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
