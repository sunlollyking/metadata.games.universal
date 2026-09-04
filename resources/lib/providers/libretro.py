"""Offline game identification against libretro-database, with libretro-thumbnails art URLs.

A Catalogue is one platform's RDB file indexed by hash, serial and normalised
title. Store fetches and caches RDB files and keeps loaded catalogues for the
life of the process. LibretroProvider is the Provider facade over a Store;
its candidate ids are the catalogue names. The platform id it reads is the
``libretro`` entry of platformids, the RDB file name without extension.
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional

from .. import namer
from .. import rdb
from . import Provider, Request

RDB_URL = "https://raw.githubusercontent.com/libretro/libretro-database/master/rdb/{}.rdb"
THUMB_INDEX_URL = "https://api.github.com/repos/libretro-thumbnails/{}/git/trees/master?recursive=1"
THUMB_URL = "https://raw.githubusercontent.com/libretro-thumbnails/{}/master/{}/{}.png"
ART_FOLDERS = (("boxfront", "Named_Boxarts"), ("titlescreen", "Named_Titles"), ("screenshot", "Named_Snaps"))
THUMB_UNSAFE = str.maketrans({c: "_" for c in '&*/:`<>?\\|"'})
#: RetroArch ships an icon for every machine it runs, named exactly as the
#: catalogues are, which is the one picture of a system available without a key
SYSTEM_ICON_INDEX_URL = "https://api.github.com/repos/libretro/retroarch-assets/git/trees/master?recursive=1"
SYSTEM_ICON_URL = "https://raw.githubusercontent.com/libretro/retroarch-assets/master/{}/{}.png"
SYSTEM_ICON_FOLDERS = ("xmb/monochrome/png", "xmb/flatui/png")
GENRE_SPLIT = re.compile(r"\s*/\s*|,\s*")
NOT_SERIAL = re.compile(r"[^A-Z0-9]")
AGE_BOARDS = (("esrb_rating", "ESRB"), ("elspa_rating", "ELSPA"), ("pegi_rating", "PEGI"),
              ("cero_rating", "CERO"), ("bbfc_rating", "BBFC"))
RATINGS = (("edge_rating", "edge", 10), ("famitsu_rating", "famitsu", 40))
STATUS_WORDS = {"beta", "proto", "sample", "demo", "alpha", "kiosk", "debug", "program"}
USER_AGENT = "Kodi metadata.games.universal"
Log = Callable[[str, bool], None]


def serial_keys(serial: str) -> List[str]:
    """The forms one serial can be written in, best first.

    A catalogue and a disc rarely spell it the same way. Sega prints "MK-51035"
    in the header of its own discs and the catalogue records "51035"; a
    multi-disc set is recorded as "T-33005G-1" where every disc says
    "T-33005G". Both are the same game, so both spellings are indexed and both
    are asked for.
    """
    if not serial:
        return []

    keys = [serial]

    # A disc number the catalogue adds and the disc itself does not carry
    base = re.sub(r"[0-9]$", "", serial) if re.search(r"[A-Z][0-9]$", serial) else serial
    if base != serial and len(base) > 3:
        keys.append(base)

    # Sega's own prefix, printed on the disc and left out of the catalogue
    if serial.startswith("MK") and serial[2:].isdigit():
        keys.append(serial[2:])
    elif serial.isdigit():
        keys.append("MK" + serial)

    return keys


def norm_serial(serial: Any) -> str:
    """One comparable key: letters and digits only, upper case, no version suffix."""
    if isinstance(serial, (bytes, bytearray)):
        serial = bytes(serial).decode("ascii", "replace")
    if not serial:
        return ""
    s = serial.strip()
    if s.startswith("GM "):
        s = s[3:].strip()
    s = s.split()[0] if s else ""
    return NOT_SERIAL.sub("", s.upper())


def name_key(name: str) -> str:
    return namer.normalise(namer.parse(name, strip_extension=False)["title"])


def thumbnail_name(name: str) -> str:
    return name.translate(THUMB_UNSAFE)


def art_urls(platform_name: str, name: str, region: Optional[str],
             held: Optional[Dict[str, set]] = None) -> Dict[str, List[Dict[str, str]]]:
    """The pictures for one game.

    ``held`` is what the thumbnail repository actually has, folder by folder.
    Without it every URL is offered and the ones that do not exist answer 404,
    which is how a library ends up with games whose cover never loads.
    """
    repo = platform_name.replace(" ", "_")
    plain = thumbnail_name(name)
    filename = urllib.parse.quote(plain)
    art: Dict[str, List[Dict[str, str]]] = {}
    for art_type, folder in ART_FOLDERS:
        if held is not None and plain not in held.get(folder, ()):
            continue
        entry = {"url": THUMB_URL.format(repo, folder, filename)}
        if art_type == "boxfront" and region:
            entry["region"] = region
        art[art_type] = [entry]
    return art


class Catalogue:
    """One platform's records, indexed for lookup."""

    def __init__(self, platform_name: str):
        self.platform_name = platform_name
        self.held_pictures: Optional[Dict[str, set]] = None
        self.count = 0
        self.crc: Dict[str, dict] = {}
        self.md5: Dict[str, dict] = {}
        self.sha1: Dict[str, dict] = {}
        self.serial: Dict[str, dict] = {}
        self.by_key: Dict[str, List[dict]] = defaultdict(list)
        self.by_name: Dict[str, List[dict]] = defaultdict(list)

    def load(self, path: str) -> None:
        for rec in rdb.records(path):
            self.add(rec)

    def add(self, rec: dict) -> None:
        name = rec.get("name")
        if not isinstance(name, str) or not name:
            return
        self.count += 1
        for field, index in (("crc", self.crc), ("md5", self.md5), ("sha1", self.sha1)):
            value = rdb.hexfield(rec, field)
            if value:
                index.setdefault(value, rec)
        for key in serial_keys(norm_serial(rec.get("serial"))):
            self.serial.setdefault(key, rec)
        self.by_key[name_key(name)].append(rec)
        self.by_name[name].append(rec)

    def find(self, query: Dict[str, str]) -> List[dict]:
        """Candidates for the identity in query, best first; empty when nothing matches."""
        for param, index in (("crc32", self.crc), ("md5", self.md5), ("sha1", self.sha1)):
            value = query.get(param, "").strip().lower()
            if value and value in index:
                return [candidate(index[value], 1.0, "hash")]
        serial = norm_serial(query.get("serial"))
        if serial:
            rec = None
            for key in serial_keys(serial):
                rec = self.serial.get(key)
                if rec is not None:
                    break
            if rec is None and len(serial) > 2:
                rec = self.serial.get(serial[:-2])
            if rec is not None:
                return [candidate(rec, 1.0, "serial")]
        title = query.get("title", "").strip()
        if not title and query.get("filename"):
            title = namer.parse(query["filename"])["title"]
        key = namer.normalise(title)
        if not key:
            return []

        # A number in front of the title is usually a catalogue number and is
        # dropped, but "007 - GoldenEye" is the game's own, and the catalogue
        # writes it as "GoldenEye 007". So the number is tried at the end too.
        keys = [key]
        number = namer.parse(query.get("filename", ""), strip_extension=True).get("number") \
            if query.get("filename") else ""
        if number and key + number not in keys:
            keys.append(key + number)

        wanted = {r for r in query.get("regions", "").lower().split(",") if r}
        seen = set()
        matches = []
        for one in keys:
            for rec in self.by_key.get(one, []):
                if rec["name"] in seen:
                    continue
                seen.add(rec["name"])
                matches.append(rec)
            if matches:
                break
        matches.sort(key=lambda rec: 0 if wanted & {r.lower() for r in record_regions(rec)} else 1)
        return [candidate(rec, 0.9, "name") for rec in matches]

    def record(self, name: str, query: Dict[str, str]) -> Optional[dict]:
        """The record for a candidate id, preferring one whose hash the query carries."""
        recs = self.by_name.get(name)
        if not recs:
            return None
        for param, field in (("crc32", "crc"), ("md5", "md5"), ("sha1", "sha1")):
            value = query.get(param, "").strip().lower()
            if value:
                for rec in recs:
                    if rdb.hexfield(rec, field) == value:
                        return rec
        return recs[0]

    def details(self, rec: dict) -> Dict[str, Any]:
        name = rec["name"]
        tags = namer.parse(name, strip_extension=False)
        regions = record_regions(rec, tags)
        year = rec.get("releaseyear")
        releasedate = release_date(year, rec.get("releasemonth"), rec.get("releaseday"))
        release = {
            "title": name,
            "regions": regions,
            "languages": tags["languages"],
            "revision": tags["revision"] or "",
            "status": tags["devstatus"] if tags["devstatus"] in STATUS_WORDS else "retail",
            "licence": tags["licence"],
            "serial": rdb.textfield(rec, "serial"),
            "releasedate": releasedate,
            "crc32": rdb.hexfield(rec, "crc") or "",
            "md5": rdb.hexfield(rec, "md5") or "",
            "sha1": rdb.hexfield(rec, "sha1") or "",
            "size": rec.get("size") if isinstance(rec.get("size"), int) else 0,
        }
        out: Dict[str, Any] = {
            "version": 1,
            "title": tags["display"],
            "originaltitle": name,
            "overview": rdb.textfield(rec, "description"),
            "developers": _one(rec, "developer"),
            "publishers": _one(rec, "publisher"),
            "genres": [g for g in GENRE_SPLIT.split(rdb.textfield(rec, "genre")) if g],
            "collections": _one(rec, "franchise"),
            "category": category(name, tags),
            "ageratings": [{"board": board, "value": rdb.textfield(rec, field), "descriptors": ""}
                           for field, board in AGE_BOARDS if rdb.textfield(rec, field)],
            "uniqueids": {"libretro": name},
            "releases": [release],
            "art": art_urls(self.platform_name, name, regions[0] if regions else None,
                            self.held_pictures),
        }
        if isinstance(year, int):
            out["year"] = year
        if releasedate:
            out["releasedate"] = releasedate
        users = rec.get("users")
        if isinstance(users, int) and users > 0:
            out["players"] = {"min": 1, "max": users}
        ratings = {}
        for field, source, maximum in RATINGS:
            value = rec.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                ratings[source] = {"rating": float(value), "max": maximum, "votes": 0}
        if ratings:
            out["ratings"] = ratings
        return out


