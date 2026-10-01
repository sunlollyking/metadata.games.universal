"""Arcade romsets, identified by what is inside the zip rather than by its name.

An arcade game is a set of chip dumps, and each emulator expects the set the
way its own romset list describes it, under the set's short name. A zip can be
renamed and still be the same set, and two zips can share a name and hold
different versions of it. So the files inside are what identify it: Kodi sends
the name, size and CRC of every member, read from the zip's directory, and
they are matched against the romset list of each arcade emulator.

The answer names the set, the game it is a clone of, and which installed
emulators hold exactly that set. The candidate id is the parent set, so the
regional and revision clones of one game become releases of it.

Names and flags that the romset lists do not carry -- whether a set is a
bootleg, a fruit machine or a mahjong game -- come from LaunchBox's MAME list,
which the LaunchBox provider indexes along with its main catalogue.
"""
import json
import os
import re
import sqlite3
import time
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from . import Provider, Request

Log = Callable[[str, bool], None]
USER_AGENT = "Kodi metadata.games.universal"
DOWNLOAD_TIMEOUT = 600
INDEX_NAME = "arcade.sqlite"
INDEX_DAYS = 30.0

#: Each emulator's romset list, in the order an emulator is preferred when
#: several hold a set exactly
SOURCES: Tuple[Tuple[str, str, str], ...] = (
    ("fbneo", "game.libretro.fbneo",
     "https://raw.githubusercontent.com/libretro/FBNeo/master/dats/"
     "FinalBurn%20Neo%20(ClrMame%20Pro%20XML%2C%20Arcade%20only).dat"),
    ("mame2003plus", "game.libretro.mame2003_plus",
     "https://raw.githubusercontent.com/libretro/mame2003-plus-libretro/master/metadata/"
     "mame2003-plus.xml"),
    ("mame2010", "game.libretro.mame2010",
     "https://raw.githubusercontent.com/libretro/mame2010-libretro/master/metadata/mame2010.xml"),
    ("mame2000", "game.libretro.mame2000",
     "https://raw.githubusercontent.com/libretro/mame2000-libretro/master/metadata/"
     "MAME%200.37b5%20XML.dat"),
)
SOURCE_RANK = {name: rank for rank, (name, _, _) in enumerate(SOURCES)}
ADDON_OF = {name: addon for name, addon, _ in SOURCES}

#: Below this share of a set's own chips, a zip is not called that set
MIN_COVERAGE = 0.5

#: The board a set runs on, from the driver it is filed under
BOARDS = (
    ("neogeo", "Neo Geo MVS"),
    ("cps1", "Capcom CPS-1"),
    ("cps2", "Capcom CPS-2"),
    ("cps3", "Capcom CPS-3"),
    ("naomi", "Sega Naomi"),
    ("stv", "Sega ST-V"),
    ("model2", "Sega Model 2"),
    ("model3", "Sega Model 3"),
    ("system16", "Sega System 16"),
    ("system18", "Sega System 18"),
    ("segas32", "Sega System 32"),
    ("pgm", "IGS PGM"),
    ("taito_f3", "Taito F3"),
    ("toaplan2", "Toaplan"),
    ("konamigx", "Konami GX"),
)

REGIONS = {
    "world": "World", "usa": "USA", "us": "USA", "japan": "Japan", "europe": "Europe",
    "euro": "Europe", "asia": "Asia", "korea": "Korea", "taiwan": "Taiwan",
    "hong kong": "Hong Kong", "china": "China", "brazil": "Brazil", "spain": "Spain",
    "germany": "Germany", "france": "France", "italy": "Italy", "uk": "United Kingdom",
    "australia": "Australia", "canada": "Canada",
}
PARENS = re.compile(r"\s*\(([^()]*)\)\s*$")

