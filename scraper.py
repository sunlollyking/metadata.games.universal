"""Kodi entry point for the universal game scraper (game scraper protocol version 1)."""
import json
import os
import sys
import time
import traceback
from typing import Any, Dict, Optional
from urllib.parse import parse_qs

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from resources.lib import saveart as saveart_lib  # noqa: E402
from resources.lib import universal  # noqa: E402
from resources.lib.providers import Request  # noqa: E402
from resources.lib.providers import (  # noqa: E402
    arcade, arcadedb, igdb, launchbox, libretro, regvault, retroachievements, screenscraper,
    thegamesdb, wikidata)

#: How long a batch may spend on the web before it finishes offline
BATCH_SECONDS = 90

ADDON_ID = "metadata.games.universal"
CACHE_DIR_ENV = "METADATA_GAMES_LIBRETRO_CACHE_DIR"
DEFAULTS: Dict[str, Any] = {
    "provider_order": "libretro,retroachievements,wikidata,igdb,screenscraper,thegamesdb,regvault,launchbox",
    "launchbox_bulk": True,
    "cache_days": 30,
    "download": True,
    "tidy_genres": True,
    "ra_username": "",
    "ra_api_key": "",
    "ss_devid": "",
    "ss_devpassword": "",
    "ss_user": "",
    "ss_password": "",
    "igdb_client_id": "",
    "igdb_client_secret": "",
    "tgdb_api_key": "",
    "tgdb_monthly_lookups": 300,
}

_universal: Optional[universal.Universal] = None
_cache_dir = ""


def log(msg: str, error: bool = False) -> None:
    xbmc.log("[{}] {}".format(ADDON_ID, msg), xbmc.LOGERROR if error else xbmc.LOGDEBUG)


def parse_query(query: str) -> Dict[str, str]:
    if query.startswith("?"):
        query = query[1:]
    return {k: v[0] for k, v in parse_qs(query, keep_blank_values=True).items()}


def settings(query: Dict[str, str]) -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    try:
        values = json.loads(query.get("pathSettings") or "{}")
    except ValueError:
        pass
    if not isinstance(values, dict):
        values = {}
    addon = xbmcaddon.Addon(ADDON_ID)
    out: Dict[str, Any] = {}
    for key, default in DEFAULTS.items():
        value = values.get(key)
        if value is None or value == "":
            value = addon.getSetting(key)
        out[key] = _coerce(value, default)
    return out