def release_date(year: Any, month: Any, day: Any) -> str:
    if not isinstance(year, int) or not isinstance(month, int) or not 1 <= month <= 12:
        return ""
    if isinstance(day, int) and 1 <= day <= 31:
        return "{:04d}-{:02d}-{:02d}".format(year, month, day)
    return "{:04d}-{:02d}".format(year, month)


def candidate(rec: dict, score: float, matchedby: str) -> dict:
    tags = namer.parse(rec["name"], strip_extension=False)
    out = {"id": rec["name"], "title": tags["display"], "score": score, "matchedby": matchedby}
    if isinstance(rec.get("releaseyear"), int):
        out["year"] = rec["releaseyear"]
    # Several entries share a title, so send what tells them apart
    if rec["name"] != tags["display"]:
        out["subtitle"] = rec["name"]
    regions = record_regions(rec, tags)
    if regions:
        out["regions"] = regions
    return out


def record_regions(rec: dict, tags: Optional[dict] = None) -> List[str]:
    if tags is None:
        tags = namer.parse(rec["name"], strip_extension=False)
    if tags["regions"]:
        return list(dict.fromkeys(tags["regions"]))
    codes = []
    for part in rdb.textfield(rec, "region").split(","):
        code = namer.REGIONS.get(part.strip().lower())
        if code and code not in codes:
            codes.append(code)
    return codes