SCHEMA = """
CREATE TABLE romset (source TEXT, name TEXT, description TEXT, year TEXT,
                     manufacturer TEXT, cloneof TEXT, romof TEXT, isbios INTEGER,
                     isdevice INTEGER, sourcefile TEXT, players INTEGER,
                     PRIMARY KEY (source, name));
CREATE TABLE rom (source TEXT, name TEXT, crc TEXT, merged INTEGER);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""
INDEXES = """
CREATE INDEX IF NOT EXISTS ix_rom_crc ON rom (crc);
CREATE INDEX IF NOT EXISTS ix_rom_set ON rom (source, name);
"""


def clean_title(description: str) -> Tuple[str, str]:
    """The game's name and its other name, from a romset description.

    "Aggressors of Dark Kombat / Tsuukai GANGAN Koushinkyoku (ADM-008 ~ ADH-008)"
    names one game twice and adds a cartridge code; the library wants the
    first name, and keeps the second as the original title.
    """
    text = description.strip()
    while True:
        m = PARENS.search(text)
        if not m or m.start() == 0:
            break
        text = text[:m.start()].rstrip()
    names = [part.strip() for part in text.split(" / ") if part.strip()]
    if not names:
        return description.strip(), ""
    return names[0], (names[1] if len(names) > 1 else "")


def regions_of(description: str) -> List[str]:
    """The regions a description's brackets name, written in full."""
    found: List[str] = []
    for group in re.findall(r"\(([^()]*)\)", description):
        for word in re.split(r"[,/]", group):
            word = re.sub(r"\s*\d.*$", "", word.strip().lower())
            region = REGIONS.get(word)
            if region and region not in found:
                found.append(region)
    return found


def board_of(sourcefile: str) -> str:
    stem = os.path.splitext(os.path.basename(sourcefile or ""))[0].lower()
    for key, board in BOARDS:
        if stem == key or stem.startswith(key):
            return board
    return ""


def members_of(request: Request) -> List[Tuple[str, int, str]]:
    """The zip's members as Kodi sent them: name, size and CRC."""
    raw = request.query.get("members")
    # Kodi lists a zip of one file as the file itself. On an arcade platform
    # that is still a set, of one chip
    if not raw and request.platform_id("launchbox").lower() == "arcade" and request.get("crc32"):
        try:
            size = int(request.get("size") or 0)
        except ValueError:
            size = 0
        raw = [[request.get("filename"), size, request.get("crc32")]]
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    out = []
    for item in raw or []:
        if isinstance(item, (list, tuple)) and len(item) >= 3:
            crc = str(item[2]).lower().zfill(8)
            try:
                out.append((str(item[0]), int(item[1]), crc))
            except (TypeError, ValueError):
                continue
    return out


