#!/usr/bin/env python3
"""Keep a library's ScreenScraper pictures in Kodi's artwork folder.

ScreenScraper serves a picture to Kodi only while a small daily allowance
lasts, because the links in the library leave the player's sign-in out. Kodi
keeps the pictures it scrapes once its artwork folder is set; this does the
same for a library scraped before that, fetching each picture signed in and
naming it exactly as Kodi would.

    keep_art.py DATABASE FOLDER SETTINGS [--max N] [--apply]

DATABASE is Kodi's games database (userdata/Database/Games*.db). FOLDER is
the artwork folder as Kodi's setting holds it, special://profile/... or a
plain path. SETTINGS is the scraper's settings.xml, for the sign-in.

Without --apply it fetches up to N pictures (default 30000), the ones every
view shows first, and stops early if ScreenScraper keeps refusing; run it
again the next day to go on. Nothing is fetched twice, and a picture
ScreenScraper no longer has is not asked for again. --apply points the
library at every picture fetched so far: stop Kodi and back the database up
first.
"""
import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from resources.lib import saveart  # noqa: E402

HOSTS = ("https://neoclone.screenscraper.fr/", "https://www.screenscraper.fr/",
         "https://api.screenscraper.fr/")
#: Fetched first: the pictures lists, info panels, backgrounds and shelves of spines show
FIRST = ("boxfront", "thumb", "poster", "clearlogo", "fanart", "boxspine")
#: Refusals in a row that mean the day's allowance is spent
GIVE_UP = 25


def real_path(folder, database):
    """FOLDER as a path on this disk, where it is written in Kodi's own form."""
    if folder.startswith("special://profile/"):
        profile = os.path.dirname(os.path.dirname(os.path.abspath(database)))
        return os.path.join(profile, folder[len("special://profile/"):])
    if folder.startswith("special://"):
        raise SystemExit("only special://profile/ can be resolved here: " + folder)
    return folder


def stem(name):
    base, ext = os.path.splitext(name)
    return base if ext else name


def plans(db):
    """For each game, its ScreenScraper pictures: link -> the path, less extension, Kodi would keep it at."""
    sources = {path: slug for path, slug in db.execute(
        "SELECT p.strPath, pl.slug FROM path p JOIN platform pl ON pl.idPlatform = p.idPlatform "
        "WHERE p.idPlatform > 0 AND coalesce(p.exclude, 0) = 0")}

    def source_of(directory):
        folder = directory
        while folder:
            if folder in sources:
                return folder
            parent = folder.rstrip("/").rsplit("/", 1)[0] + "/"
            if parent == folder or len(parent) < 2:
                return None
            folder = parent
        return None

    # Kodi refreshes a game from the first file of its default release
    play = {}
    for game, directory, name in db.execute(
            "SELECT g.idGame, p.strPath, f.strFilename FROM game g JOIN files f ON f.idRelease = "
            "g.idDefaultRelease JOIN path p ON p.idPath = f.idPath ORDER BY g.idGame, f.discNumber, "
            "f.strFilename"):
        play.setdefault(game, (directory, name))

    art = defaultdict(list)
    for game, kind, url in db.execute("SELECT media_id, type, url FROM art WHERE media_type = 'game'"):
        if url.startswith(HOSTS) and kind and not kind[-1].isdigit():
            art[game].append((kind, url))

    out = {}
    for game, pieces in art.items():
        if game not in play:
            continue
        directory, name = play[game]
        source = source_of(directory)
        if source is None:
            continue
        within = directory[len(source):]
        wanted = {}
        for kind, url in sorted(pieces):
            wanted.setdefault(url, (kind, "/".join((sources[source], kind, within + stem(name)))))
        out[game] = wanted
    return out


def fetched(base):
    """The file a picture was kept in, whatever its extension, or None."""
    for ext in saveart.EXTENSIONS.values():
        if os.path.isfile(base + ext):
            return base + ext
    return None


def missing_list(real):
    """Where the pictures ScreenScraper no longer has are remembered, by a digest of their link."""
    return os.path.join(real, ".keep_art-missing")


def digest(url):
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def fetch(db, folder, real, settings, budget):
    try:
        with open(missing_list(real), encoding="utf-8") as f:
            missing = set(f.read().split())
    except OSError:
        missing = set()

    todo = []
    for game, wanted in plans(db).items():
        for url, (kind, relative) in wanted.items():
            if digest(url) not in missing and fetched(os.path.join(real, relative)) is None:
                todo.append((kind not in FIRST, game, url, relative))
    todo.sort()
    print("{} pictures still to fetch; fetching up to {}".format(len(todo), budget))

    os.makedirs(real, exist_ok=True)
    staging = tempfile.mkdtemp(prefix="keep_art-")
    got = refused = gone = 0
    try:
        for _, _, url, relative in todo[:budget]:
            path, why = saveart.save_one(url, staging, settings, lambda msg, error=False: None)
            if path is None:
                # A picture that is not there is not a refusal, and is not asked for again
                if why == saveart.MISSING:
                    gone += 1
                    with open(missing_list(real), "a", encoding="utf-8") as f:
                        f.write(digest(url) + "\n")
                    continue
                refused += 1
                if refused >= GIVE_UP:
                    print("ScreenScraper refused {} in a row; stopping for today".format(refused))
                    break
                continue
            refused = 0
            target = os.path.join(real, relative) + os.path.splitext(path)[1]
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.move(path, target)
            got += 1
            if got % 500 == 0:
                print("fetched", got, flush=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        print("{} no longer on ScreenScraper".format(gone))
        print("fetched {} this run".format(got))


def apply(db, folder, real):
    changed = 0
    with db:
        for game, wanted in plans(db).items():
            kept = {}
            for url, (_, relative) in wanted.items():
                file = fetched(os.path.join(real, relative))
                if file is not None:
                    kept[url] = folder.rstrip("/") + "/" + relative + os.path.splitext(file)[1]
            for url, path in kept.items():
                changed += db.execute("UPDATE art SET url = ? WHERE media_type = 'game' AND media_id = ? "
                                      "AND url = ?", (path, game, url)).rowcount
    print("{} art rows now point at kept pictures".format(changed))


def main(argv):
    do_apply = "--apply" in argv
    budget = 30000
    args = []
    rest = iter(argv)
    for arg in rest:
        if arg == "--apply":
            continue
        if arg == "--max":
            budget = int(next(rest))
            continue
        args.append(arg)
    if len(args) != 3:
        print(__doc__)
        return 2
    database, folder, settings_xml = args

    settings = {e.get("id"): e.text or "" for e in ET.parse(settings_xml).getroot().iter("setting")}
    real = real_path(folder, database)
    if do_apply:
        apply(sqlite3.connect(database, timeout=60), folder, real)
    else:
        fetch(sqlite3.connect("file:{}?mode=ro".format(database), uri=True, timeout=60), folder, real,
              settings, budget)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