def category(name: str, tags: dict) -> str:
    if "[bios]" in name.lower() or tags["devstatus"] == "bios":
        return "bios"
    if tags["licence"] in ("aftermarket", "homebrew"):
        return "homebrew"
    if tags["hack"]:
        return "hack"
    return "retail"


def _one(rec: dict, field: str) -> List[str]:
    value = rdb.textfield(rec, field)
    return [value] if value else []


class Store:
    """Fetches, caches and holds catalogues for the life of the process."""

    def __init__(self, cache_dir: str, download: bool, cache_days: int, log: Log):
        self.cache_dir = cache_dir
        self.download = download
        self.cache_days = cache_days
        self.log = log
        self.catalogues: Dict[str, Optional[Catalogue]] = {}
        self.thumbnail_index: Dict[str, Optional[Dict[str, set]]] = {}
        self.system_icon_index: Optional[Dict[str, set]] = None

    def catalogue(self, platform_name: str) -> Optional[Catalogue]:
        if platform_name not in self.catalogues:
            self.catalogues[platform_name] = self._open(platform_name)
        return self.catalogues[platform_name]

    def _open(self, platform_name: str) -> Optional[Catalogue]:
        path = self._path(platform_name)
        if not self._ensure(platform_name, path):
            return None
        cat = Catalogue(platform_name)
        started = time.time()
        cat.load(path)
        self.log("loaded {} records from {} in {:.2f}s".format(cat.count, path, time.time() - started), False)
        return cat

    def thumbnails(self, platform_name: str) -> Optional[Dict[str, set]]:
        """What the thumbnail repository holds for a platform, folder by folder.

        One request per platform, kept as long as the catalogue is. None means
        the question could not be answered, and every URL is offered as before.
        """
        if platform_name in self.thumbnail_index:
            return self.thumbnail_index[platform_name]

        held = self._read_thumbnails(platform_name)
        self.thumbnail_index[platform_name] = held
        return held

    def _read_thumbnails(self, platform_name: str) -> Optional[Dict[str, set]]:
        path = os.path.join(self.cache_dir, platform_name + ".thumbs.json")
        fresh = os.path.isfile(path) and time.time() - os.path.getmtime(path) < self.cache_days * 86400

        if not fresh and self.download:
            try:
                self._write_thumbnails(platform_name, path)
            except Exception as err:
                self.log("thumbnail list failed for {}: {}".format(platform_name, err), False)

        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as handle:
                held = json.load(handle)
        except Exception:
            return None
        if not isinstance(held, dict) or not held:
            return None
        return {folder: set(names) for folder, names in held.items()}

    def system_icons(self, platform_name: str) -> List[Dict[str, str]]:
        """The machine's own icons, in the order the asset sets are preferred."""
        held = self._system_icon_index()
        if held is None:
            return []
        return [{"url": SYSTEM_ICON_URL.format(folder, urllib.parse.quote(platform_name))}
                for folder in SYSTEM_ICON_FOLDERS if platform_name in held.get(folder, ())]

    def _system_icon_index(self) -> Optional[Dict[str, set]]:
        """What the asset repository holds, so no URL is offered that answers 404."""
        if self.system_icon_index is not None:
            return self.system_icon_index

        path = os.path.join(self.cache_dir, "system-icons.json")
        fresh = os.path.isfile(path) and time.time() - os.path.getmtime(path) < self.cache_days * 86400
        if not fresh and self.download:
            try:
                self._write_system_icons(path)
            except Exception as err:
                self.log("the system icon list failed: {}".format(err), False)

        held: Dict[str, set] = {}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            if isinstance(stored, dict):
                held = {folder: set(names) for folder, names in stored.items()}
        except Exception:
            pass

        self.system_icon_index = held
        return held

    def _write_system_icons(self, path: str) -> None:
        request = urllib.request.Request(SYSTEM_ICON_INDEX_URL,
                                         headers={"User-Agent": USER_AGENT,
                                                  "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            tree = json.loads(response.read().decode("utf-8"))
        if tree.get("truncated"):
            self.log("the system icon list is truncated; not using it", False)
            return

        wanted = set(SYSTEM_ICON_FOLDERS)
        held: Dict[str, List[str]] = {folder: [] for folder in wanted}
        for entry in tree.get("tree", []):
            entry_path = entry.get("path", "")
            if not entry_path.endswith(".png"):
                continue
            folder, _, filename = entry_path.rpartition("/")
            if folder in wanted and filename:
                held[folder].append(filename[:-4])

        if not any(held.values()):
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        partial = path + ".part"
        with open(partial, "w", encoding="utf-8") as out:
            json.dump(held, out)
        os.replace(partial, path)

    def _write_thumbnails(self, platform_name: str, path: str) -> None:
        repo = platform_name.replace(" ", "_")
        url = THUMB_INDEX_URL.format(urllib.parse.quote(repo))
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                       "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            tree = json.loads(response.read().decode("utf-8"))

        # A repository too big to list leaves the question unanswered rather
        # than answering it with half the files
        if tree.get("truncated"):
            self.log("thumbnail list for {} is truncated; not using it".format(platform_name), False)
            return

        wanted = {folder for _, folder in ART_FOLDERS}
        held: Dict[str, List[str]] = {folder: [] for folder in wanted}
        for entry in tree.get("tree", []):
            entry_path = entry.get("path", "")
            if not entry_path.endswith(".png"):
                continue
            folder, _, filename = entry_path.partition("/")
            if folder in wanted and filename:
                held[folder].append(filename[:-4])

        if not any(held.values()):
            return

        os.makedirs(os.path.dirname(path), exist_ok=True)
        partial = path + ".part"
        with open(partial, "w", encoding="utf-8") as out:
            json.dump(held, out)
        os.replace(partial, path)
        self.log("listed {} pictures for {}".format(sum(len(v) for v in held.values()),
                                                    platform_name), False)

    def _path(self, platform_name: str) -> str:
        return os.path.join(self.cache_dir, platform_name + ".rdb")

    def _ensure(self, platform_name: str, path: str) -> bool:
        cached = os.path.isfile(path)
        if not self.download:
            return cached
        if cached and time.time() - os.path.getmtime(path) < self.cache_days * 86400:
            return True
        url = RDB_URL.format(urllib.parse.quote(platform_name))
        try:
            self._fetch(url, path)
            return True
        except Exception as err:
            self.log("download failed for {}: {}".format(url, err), True)
            return cached

    def _fetch(self, url: str, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        partial = path + ".part"
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response, open(partial, "wb") as out:
            while True:
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
        os.replace(partial, path)
        self.log("downloaded {} to {}".format(url, path), False)


def platform_info(platform_name: str) -> Dict[str, Any]:
    """Manufacturer and display name from an RDB file name such as "Sega - Mega Drive - Genesis"."""
    parts = [p.strip() for p in platform_name.split(" - ") if p.strip()]
    info: Dict[str, Any] = {"version": 1, "name": platform_name}
    if len(parts) >= 2:
        info["manufacturer"] = parts[0]
        info["name"] = parts[1] if parts[1].startswith(parts[0]) else "{} {}".format(parts[0], parts[1])
    return info


class LibretroProvider(Provider):
    """Always available: works from cached RDB files, downloading them only when allowed."""

    name = "libretro"
    details_are_free = True

    def __init__(self, cache_dir: str, log: Log):
        super().__init__(log)
        self.store = Store(cache_dir, True, 30, log)

    @property
    def cache_dir(self) -> str:
        return self.store.cache_dir

    def available(self, settings: Dict[str, Any]) -> bool:
        return True

    def catalogue(self, request: Request) -> Optional[Catalogue]:
        self.store.download = bool(request.settings.get("download", True))
        self.store.cache_days = int(request.settings.get("cache_days", 30))
        name = request.platform_id(self.name)
        if not name:
            self.log("platform {!r} has no libretro id".format(request.get("platform")), False)
            return None
        return self.store.catalogue(name)

    def find(self, request: Request) -> List[dict]:
        cat = self.catalogue(request)
        return cat.find(request.query) if cat else []

    def details(self, candidate_id: str, request: Request) -> Optional[Dict[str, Any]]:
        cat = self.catalogue(request)
        rec = cat.record(candidate_id, request.query) if cat else None
        if rec is None or cat is None:
            return None
        if cat.held_pictures is None:
            cat.held_pictures = self.store.thumbnails(cat.platform_name)
        return cat.details(rec)

    def platform(self, request: Request) -> Optional[Dict[str, Any]]:
        name = request.platform_id(self.name)
        if not name:
            return None
        info = platform_info(name)
        icons = self.store.system_icons(name)
        if icons:
            info["art"] = {"icon": icons}
        return info
