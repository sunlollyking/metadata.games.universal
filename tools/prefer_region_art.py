#!/usr/bin/env python3
"""Put each game's artwork from the preferred regions first.

A library scanned before Kodi chose art by the player's region order shows,
say, a Japanese box where the European one was scraped too. The region of a
stored picture survives only in its address, so it is read from there:
ScreenScraper's media=box-2D(eu), or the region tags in a libretro-thumbnails
file name. Where a better box picture of the same kind is stored, the two
swap places, and the thumb and poster that showed the old one show the new.
ScreenScraper's own pictures, region "ss", are mostly boxes drawn from a
template around a screenshot, and its screen marquees are a game's logo over
its screenshot, so both come after every other picture of their kind.

    prefer_region_art.py DATABASE [--regions Europe,World,USA,Japan]
                         [--originals BACKUP.db ...] [--apply]

DATABASE is Kodi's games database (userdata/Database/Games*.db); stop Kodi or
back it up first. --regions is the order in Kodi's "Region priority" setting.
A picture kept in the artwork folder (keep_art.py) no longer has its address;
--originals names databases from before it was kept, newest first, to read
it from. A kept picture that loses its place gets its address back and its
file is moved to library-art-replaced beside the folder, so that keep_art.py
fetches the new one. Without --apply it only counts.
"""
import collections
import os
import re
import sqlite3
import sys
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from resources.lib.providers.screenscraper import SS_OWN_ART_REGION, SS_OWN_MEDIA, SS_REGION_NAMES  # noqa: E402

DEFAULT_REGIONS = "Europe,World,USA,Japan"
SHOWN_AS = ("thumb", "poster")
#: Only the box and the marquee a cabinet shows: other pictures swapped to the
#: best region would mostly come from ScreenScraper, which is slow and counts
#: every fetch against a quota
KINDS = ("boxfront", "boxback", "boxspine", "box3d", "boxfull", "marquee")
KEPT = "special://profile/library-art/"
_SS = re.compile(r"[?&]media=([^&(]*)\(([a-z]+)\)")
_TAGS = re.compile(r"\(([^)]*)\)")
_NUMBERED = re.compile(r"^(.*?)(\d+)$")
_REGION_WORDS = {name.lower(): name for name in SS_REGION_NAMES.values()}


def region(url):
    """The region a picture's address names, or None."""
    ss = _SS.search(url)
    if ss:
        if ss.group(2) == "ss" or ss.group(1) in SS_OWN_MEDIA:
            return SS_OWN_ART_REGION
        return SS_REGION_NAMES.get(ss.group(2))
    name = urllib.parse.unquote(url.rsplit("/", 1)[-1])
    for tag in _TAGS.findall(name):
        for word in (w.strip() for w in tag.split(",")):
            if word.lower() in _REGION_WORDS:
                return _REGION_WORDS[word.lower()]
    return None


def rank(url, priority):
    """Lower is better. Between two of a region, one ScreenScraper doesn't ration is chosen."""
    found = region(url)
    if found is None:
        place = len(priority) + 1
    elif found == SS_OWN_ART_REGION:
        place = len(priority) + 3
    else:
        place = next((index for index, wanted in enumerate(priority) if wanted.lower() == found.lower()),
                     len(priority) + 2)
    return place, _SS.search(url) is not None


def originals(backups):
    """The addresses older databases held, by game and kind, newest first."""
    found = {}
    for backup in backups:
        old = sqlite3.connect("file:{}?mode=ro".format(backup), uri=True)
        for game, kind, url in old.execute("select media_id, type, url from art where media_type = 'game'"):
            if url.startswith("http"):
                found.setdefault((game, kind), url)
        old.close()
    return found


def real_path(kept, database):
    """A special://profile/ picture as a path on this disk."""
    profile = os.path.dirname(os.path.dirname(os.path.abspath(database)))
    return os.path.join(profile, kept[len("special://profile/"):])


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
    priority = [r.strip() for r in regions.split(",") if r.strip()]
    address = originals(backups)

    db = sqlite3.connect(args[0], timeout=60)
    games = collections.defaultdict(dict)
    for game, kind, url in db.execute("select media_id, type, url from art where media_type = 'game'"):
        games[game][kind] = url

    changed = moved = 0
    with db:
        for game, art in games.items():
            def source(kind):
                """The address a picture came from, kept or not, or None."""
                url = art[kind]
                if url.startswith("http"):
                    return url
                if url.startswith(KEPT):
                    return address.get((game, kind))
                return None

            kinds = collections.defaultdict(list)
            for kind in art:
                numbered = _NUMBERED.match(kind)
                base = numbered.group(1) if numbered and numbered.group(1) in art else kind
                kinds[base].append(kind)
            for base, slots in kinds.items():
                # Art from the collection itself, rather than a scraper, stays
                if base not in KINDS or len(slots) < 2 or source(base) is None:
                    continue
                candidates = [k for k in sorted(slots, key=lambda k: (k != base, k)) if source(k)]
                best = min(candidates, key=lambda k: rank(source(k), priority))
                if best == base or rank(source(best), priority)[0] >= rank(source(base), priority)[0]:
                    continue
                changed += 1
                if not apply:
                    continue
                old, new = art[base], art[best]
                # A kept picture moves back to its address, so its file can make way for the new one
                demoted = source(base)
                db.execute("update art set url = ? where media_type = 'game' and media_id = ? and type = ?",
                           (new, game, base))
                db.execute("update art set url = ? where media_type = 'game' and media_id = ? and type = ?",
                           (demoted, game, best))
                for shown in SHOWN_AS:
                    if art.get(shown) == old:
                        db.execute("update art set url = ? where media_type = 'game' and media_id = ? "
                                   "and type = ?", (new, game, shown))
                        art[shown] = new
                art[base], art[best] = new, demoted
                if old.startswith(KEPT) and old not in art.values():
                    path = real_path(old, args[0])
                    if os.path.isfile(path):
                        aside = real_path(old.replace("library-art/", "library-art-replaced/", 1), args[0])
                        os.makedirs(os.path.dirname(aside), exist_ok=True)
                        os.replace(path, aside)
                        moved += 1
    print(f"{'moved' if apply else 'would move'} a better-region picture first in {changed} places"
          + (f", {moved} kept files set aside" if apply else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