class Index:
    """Every emulator's romset list as one SQLite file, rebuilt when it is stale."""

    def __init__(self, path: str, log: Log):
        self.path = path
        self.log = log
        self._db: Optional[sqlite3.Connection] = None

    def age_days(self) -> float:
        try:
            return (time.time() - os.path.getmtime(self.path)) / 86400.0
        except OSError:
            return float("inf")

    def sources(self) -> List[str]:
        db = self.connect()
        if db is None:
            return []
        row = db.execute("SELECT value FROM meta WHERE key = 'sources'").fetchone()
        return json.loads(row[0]) if row else []

    def connect(self) -> Optional[sqlite3.Connection]:
        if self._db is None and os.path.exists(self.path):
            self._db = sqlite3.connect(self.path)
            self._db.row_factory = sqlite3.Row
            self._db.executescript(INDEXES)
        return self._db

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None

    def build(self, sources: Sequence[Tuple[str, str]], fetch: Callable[[str, str], None]) -> bool:
        """Write a fresh index from the given lists, keeping the old one if that fails."""
        self.close()
        folder = os.path.dirname(self.path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        working = self.path + ".part"
        _remove(working)
        built: List[str] = []
        try:
            db = sqlite3.connect(working)
            db.executescript(SCHEMA)
            for name, url in sources:
                dat = os.path.join(folder, name + ".dat.part")
                try:
                    fetch(url, dat)
                    sets = self._load(db, name, dat)
                except Exception as err:  # noqa: BLE001 - one list failing leaves the others
                    self.log("arcade: the {} romset list could not be read: {}".format(name, err),
                             True)
                    continue
                finally:
                    _remove(dat)
                built.append(name)
                self.log("arcade: indexed {} {} sets".format(sets, name), False)
            db.execute("INSERT INTO meta VALUES ('sources', ?)", (json.dumps(built),))
            db.executescript(INDEXES)
            db.commit()
            db.close()
        except Exception as err:  # noqa: BLE001
            self.log("arcade: building the index failed: {}".format(err), True)
            _remove(working)
            return False
        if not built:
            _remove(working)
            return False
        os.replace(working, self.path)
        return True

    @staticmethod
    def _load(db: sqlite3.Connection, source: str, path: str) -> int:
        sets: List[tuple] = []
        roms: List[tuple] = []
        count = 0
        for _, el in ET.iterparse(path, events=("end",)):
            if el.tag not in ("game", "machine"):
                continue
            name = el.get("name") or ""
            players = 0
            inputs = el.find("input")
            if inputs is not None:
                try:
                    players = int(inputs.get("players") or 0)
                except ValueError:
                    players = 0
            sets.append((source, name, (el.findtext("description") or "").strip(),
                         (el.findtext("year") or "").strip(),
                         (el.findtext("manufacturer") or "").strip(),
                         el.get("cloneof") or "", el.get("romof") or "",
                         1 if el.get("isbios") == "yes" else 0,
                         1 if el.get("isdevice") == "yes" else 0,
                         el.get("sourcefile") or "", players))
            for rom in el.findall("rom"):
                crc = (rom.get("crc") or "").lower()
                if crc and rom.get("status") != "nodump":
                    roms.append((source, name, crc, 1 if rom.get("merge") else 0))
            el.clear()
            count += 1
            if len(roms) >= 20000:
                db.executemany("INSERT INTO rom VALUES (?,?,?,?)", roms)
                roms = []
            if len(sets) >= 2000:
                db.executemany("INSERT OR REPLACE INTO romset VALUES (?,?,?,?,?,?,?,?,?,?,?)", sets)
                sets = []
        db.executemany("INSERT INTO rom VALUES (?,?,?,?)", roms)
        db.executemany("INSERT OR REPLACE INTO romset VALUES (?,?,?,?,?,?,?,?,?,?,?)", sets)
        return count


def _genres(flags: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
    """A MAME genre is a category and a subcategory, "Fighter / Versus"; only
    the category is a genre."""
    if flags and flags.get("genre"):
        return {"genres": [flags["genre"].split("/")[0].strip()]}
    return {}


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _download(url: str, target: str) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as answer:
        with open(target, "wb") as out:
            while True:
                chunk = answer.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)


class Match:
    """What one zip turned out to be."""

    def __init__(self, source: str, row: sqlite3.Row, coverage: float, exact: bool,
                 exact_sets: List[Tuple[str, str]]):
        self.source = source
        self.row = row
        self.coverage = coverage
        self.exact = exact
        #: Every list, best first, that holds exactly this zip, with the name
        #: that list gives the set: the lists do not always agree on it
        self.exact_sets = exact_sets

    @property
    def romset(self) -> str:
        return self.row["name"]

    #: Set when the clone is really another game, which MAME's older lists
    #: file as a clone of the one it followed
    own_game = False

    @property
    def parent(self) -> str:
        if self.own_game:
            return self.row["name"]
        return self.row["cloneof"] or self.row["name"]


class ArcadeProvider(Provider):
    name = "arcade"
    details_are_free = True

    def __init__(self, log: Log, cache_dir: str = "",
                 installed: Optional[Callable[[str], bool]] = None,
                 launchbox_index: Optional[str] = None,
                 fetch: Callable[[str, str], None] = _download):
        super().__init__(log)
        self.index = Index(os.path.join(cache_dir or "", "arcade", INDEX_NAME), log)
        #: Whether an emulator is installed. Only installed emulators' lists
        #: are fetched; with none installed, FBNeo's still names the games.
        self.installed = installed or (lambda addon: True)
        self.launchbox_index = launchbox_index or os.path.join(
            cache_dir or "", "launchbox", "launchbox.sqlite")
        self.fetch = fetch
        self._tried_to_build = False
        self._launchbox: Optional[sqlite3.Connection] = None

    def close(self) -> None:
        self.index.close()
        if self._launchbox is not None:
            self._launchbox.close()
            self._launchbox = None

    def wanted_sources(self) -> List[Tuple[str, str]]:
        wanted = [(name, url) for name, addon, url in SOURCES if self.installed(addon)]
        return wanted or [(SOURCES[0][0], SOURCES[0][2])]

    def _ensure(self) -> Optional[sqlite3.Connection]:
        wanted = [name for name, _ in self.wanted_sources()]
        stale = self.index.age_days() > INDEX_DAYS or not set(wanted) <= set(self.index.sources())
        if stale and not self._tried_to_build:
            self._tried_to_build = True
            self.index.build(self.wanted_sources(), self.fetch)
        return self.index.connect()

    def prefetch(self, requests: Any) -> None:
        if any(members_of(r) for r in requests or []):
            self._ensure()

    def identify(self, request: Request) -> Optional[Match]:
        members = members_of(request)
        if not members:
            return None
        db = self._ensure()
        if db is None:
            return None
        crcs = {crc for _, _, crc in members}
        marks = ",".join("?" * len(crcs))
        hits: Dict[Tuple[str, str], int] = defaultdict(int)
        for row in db.execute("SELECT DISTINCT source, name, crc FROM rom WHERE crc IN ({})".format(marks),
                              tuple(crcs)):
            hits[(row["source"], row["name"])] += 1
        scored: List[Tuple[tuple, str, str, float, bool]] = []
        for (source, name), count in hits.items():
            own, full = set(), set()
            for row in db.execute("SELECT crc, merged FROM rom WHERE source = ? AND name = ?",
                                  (source, name)):
                full.add(row["crc"])
                if not row["merged"]:
                    own.add(row["crc"])
            if not own:
                continue
            coverage = len(own & crcs) / len(own)
            unknown = len(crcs - full)
            exact = coverage == 1.0 and unknown == 0
            score = (coverage, -unknown, count, -SOURCE_RANK.get(source, 99))
            scored.append((score, source, name, coverage, exact))
        if not scored:
            return None
        scored.sort(reverse=True)
        # A merged set is a parent's zip that also carries its clones' chips.
        # Emulators load it by the parent's name and pass over the rest, so a
        # zip named for a parent it holds entirely is that parent
        stem = os.path.splitext(os.path.basename(request.get("filename")))[0].lower()
        named: Dict[str, str] = {}
        for _, s, n, c, _ in scored:
            if n == stem and c == 1.0 and s not in named and not db.execute(
                    "SELECT cloneof FROM romset WHERE source = ? AND name = ?", (s, n)).fetchone()[0]:
                named[s] = n
        exact_sets = dict(named)
        for _, s, n, _, e in scored:
            if e and s not in exact_sets:
                exact_sets[s] = n
        ordered = sorted(exact_sets.items(), key=lambda item: SOURCE_RANK.get(item[0], 99))
        _, source, name, coverage, exact = scored[0]
        if named:
            source, name = min(named.items(), key=lambda item: SOURCE_RANK.get(item[0], 99))
            coverage, exact = 1.0, True
        elif coverage < MIN_COVERAGE:
            return None
        # Described from the list the preferred emulator uses when one holds
        # the set exactly, so the name given is the one that emulator loads
        elif ordered and not exact:
            source, name = ordered[0]
            coverage, exact = 1.0, True
        row = db.execute("SELECT * FROM romset WHERE source = ? AND name = ?", (source, name)).fetchone()
        match = Match(source, row, coverage, exact, ordered)
        # A regional or revised set keeps the game's name; one named otherwise
        # is a game of its own ("Breakers Revenge" is not a release of "Breakers").
        # A bootleg or a hack is a version of the game it was made from,
        # whatever it calls itself.
        if row["cloneof"] and not self._derived(row):
            parent = db.execute("SELECT description FROM romset WHERE source = ? AND name = ?",
                                (source, row["cloneof"])).fetchone()
            if parent is not None and clean_title(parent["description"])[0].lower() != \
                    clean_title(row["description"])[0].lower():
                match.own_game = True
        return match

    def find(self, request: Request) -> List[dict]:
        match = self.identify(request)
        if match is None:
            known = self._known_by_name(request)
            if known is None:
                return []
            return [{"id": known["filename"], "title": known["name"], "score": 0.5,
                     "matchedby": "filename"}]
        title, _ = clean_title(self._parent_description(match))
        return [{"id": match.parent, "title": title, "score": round(match.coverage, 3),
                 "matchedby": "hash", "subtitle": match.row["description"],
                 "regions": regions_of(match.row["description"])}]

    def details(self, candidate_id: str, request: Request) -> Optional[Dict[str, Any]]:
        match = self.identify(request)
        if match is None:
            known = self._known_by_name(request)
            if known is None or known["filename"] != candidate_id:
                return None
            return self._details_by_name(known)
        if match.parent != candidate_id:
            return None
        row = match.row
        title, other = clean_title(self._parent_description(match))
        out: Dict[str, Any] = {"version": 1, "title": title,
                               "uniqueids": {self.name: match.parent},
                               "romset": match.romset}
        if other:
            out["originaltitle"] = other
        year = row["year"][:4]
        if year.isdigit():
            out["year"] = int(year)
        if row["manufacturer"]:
            out["publishers"] = [row["manufacturer"]]
        if row["players"]:
            out["players"] = {"max": int(row["players"])}
        flags = self._launchbox_flags(match.romset) or self._launchbox_flags(match.parent)
        derived = self._derived(row) if row["cloneof"] and not match.own_game else ""
        game = self._parent_row(match) if derived else row
        game_flags = self._launchbox_flags(game["name"]) if derived else flags
        out["category"] = self._category(game["description"],
                                         bool(game["isbios"] or game["isdevice"]), game_flags)
        tags = []
        board = board_of(row["sourcefile"] or (flags or {}).get("source", ""))
        if board:
            tags.append(board)
        for flag, tag in (("mahjong", "Mahjong"), ("quiz", "Quiz"), ("mature", "Mature")):
            if (flags or {}).get(flag):
                tags.append(tag)
        if tags:
            out["tags"] = tags
        out.update(_genres(flags))
        out["emulators"] = [{"addon": ADDON_OF[s], "romset": n, "requires": self._requires(s, n)}
                            for s, n in match.exact_sets if s in ADDON_OF]
        release = {
            "title": row["description"],
            "regions": regions_of(row["description"]),
            "romset": match.romset,
            "status": "proto" if "prototype" in row["description"].lower() else "retail",
        }
        if derived == "hack":
            release["edition"] = "Mod"
        elif derived == "bootleg":
            release["licence"] = "pirate"
        out["releases"] = [release]
        return out

    def _derived(self, row: sqlite3.Row) -> str:
        """"hack" or "bootleg" where a set was made from another game, or ""."""
        flags = self._launchbox_flags(row["name"]) or {}
        description = (row["description"] or "").lower()
        if flags.get("hack") or "hack" in description:
            return "hack"
        if flags.get("bootleg") or "bootleg" in description:
            return "bootleg"
        return ""

    def _parent_row(self, match: Match) -> sqlite3.Row:
        db = self.index.connect()
        parent = db.execute("SELECT * FROM romset WHERE source = ? AND name = ?",
                            (match.source, match.row["cloneof"])).fetchone() if db else None
        return parent if parent is not None else match.row

    def _requires(self, source: str, name: str) -> List[str]:
        """The sets an emulator needs beside this one: its parent, then the BIOS.

        MAME looks for them in the same folder as the game.
        """
        db = self.index.connect()
        out: List[str] = []
        current = name
        while db is not None and len(out) < 4:
            row = db.execute("SELECT romof FROM romset WHERE source = ? AND name = ?",
                             (source, current)).fetchone()
            if row is None or not row["romof"] or row["romof"] in out:
                break
            current = row["romof"]
            out.append(current)
        return out

    def _parent_description(self, match: Match) -> str:
        if not match.row["cloneof"] or match.own_game:
            return match.row["description"]
        db = self.index.connect()
        parent = db.execute("SELECT description FROM romset WHERE source = ? AND name = ?",
                            (match.source, match.row["cloneof"])).fetchone() if db else None
        return parent["description"] if parent else match.row["description"]

    def _known_by_name(self, request: Request) -> Optional[Dict[str, Any]]:
        """LaunchBox's MAME entry for a zip no emulator's list holds, found by its name.

        MAME knows far more than the emulators installed here: fruit machines,
        consoles, and games newer than every list. Named, they can at least be
        filed where they belong.
        """
        if not members_of(request):
            return None
        stem = os.path.splitext(os.path.basename(request.get("filename")))[0].lower()
        return self._launchbox_flags(stem) if stem else None

    def _details_by_name(self, known: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {"version": 1, "title": known["name"],
                               "uniqueids": {self.name: known["filename"]},
                               "romset": known["filename"], "emulators": [],
                               "category": self._category(known["name"], False, known)}
        year = (known.get("year") or "")[:4]
        if year.isdigit():
            out["year"] = int(year)
        if known.get("publisher"):
            out["publishers"] = [known["publisher"]]
        board = board_of(known.get("source") or "")
        if board:
            out["tags"] = [board]
        out.update(_genres(known))
        out["releases"] = [{"title": known["name"], "romset": known["filename"],
                            "status": "proto" if known.get("prototype") else "retail"}]
        return out

    @staticmethod
    def _category(description: str, bios: bool, flags: Optional[Dict[str, Any]]) -> str:
        flags = flags or {}
        if bios or (flags.get("genre") or "").startswith("System"):
            return "bios"
        if flags.get("mechanical") or flags.get("casino") or flags.get("fruit") or flags.get("nonarcade") \
                or (flags.get("genre") or "").startswith("Gambling"):
            return "nongame"
        description = description.lower()
        if flags.get("bootleg") or flags.get("hack") or "bootleg" in description or "hack" in description:
            return "hack"
        return "retail"

    def _launchbox_flags(self, romset: str) -> Optional[Dict[str, Any]]:
        """LaunchBox's MAME entry for a set, when its index is there."""
        if self._launchbox is None:
            if not os.path.exists(self.launchbox_index):
                return None
            self._launchbox = sqlite3.connect(self.launchbox_index)
            self._launchbox.row_factory = sqlite3.Row
        try:
            row = self._launchbox.execute("SELECT * FROM mame WHERE filename = ?", (romset,)).fetchone()
        except sqlite3.Error:
            return None
        return dict(row) if row else None
