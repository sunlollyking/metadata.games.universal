"""LaunchBox Games Database provider: one bulk file, then everything is answered locally.

The service publishes its whole catalogue as a zip, regenerated daily, at
https://gamesdb.launchbox-app.com/Metadata.zip. There is no per-game API and
no key, so the whole source is one download: about a hundred megabytes for
some 188,000 games and 1.3 million pictures.

The XML inside is far too large to re-read per game, so it is parsed once,
straight out of the zip, into an SQLite index in the provider's cache folder.
After that a game costs two indexed lookups and nothing on the network, which
is what makes this the cheapest source in the set to run over a whole library.

The platform is the ``launchbox`` entry of platformids, which is the name the
service files a platform under, e.g. "Sega Genesis". Candidate ids are its
game ids. Picture URLs are the file name under
https://images.launchbox-app.com/.

The catalogue is written by its users, so a picture's provenance matters: a
scan, a reconstruction and a piece of fan art are all offered for the same
game and are told apart only by the type they are filed under. ART lists the
real scan before the reconstruction before the fan art, and the first URL of a
type is the one a view shows.
"""
import os
import re
import sqlite3
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from .. import namer
from . import Provider, Request

METADATA_URL = "https://gamesdb.launchbox-app.com/Metadata.zip"
IMAGE_URL = "https://images.launchbox-app.com/{}"
USER_AGENT = "Kodi metadata.games.universal"
ARCHIVE_MEMBER = "Metadata.xml"
INDEX_NAME = "launchbox.sqlite"
DOWNLOAD_TIMEOUT = 600
#: How long an index is used before the catalogue is fetched again
INDEX_DAYS = 30.0
#: What the service calls a picture, and what the library calls it. A type may
#: appear more than once: the earlier entry is the better provenance and is
#: offered first.
ART = (
    ("Box - Front", "boxfront"),
    ("Box - Front - Reconstructed", "boxfront"),
    ("Fanart - Box - Front", "boxfront"),
    ("Clear Logo", "clearlogo"),
    ("Screenshot - Game Title", "titlescreen"),
    ("Screenshot - Gameplay", "screenshot"),
    ("Fanart - Background", "fanart"),
    ("Box - Back", "boxback"),
    ("Box - Back - Reconstructed", "boxback"),
    ("Box - 3D", "box3d"),
    ("Box - Spine", "boxspine"),
    ("Cart - Front", "cartridge"),
    ("Fanart - Cart - Front", "cartridge"),
    ("Disc", "disc"),
    ("Fanart - Disc", "disc"),
    ("Banner", "banner"),
    ("Advertisement Flyer - Front", "flyer"),
    ("Arcade - Marquee", "marquee"),
    ("Arcade - Cabinet", "cabinet"),
)
ART_RANK = {name: rank for rank, (name, _) in enumerate(ART)}
ART_TYPE = dict(ART)
GENRE_SPLIT = re.compile(r"\s*;\s*|\s*,\s*")
YEAR = re.compile(r"^(\d{4})")
Log = Callable[[str, bool], None]

SCHEMA = """
CREATE TABLE game (id INTEGER PRIMARY KEY, name TEXT, platform TEXT, overview TEXT,
                   released TEXT, developer TEXT, publisher TEXT, genres TEXT,
                   players INTEGER, cooperative INTEGER, esrb TEXT, rating REAL,
                   votes INTEGER, wikipedia TEXT, kind TEXT);
CREATE TABLE name_key (platform TEXT, key TEXT, id INTEGER);
CREATE TABLE image (id INTEGER, rank INTEGER, kind TEXT, region TEXT, filename TEXT);
"""
INDEXES = """
CREATE INDEX ix_name_key ON name_key (platform, key);
CREATE INDEX ix_image ON image (id, rank);
"""


def platform_key(name: Any) -> str:
    return str(name or "").strip().lower()


def year_of(released: Any) -> int:
    m = YEAR.match(str(released or ""))
    return int(m.group(1)) if m else 0


