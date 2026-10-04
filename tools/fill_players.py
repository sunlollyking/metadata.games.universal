"""Give the games in a library their co-op play and player counts, without scraping it again.

Co-op play never reached the library: LaunchBox's flag was filed inside the
player count, where Kodi does not look, and no second source was asked for it.
This reads it from the LaunchBox catalogue the scraper keeps and from IGDB's
multiplayer modes for the game's platform. A game is marked co-op when either
says it can be played together on one machine, and a game with no player count
is given one. Nothing already in the library is taken away.

  fill_players.py DATABASE SETTINGS             say what would change
  fill_players.py DATABASE SETTINGS --apply     back the database up, then write

DATABASE is Kodi's Games*.db and SETTINGS the scraper's settings.xml, for the
IGDB keys. The LaunchBox catalogue is read from rdb/launchbox beside SETTINGS.
"""
import collections
import json
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from resources.lib.providers import igdb  # noqa: E402
from resources.lib.providers.launchbox import INDEX_NAME  # noqa: E402

USER_AGENT = "Kodi metadata.games.universal"
IGDB_BATCH = 500
LAUNCHBOX_BATCH = 900


def fetch_json(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=dict({"User-Agent": USER_AGENT}, **(headers or {})))
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def igdb_games(ids, settings):
    """Each game's multiplayer modes, by IGDB id."""
    query = urllib.parse.urlencode({"client_id": settings["igdb_client_id"],
                                    "client_secret": settings["igdb_client_secret"],
                                    "grant_type": "client_credentials"})
    token = fetch_json(igdb.TOKEN_URL + "?" + query, data=b"")["access_token"]
    headers = {"Client-ID": settings["igdb_client_id"], "Authorization": "Bearer " + token}
    out = {}
    ids = sorted(ids)
    for i in range(0, len(ids), IGDB_BATCH):
        body = ("fields id,multiplayer_modes.offlinemax,multiplayer_modes.offlinecoop,"
                "multiplayer_modes.platform; where id = ({}); limit {};").format(
                    ",".join(ids[i:i + IGDB_BATCH]), IGDB_BATCH)
        for game in fetch_json("https://api.igdb.com/v4/games", data=body.encode(), headers=headers):
            out[str(game["id"])] = game
        time.sleep(0.3)
    return out


def launchbox_games(ids, index_path):
    """Each game's player count and co-op flag, by LaunchBox id."""
    out = {}
    if not os.path.isfile(index_path):
        return out
    index = sqlite3.connect("file:{}?mode=ro".format(index_path), uri=True)
    ids = sorted(int(i) for i in ids if i.isdigit())
    for i in range(0, len(ids), LAUNCHBOX_BATCH):
        batch = ids[i:i + LAUNCHBOX_BATCH]
        for game_id, players, cooperative in index.execute(
                "SELECT id, players, cooperative FROM game WHERE id IN ({})".format(",".join("?" * len(batch))),
                batch):
            out[str(game_id)] = (players or 0, bool(cooperative))
    index.close()
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        sys.exit(__doc__)
    database, settings_path = args
    settings = {e.get("id"): e.text or "" for e in ET.parse(settings_path).getroot().iter("setting")}
    index_path = os.path.join(os.path.dirname(os.path.abspath(settings_path)), "rdb", "launchbox", INDEX_NAME)

    db = sqlite3.connect(database, timeout=60)
    platform_igdb = {platform: value for platform, value in db.execute(
        "SELECT media_id, value FROM uniqueid WHERE media_type = 'platform' AND type = 'igdb'")}
    slugs = dict(db.execute("SELECT idPlatform, slug FROM platform"))
    games = {game: (platform, low or 0, high or 0, bool(coop)) for game, platform, low, high, coop in db.execute(
        "SELECT idGame, idPlatform, playersMin, playersMax, coop FROM game")}
    ids = collections.defaultdict(dict)
    for game, kind, value in db.execute(
            "SELECT media_id, type, value FROM uniqueid WHERE media_type = 'game' AND type IN ('igdb', 'launchbox')"):
        if game in games and value:
            ids[game][kind] = value

    from_igdb = igdb_games({i["igdb"] for i in ids.values() if i.get("igdb", "").isdigit()}, settings) \
        if settings.get("igdb_client_id") and settings.get("igdb_client_secret") else {}
    from_launchbox = launchbox_games({i["launchbox"] for i in ids.values() if "launchbox" in i}, index_path)

    changes = []
    coop_by = collections.Counter()
    filled_by = collections.Counter()
    per_platform = collections.Counter()
    for game, known in ids.items():
        platform, low, high, coop = games[game]
        mode = igdb.multiplayer(from_igdb.get(known.get("igdb"), {}), platform_igdb.get(platform, ""))
        lb_players, lb_coop = from_launchbox.get(known.get("launchbox"), (0, False))
        igdb_coop = bool(mode and mode.get("offlinecoop"))
        new_coop = coop or igdb_coop or lb_coop
        new_low, new_high = low, high
        if high <= 0:
            igdb_max = mode.get("offlinemax") if mode else None
            if isinstance(igdb_max, int) and igdb_max > 0:
                new_low, new_high = 1, igdb_max
                filled_by["IGDB"] += 1
            elif lb_players > 0:
                new_low, new_high = 1, lb_players
                filled_by["LaunchBox"] += 1
        if new_coop and not coop:
            coop_by["IGDB and LaunchBox" if igdb_coop and lb_coop else "IGDB" if igdb_coop else "LaunchBox"] += 1
            per_platform[slugs.get(platform, "?")] += 1
        if (new_low, new_high, new_coop) != (low, high, coop):
            changes.append((new_low, new_high, int(new_coop), game))

    print("IGDB answered for {} games, LaunchBox for {}".format(len(from_igdb), len(from_launchbox)))
    print("newly co-op: {} ({})".format(sum(coop_by.values()),
                                       ", ".join("{} {}".format(n, k) for k, n in coop_by.most_common())))
    print("  most on: " + ", ".join("{} {}".format(k, n) for k, n in per_platform.most_common(12)))
    print("player counts filled: {} ({})".format(sum(filled_by.values()),
                                                 ", ".join("{} {}".format(n, k) for k, n in filled_by.items())))

    if "--apply" in sys.argv:
        backup = "{}.{}-pre-players".format(database, time.strftime("%Y%m%d-%H%M%S"))
        with sqlite3.connect(backup) as copy:
            db.backup(copy)
        with db:
            db.executemany("UPDATE game SET playersMin = ?, playersMax = ?, coop = ? WHERE idGame = ?", changes)
        print("written {}; backup {}".format(len(changes), os.path.basename(backup)))


if __name__ == "__main__":
    main()
