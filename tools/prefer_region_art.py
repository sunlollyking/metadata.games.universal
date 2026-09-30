#!/usr/bin/env python3
"""Put each game's artwork from the preferred regions first.

A library scanned before Kodi chose art by the player's region order shows,
say, a Japanese box where the European one was scraped too. The region of a
stored picture survives only in its address, so it is read from there:
ScreenScraper's media=box-2D(eu), or the region tags in a libretro-thumbnails
file name. Where a better box picture of the same kind is stored, the two
swap places, and the thumb and poster that showed the old one show the new.

    prefer_region_art.py DATABASE [--regions Europe,World,USA,Japan] [--apply]

DATABASE is Kodi's games database (userdata/Database/Games*.db); stop Kodi or
back it up first. --regions is the order in Kodi's "Region priority" setting.
Without --apply it only counts.
"""
import collections
import os
import re
import sqlite3
import sys
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from resources.lib.providers.screenscraper import SS_REGION_NAMES  # noqa: E402

DEFAULT_REGIONS = "Europe,World,USA,Japan"
SHOWN_AS = ("thumb", "poster")
#: Only the box: other pictures swapped to the best region would mostly come
#: from ScreenScraper, which is slow and counts every fetch against a quota
KINDS = ("boxfront", "boxback", "boxspine", "box3d", "boxfull")
_SS = re.compile(r"[?&]media=[^&(]*\(([a-z]+)\)")
_TAGS = re.compile(r"\(([^)]*)\)")
_NUMBERED = re.compile(r"^(.*?)(\d+)$")
_REGION_WORDS = {name.lower(): name for name in SS_REGION_NAMES.values()}


def region(url):
    """The region a picture's address names, or None."""
    ss = _SS.search(url)
    if ss:
        return SS_REGION_NAMES.get(ss.group(1))
    name = urllib.parse.unquote(url.rsplit("/", 1)[-1])
    for tag in _TAGS.findall(name):
        for word in (w.strip() for w in tag.split(",")):
            if word.lower() in _REGION_WORDS:
                return _REGION_WORDS[word.lower()]
    return None


def rank(url, priority):
    found = region(url)
    if found is None:
        return len(priority) + 1
    for index, wanted in enumerate(priority):
        if wanted.lower() == found.lower():
            return index
    return len(priority) + 2


def main(argv):
    apply = "--apply" in argv
    args = [a for a in argv if a != "--apply"]
    regions = DEFAULT_REGIONS
    if "--regions" in args:
        at = args.index("--regions")
        regions = args[at + 1]
        del args[at:at + 2]
    if len(args) != 1:
        print(__doc__)
        return 2
    priority = [r.strip() for r in regions.split(",") if r.strip()]

    db = sqlite3.connect(args[0], timeout=60)
    games = collections.defaultdict(dict)
    for game, kind, url in db.execute("select media_id, type, url from art where media_type = 'game'"):
        games[game][kind] = url

    changed = 0
    with db:
        for game, art in games.items():
            kinds = collections.defaultdict(list)
            for kind in art:
                numbered = _NUMBERED.match(kind)
                base = numbered.group(1) if numbered and numbered.group(1) in art else kind
                kinds[base].append(kind)
            for base, slots in kinds.items():
                # Art from the collection itself, rather than a scraper, stays
                if base not in KINDS or len(slots) < 2 or not art[base].startswith("http"):
                    continue
                best = min(sorted(slots, key=lambda k: (k != base, k)), key=lambda k: rank(art[k], priority))
                if best == base or rank(art[best], priority) >= rank(art[base], priority):
                    continue
                changed += 1
                if not apply:
                    continue
                old, new = art[base], art[best]
                db.execute("update art set url = ? where media_type = 'game' and media_id = ? and type = ?",
                           (new, game, base))
                db.execute("update art set url = ? where media_type = 'game' and media_id = ? and type = ?",
                           (old, game, best))
                for shown in SHOWN_AS:
                    if art.get(shown) == old:
                        db.execute("update art set url = ? where media_type = 'game' and media_id = ? "
                                   "and type = ?", (new, game, shown))
                art[base], art[best] = new, old
    print(f"{'moved' if apply else 'would move'} a better-region picture first in {changed} places")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