def int_or(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def float_or(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Index:
    """The catalogue as an SQLite file, built once from the published zip."""

    def __init__(self, path: str, log: Log):
        self.path = path
        self.log = log
        self._db: Optional[sqlite3.Connection] = None

    def age_days(self) -> float:
        try:
            return (time.time() - os.path.getmtime(self.path)) / 86400.0
        except OSError:
            return float("inf")

    def ready(self, max_age_days: float) -> bool:
        return self.age_days() <= max_age_days

    def connect(self) -> Optional[sqlite3.Connection]:
        if self._db is None:
            if not os.path.exists(self.path):
                return None
            self._db = sqlite3.connect(self.path)
            self._db.row_factory = sqlite3.Row
        return self._db

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None

    def build(self) -> bool:
        """Fetch the catalogue and write a fresh index beside it.

        Written to a temporary name and moved into place, so a download that
        fails partway leaves the index that is already there working.
        """
        self.close()
        folder = os.path.dirname(self.path)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        archive = self.path + ".zip.part"
        working = self.path + ".part"
        try:
            self._download(archive)
            self._write(archive, working)
        except Exception as err:  # noqa: BLE001 - one bad build must not stop a scan
            self.log("launchbox: building the index failed: {}".format(err), True)
            _remove(working)
            _remove(archive)
            return False
        _remove(archive)
        os.replace(working, self.path)
        return True

    def _download(self, target: str) -> None:
        self.log("launchbox: fetching the catalogue, this happens once a month", False)
        request = urllib.request.Request(METADATA_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as answer:
            with open(target, "wb") as out:
                while True:
                    chunk = answer.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)

    def _write(self, archive: str, target: str) -> None:
        _remove(target)
        db = sqlite3.connect(target)
        db.executescript(SCHEMA)
        games = 0
        with zipfile.ZipFile(archive) as z:
            with z.open(ARCHIVE_MEMBER) as xml:
                for kind, rows in _read(xml):
                    if kind == "game":
                        games += len(rows)
                        db.executemany(
                            "INSERT OR REPLACE INTO game VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
                    elif kind == "name":
                        db.executemany("INSERT INTO name_key VALUES (?,?,?)", rows)
                    else:
                        db.executemany("INSERT INTO image VALUES (?,?,?,?,?)", rows)
        db.executescript(INDEXES)
        db.commit()
        db.close()
        self.log("launchbox: indexed {} games".format(games), False)


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _read(stream: Any) -> Iterable[Tuple[str, List[tuple]]]:
    """Walk the catalogue once, handing back rows in batches of each kind.

    Every element is cleared as it is left, so the whole file never has to be
    held at once.
    """
    games: List[tuple] = []
    names: List[tuple] = []
    images: List[tuple] = []
    platform_of: Dict[str, str] = {}
    for _, el in ET.iterparse(stream, events=("end",)):
        if el.tag == "Game":
            game_id = int_or(el.findtext("DatabaseID"), -1)
            name = (el.findtext("Name") or "").strip()
            platform = platform_key(el.findtext("Platform"))
            if game_id >= 0 and name and platform:
                platform_of[str(game_id)] = platform
                games.append((
                    game_id, name, platform, (el.findtext("Overview") or "").strip(),
                    (el.findtext("ReleaseDate") or el.findtext("ReleaseYear") or "").strip(),
                    (el.findtext("Developer") or "").strip(),
                    (el.findtext("Publisher") or "").strip(),
                    (el.findtext("Genres") or "").strip(),
                    int_or(el.findtext("MaxPlayers")),
                    1 if (el.findtext("Cooperative") or "").lower() == "true" else 0,
                    (el.findtext("ESRB") or "").strip(),
                    float_or(el.findtext("CommunityRating")),
                    int_or(el.findtext("CommunityRatingCount")),
                    (el.findtext("WikipediaURL") or "").strip(),
                    (el.findtext("ReleaseType") or "").strip(),
                ))
                key = namer.normalise(name)
                if key:
                    names.append((platform, key, game_id))
        elif el.tag == "GameAlternateName":
            game_id = el.findtext("DatabaseID")
            key = namer.normalise(el.findtext("AlternateName") or "")
            platform = platform_of.get(str(game_id or ""))
            if key and platform:
                names.append((platform, key, int_or(game_id, -1)))
        elif el.tag == "GameImage":
            kind = (el.findtext("Type") or "").strip()
            filename = (el.findtext("FileName") or "").strip()
            if filename and kind in ART_RANK:
                images.append((int_or(el.findtext("DatabaseID"), -1), ART_RANK[kind], kind,
                               (el.findtext("Region") or "").strip(), filename))
        else:
            continue
        el.clear()
        if len(games) >= 2000:
            yield "game", games
            games = []
        if len(names) >= 5000:
            yield "name", names
            names = []
        if len(images) >= 5000:
            yield "image", images
            images = []
    yield "game", games
    yield "name", names
    yield "image", images


class LaunchBoxProvider(Provider):
    name = "launchbox"
    #: The index is local, so describing a game costs nothing beyond finding it
    details_are_free = True

    def __init__(self, log: Log, cache_dir: str = ""):
        super().__init__(log)
        self.index = Index(os.path.join(cache_dir or "", "launchbox", INDEX_NAME), log)
        self._tried_to_build = False

    def available(self, settings: Dict[str, Any]) -> bool:
        return str(settings.get("launchbox_bulk", "true")).lower() not in ("false", "0")

    def prefetch(self, requests: Any) -> None:
        """Make sure the index is there before a batch starts asking."""
        self._ensure()

    def find(self, request: Request) -> List[dict]:
        db = self._ensure()
        if db is None:
            return []
        platform = platform_key(request.platform_id(self.name))
        key = namer.normalise(request.title())
        if not platform or not key:
            return []
        rows = db.execute(
            "SELECT g.id, g.name FROM name_key n JOIN game g ON g.id = n.id "
            "WHERE n.platform = ? AND n.key = ?", (platform, key)).fetchall()
        seen = set()
        out = []
        for row in rows:
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            out.append({"id": str(row["id"]), "title": row["name"], "score": 0.9,
                        "matchedby": "name"})
        return out

    def details(self, candidate_id: str, request: Request) -> Optional[Dict[str, Any]]:
        db = self._ensure()
        if db is None:
            return None
        row = db.execute("SELECT * FROM game WHERE id = ?", (int_or(candidate_id, -1),)).fetchone()
        if row is None:
            return None
        out: Dict[str, Any] = {
            "version": 1,
            "title": row["name"],
            "uniqueids": {self.name: str(row["id"])},
            "art": self._art(db, row["id"]),
        }
        if row["overview"]:
            out["overview"] = row["overview"]
        if row["developer"]:
            out["developers"] = [row["developer"]]
        if row["publisher"]:
            out["publishers"] = [row["publisher"]]
        genres = [g for g in GENRE_SPLIT.split(row["genres"] or "") if g]
        if genres:
            out["genres"] = genres
        year = year_of(row["released"])
        if year:
            out["year"] = year
            out["releasedate"] = str(row["released"])[:10]
        if row["players"]:
            out["players"] = {"max": row["players"], "coop": bool(row["cooperative"])}
        if row["esrb"]:
            out["ageratings"] = [{"board": "ESRB", "rating": row["esrb"]}]
        if row["rating"] is not None and row["votes"]:
            out["ratings"] = [{"name": self.name, "value": row["rating"], "max": 5,
                               "votes": row["votes"]}]
        return out

    def _art(self, db: sqlite3.Connection, game_id: int) -> Dict[str, List[dict]]:
        art: Dict[str, List[dict]] = {}
        for row in db.execute(
                "SELECT kind, region, filename FROM image WHERE id = ? ORDER BY rank, rowid",
                (game_id,)):
            our = ART_TYPE.get(row["kind"])
            if not our:
                continue
            picture = {"url": IMAGE_URL.format(row["filename"])}
            if row["region"]:
                picture["region"] = row["region"]
            art.setdefault(our, []).append(picture)
        return art

    def _ensure(self) -> Optional[sqlite3.Connection]:
        """The index, built or refreshed if it is missing or stale.

        A failed build is not retried within the same run: the catalogue is one
        large download and a scan must not stall on it once per game.
        """
        if not self.index.ready(INDEX_DAYS) and not self._tried_to_build:
            self._tried_to_build = True
            self.index.build()
        return self.index.connect()
