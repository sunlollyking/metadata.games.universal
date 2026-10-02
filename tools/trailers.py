"""Give the games in a library trailers that play, without scraping it again.

Older versions of the scraper stored ScreenScraper's videos as trailers, as
links without the user's login, which the service refuses once its shared
allowance is spent. This points each game that has no trailer, or one of those,
at ArcadeDB's recording of an arcade set, or else at IGDB's trailer through
the YouTube add-on. A game neither has keeps its link unless asked to clear it,
so a skin stops offering a trailer that cannot play.

  trailers.py DATABASE SETTINGS                          say what would change
  trailers.py DATABASE SETTINGS --apply [--clear-dead]   back the database up, then write

DATABASE is Kodi's Games*.db and SETTINGS the scraper's settings.xml, for the
IGDB keys.
"""
import json
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from resources.lib.providers import arcadedb, igdb  # noqa: E402

DEAD = "screenscraper.fr/api2/mediaVideoJeu.php"
USER_AGENT = "Kodi metadata.games.universal"
#: Sets ArcadeDB is asked about at once, and IGDB games
ARCADE_BATCH = 50
IGDB_BATCH = 500


def fetch_json(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=dict({"User-Agent": USER_AGENT}, **(headers or {})))
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def arcade_clips(sets):
    """ArcadeDB's recording of each set, by set name."""
    out = {}
    sets = sorted(sets)
    for i in range(0, len(sets), ARCADE_BATCH):
        query = urllib.parse.urlencode({"ajax": "query_mame", "game_name": ";".join(sets[i:i + ARCADE_BATCH]),
                                        "lang": "en"})
        for row in fetch_json(arcadedb.API + "?" + query).get("result") or []:
            clip = row.get("url_video_shortplay_hd") or row.get("url_video_shortplay")
            if clip:
                out[row.get("game_name")] = clip
        time.sleep(arcadedb.MIN_INTERVAL)
    return out


def igdb_trailers(ids, settings):
    """IGDB's trailer for each game, by IGDB id, as Kodi plays it."""
    query = urllib.parse.urlencode({"client_id": settings["igdb_client_id"],
                                    "client_secret": settings["igdb_client_secret"],
                                    "grant_type": "client_credentials"})
    token = fetch_json(igdb.TOKEN_URL + "?" + query, data=b"")["access_token"]
    headers = {"Client-ID": settings["igdb_client_id"], "Authorization": "Bearer " + token}
    out = {}
    ids = sorted(ids)
    for i in range(0, len(ids), IGDB_BATCH):
        body = "fields id,videos.video_id,videos.name; where id = ({}); limit {};".format(
            ",".join(map(str, ids[i:i + IGDB_BATCH])), IGDB_BATCH)
        for game in fetch_json("https://api.igdb.com/v4/games", data=body.encode(), headers=headers):
            trailer = igdb.game_details(game, "").get("trailer")
            if trailer:
                out[str(game["id"])] = trailer
        time.sleep(0.3)
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        sys.exit(__doc__)
    database, settings_path = args
    settings = {e.get("id"): e.text or "" for e in ET.parse(settings_path).getroot().iter("setting")}

    db = sqlite3.connect(database, timeout=60)
    wanted = {}
    for game_id, trailer in db.execute("SELECT idGame, trailer FROM game"):
        if not trailer or DEAD in trailer:
            wanted[game_id] = trailer or ""
    ids = {}
    for game_id, kind, value in db.execute(
            "SELECT media_id, type, value FROM uniqueid WHERE media_type = 'game' AND type IN ('arcade', 'igdb')"):
        if game_id in wanted and value:
            ids.setdefault(game_id, {})[kind] = value

    clips = arcade_clips({i["arcade"] for i in ids.values() if "arcade" in i})
    trailers = igdb_trailers({i["igdb"] for i in ids.values() if i.get("igdb", "").isdigit()}, settings) \
        if settings.get("igdb_client_id") and settings.get("igdb_client_secret") else {}

    changes = []
    for game_id, known in ids.items():
        trailer = clips.get(known.get("arcade")) or trailers.get(known.get("igdb"))
        if trailer:
            changes.append((trailer, game_id))
    found = {game_id for _, game_id in changes}
    if "--clear-dead" in sys.argv:
        changes += [("", game_id) for game_id, trailer in wanted.items() if trailer and game_id not in found]
    dead = sum(1 for t in wanted.values() if t)
    replaced = sum(1 for game_id in found if wanted[game_id])
    print("games without a working trailer: {} ({} with a dead link)".format(len(wanted), dead))
    print("trailers found: {} from ArcadeDB, {} from IGDB; {} replace a dead link".format(
        sum(1 for t, _ in changes if t.startswith("https://adb.")), sum(1 for t, _ in changes if t.startswith("plugin:")),
        replaced))
    print("dead links left: {}{}".format(dead - replaced, ", to be cleared" if "--clear-dead" in sys.argv else ""))

    if "--apply" in sys.argv:
        backup = "{}.{}-pre-trailers".format(database, time.strftime("%Y%m%d-%H%M%S"))
        with sqlite3.connect(backup) as copy:
            db.backup(copy)
        with db:
            db.executemany("UPDATE game SET trailer = ? WHERE idGame = ?", changes)
        print("written {}; backup {}".format(len(changes), os.path.basename(backup)))


if __name__ == "__main__":
    main()