def _coerce(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(default, bool):
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes")
        return bool(value)
    if isinstance(default, int):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return str(value).strip()


def scraper() -> universal.Universal:
    global _universal, _cache_dir
    cache_dir = os.environ.get(CACHE_DIR_ENV) or xbmcvfs.translatePath(
        "special://profile/addon_data/{}/rdb/".format(ADDON_ID))
    if _universal is None or _cache_dir != cache_dir:
        libretro_provider = libretro.LibretroProvider(cache_dir, log)
        providers = [
            libretro_provider,
            retroachievements.RetroAchievementsProvider(log, cache_dir),
            screenscraper.ScreenScraperProvider(log, cache_dir),
            igdb.IgdbProvider(log, cache_dir),
            thegamesdb.TheGamesDbProvider(log, cache_dir),
            regvault.RegVaultProvider(log),
            launchbox.LaunchBoxProvider(log, cache_dir),
            wikidata.WikidataProvider(log, cache_dir),
            arcade.ArcadeProvider(
                log, cache_dir,
                installed=lambda addon: bool(
                    xbmc.getCondVisibility("System.HasAddon({})".format(addon))),
                thumbnails=lambda: libretro_provider.store.thumbnails(arcade.THUMB_PLATFORM)),
            arcadedb.ArcadeDbProvider(log, cache_dir),
        ]
        _universal = universal.Universal(providers, log, cache_dir)
        _cache_dir = cache_dir
    return _universal


def request(query: Dict[str, str], bulk: bool = False) -> Request:
    # Kodi says when a call belongs to a scan rather than to one game a person
    # is looking at, so a source with a small allowance can be left out of it
    return Request(query, settings(query), bulk or query.get("bulk") == "1")


def find(handle: int, query: Dict[str, str]) -> None:
    candidates = scraper().find(request(query))
    for cand in candidates:
        cand["platform"] = query.get("platform", "")
        details = cand.pop("details", None)
        item = xbmcgui.ListItem(cand["title"])
        item.setProperty("gamelibrary.candidate", json.dumps(cand))
        if details:
            item.setProperty("gamelibrary.details", json.dumps(details))
        xbmcplugin.addDirectoryItem(handle, url=cand["id"], listitem=item, isFolder=False)
    log("find {!r}: {} candidate(s)".format(query.get("title") or query.get("filename"), len(candidates)))
    xbmcplugin.endOfDirectory(handle)


def findmany(handle: int, query: Dict[str, str]) -> None:
    """One call for a whole folder: the queries arrive in a file, named by index.

    A scan of a full set makes one of these per hundred games instead of one
    call per game, and the round trip is what a scan spends its time on.
    """
    with open(query.get("batch", ""), "r", encoding="utf-8") as handle_file:
        batch = json.load(handle_file)
    queries = batch.get("queries") or []

    shared = {k: v for k, v in query.items() if k in ("platform", "platformids", "settings", "preferredregions")}
    engine = scraper()

    merged_queries = []
    for one in queries:
        merged = dict(shared)
        # Lists, such as a zip's members, stay JSON as they would in a URL
        merged.update({k: json.dumps(v) if isinstance(v, (list, dict)) else str(v)
                       for k, v in one.items() if v not in (None, "")})
        merged_queries.append(merged)

    # A source that can answer the whole folder in one query does so now
    try:
        engine.prefetch([request(m, bulk=True) for m in merged_queries])
    except Exception:
        log("findmany: preparing the batch failed: {}".format(traceback.format_exc()), True)

    found = 0
    engine.begin_batch()
    started = time.time()
    for index, merged in enumerate(merged_queries):
        # A batch that is taking too long finishes from the offline catalogue.
        # A scan of a full set must not stall on a source having a bad day.
        if time.time() - started > BATCH_SECONDS:
            engine.stay_offline()


        try:
            candidates = engine.find(request(merged, bulk=True))
        except Exception:
            log("findmany: query {} failed: {}".format(index, traceback.format_exc()), True)
            continue
        for position, cand in enumerate(candidates):
            cand["platform"] = merged.get("platform", "")
            cand["query"] = index
            details = cand.pop("details", None)

            # The best candidate carries its details, so a scan does not come
            # back a second time for every game. Starting a process for each
            # one costs more than the lookups inside it.
            if details is None and position == 0:
                try:
                    details = engine.details(cand["id"], request(merged, bulk=True))
                except Exception:
                    log("findmany: details for {} failed: {}".format(cand["id"],
                                                                    traceback.format_exc()), True)

            item = xbmcgui.ListItem(cand["title"])
            item.setProperty("gamelibrary.candidate", json.dumps(cand))
            if details:
                item.setProperty("gamelibrary.details", json.dumps(details))
            xbmcplugin.addDirectoryItem(handle, url=cand["id"], listitem=item, isFolder=False)
            found += 1

    # Says the batch was understood, so Kodi knows an empty answer means
    # "nothing matched" rather than "this scraper cannot do batches"
    marker = xbmcgui.ListItem("batch")
    marker.setProperty("gamelibrary.batch", json.dumps({"version": 1, "queries": len(queries)}))
    xbmcplugin.addDirectoryItem(handle, url="batch://done", listitem=marker, isFolder=False)

    log("findmany: {} queries, {} candidate(s)".format(len(queries), found))
    xbmcplugin.endOfDirectory(handle)


def getdetails(handle: int, query: Dict[str, str]) -> None:
    details = scraper().details(query.get("id", ""), request(query))
    if details is None:
        log("getdetails: no record for {!r}".format(query.get("id")), True)
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
        return
    item = xbmcgui.ListItem(details["title"])
    item.setProperty("gamelibrary.details", json.dumps(details))
    xbmcplugin.setResolvedUrl(handle, True, item)


def getplatform(handle: int, query: Dict[str, str]) -> None:
    info = scraper().platform(request(query))
    if info is None:
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
        return
    item = xbmcgui.ListItem(info["name"])
    item.setProperty("gamelibrary.platform", json.dumps(info))
    xbmcplugin.setResolvedUrl(handle, True, item)


def getprogress(handle: int, query: Dict[str, str]) -> None:
    """How far the signed-in person has got with the games they have played.

    About the person rather than about a game, so it is asked for on its own
    and answers for the whole library at once.
    """
    progress = scraper().progress(request(query))
    item = xbmcgui.ListItem("progress")
    item.setProperty("gamelibrary.progress", json.dumps(progress))
    xbmcplugin.setResolvedUrl(handle, True, item)


def saveart(handle: int, query: Dict[str, str]) -> None:
    """Fetch the pictures Kodi keeps in its art folder; Kodi moves each file from here."""
    with open(query.get("batch", ""), "r", encoding="utf-8") as handle_file:
        urls = [u for u in json.load(handle_file).get("art") or [] if isinstance(u, str) and u]
    folder = xbmcvfs.translatePath("special://profile/addon_data/{}/saved/".format(ADDON_ID))
    files = saveart_lib.save(urls, folder, settings(query), log)
    log("saveart: {} of {} picture(s)".format(len(files), len(urls)))
    item = xbmcgui.ListItem("saved")
    item.setProperty("gamelibrary.saved", json.dumps({"version": 1, "files": files}))
    xbmcplugin.setResolvedUrl(handle, True, item)


ACTIONS = {"find": find, "findmany": findmany, "getdetails": getdetails,
           "getplatform": getplatform, "getprogress": getprogress, "saveart": saveart}


def main(argv) -> None:
    handle = -1
    action = ""
    try:
        handle = int(argv[1])
        query = parse_query(argv[2] if len(argv) > 2 else "")
        action = query.get("action", "")
        handler = ACTIONS.get(action)
        if handler is None:
            raise ValueError("unknown action {!r}".format(action))
        handler(handle, query)
    except Exception:
        log("{} failed: {}".format(action or "request", traceback.format_exc()), True)
        if handle >= 0:
            if action in ("getdetails", "getplatform", "getprogress", "saveart"):
                xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
            else:
                xbmcplugin.endOfDirectory(handle, succeeded=False)


if __name__ == "__main__":
    main(sys.argv)
