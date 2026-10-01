"""Provider interface shared by every catalogue the universal scraper can ask.

A Provider answers the three scraper questions for one catalogue. Candidate ids
it returns are local to the provider; the orchestrator prefixes them with the
provider name. Request bundles what one scraper call knows: the query Kodi
sent, the resolved add-on settings and the parsed platform ids. Online
providers keep what they download in a Cache folder of their own, refreshed
by age.
"""
import json
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import namer

Log = Callable[[str, bool], None]
_UNSET = object()
HASH_PARAMS = ("crc32", "md5", "sha1")

#: A picture of the medium is a disc for these dumps and a cartridge, tape or
#: card for everything else. The file says it: a platform is no guide, since
#: the PC Engine, the Mega Drive and the Neo Geo all sold both.
DISC_EXTENSIONS = frozenset((
    "cue", "chd", "iso", "cdi", "gdi", "bin", "img", "ccd", "mds", "nrg", "pbp",
    "m3u", "toc", "gcm", "rvz", "wbfs", "wia", "cso", "dol",
))

_platform_key_rx = re.compile(r"[^a-z0-9]+")


class Request:
    """One scraper call as seen by a provider."""

    def __init__(self, query: Dict[str, str], settings: Dict[str, Any], bulk: bool = False):
        self.query = query
        self.settings = settings
        #: True while a whole folder is being scanned. A source with a small
        #: daily or monthly allowance, or one that asks not to be scraped in
        #: bulk, is left out of those and used for single games only.
        self.bulk = bulk
        self.platformids = _platform_ids(query.get("platformids", ""))

    def get(self, key: str, default: str = "") -> str:
        value = self.query.get(key)
        return value if isinstance(value, str) else default

    def platform_id(self, provider_name: str) -> str:
        value = self.platformids.get(provider_name)
        return value.strip() if isinstance(value, str) else ""

    def title(self) -> str:
        """The title Kodi parsed, or one parsed here from the file name."""
        title = self.get("title").strip()
        if not title and self.get("filename"):
            title = namer.parse(self.get("filename"))["title"]
        return title

    def regions(self) -> List[str]:
        return [r.strip() for r in self.get("regions").lower().split(",") if r.strip()]

    def preferred_regions(self) -> List[str]:
        """The player's regions, in their order, before the dump's own."""
        return [r.strip() for r in self.get("preferredregions").lower().split(",") if r.strip()]

    def hashes(self) -> Dict[str, str]:
        """The hashes Kodi computed, lower case, keyed by query parameter."""
        out = {}
        for key in HASH_PARAMS:
            value = self.get(key).strip().lower()
            if value:
                out[key] = value
        return out

    def cache_days(self) -> int:
        try:
            return max(int(self.settings.get("cache_days", 30)), 1)
        except (TypeError, ValueError):
            return 30


def _platform_ids(raw: str) -> Dict[str, str]:
    try:
        ids = json.loads(raw or "{}")
    except ValueError:
        return {}
    return ids if isinstance(ids, dict) else {}


def platform_names(request: Request) -> List[str]:
    """Names the platform goes by, best first, for catalogues that have no id in platformids."""
    names: List[str] = []
    for key in ("launchbox", "hyperspin"):
        names.append(request.platform_id(key))
    libretro = request.platform_id("libretro")
    parts = [p.strip() for p in libretro.split(" - ") if p.strip()]
    if len(parts) >= 2:
        for part in parts[1:]:
            names.append(part if part.startswith(parts[0]) else "{} {}".format(parts[0], part))
            names.append(part)
    elif libretro:
        names.append(libretro)
    names.append(request.platform_id("esde"))
    names.append(request.get("platform"))
    return list(dict.fromkeys(n for n in names if n))


def medium_art_type(request: "Request") -> str:
    """What a picture of the game's own medium should be called."""
    name = request.get("filename") or request.get("path")
    _, _, extension = name.rpartition(".")
    return "disc" if extension.lower() in DISC_EXTENSIONS else "cartridge"


def platform_key(name: str) -> str:
    return _platform_key_rx.sub("", name.lower().replace("&", " and "))


def platform_keys(catalogue_name: str) -> List[str]:
    """Keys a catalogue's platform name answers to: whole, each slash part, the bracketed tag and what precedes it."""
    pieces = [catalogue_name]
    pieces.extend(catalogue_name.split("/"))
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", catalogue_name)
    if m:
        pieces.extend((m.group(1), m.group(2)))
    return [k for k in dict.fromkeys(platform_key(p) for p in pieces) if k]


class Provider:
    """A catalogue that can identify a file, describe a game and describe a platform.

    The defaults describe a provider that knows nothing: it is available only
    when every setting in required_settings holds a value, and it returns no
    candidates, no details and no platform.
    """

    name = ""
    required_settings: Tuple[str, ...] = ()

    #: True when details cost nothing beyond the find that already happened, as
    #: for a local catalogue. Such a provider may answer find with the details
    #: attached, sparing Kodi a second call per game.
    details_are_free = False

    #: False for a source with a small allowance, or one that asks not to be
    #: scraped in bulk. Such a provider is used during a scan only while its
    #: share for the period is unspent, and always for a single game.
    bulk_safe = True

    #: How many games such a source may be asked about in a month, and the
    #: setting a person can change it with. Zero means no limit.
    monthly_budget = 0
    budget_setting = ""

    def budget_limit(self, settings: Dict[str, Any]) -> int:
        if not self.budget_setting:
            return self.monthly_budget
        try:
            return max(int(settings.get(self.budget_setting, self.monthly_budget)), 0)
        except (TypeError, ValueError):
            return self.monthly_budget

    def __init__(self, log: Log):
        self.log = log

    def available(self, settings: Dict[str, Any]) -> bool:
        return all(settings.get(key) for key in self.required_settings)

    def credentials(self, settings: Dict[str, Any]) -> Dict[str, str]:
        return {key: str(settings.get(key) or "") for key in self.required_settings}

    def prefetch(self, requests: Sequence["Request"]) -> None:
        """Warm up for a batch of queries. A provider that can answer many at
        once does so here, so find and details cost nothing after it."""

    def find(self, request: Request) -> List[dict]:
        return []

    def details(self, candidate_id: str, request: Request) -> Optional[Dict[str, Any]]:
        return None

    def platform(self, request: Request) -> Optional[Dict[str, Any]]:
        return None


class Cache:
    """JSON documents in one folder, each valid for a number of days; memory only without a folder."""

    def __init__(self, folder: str = ""):
        self.folder = folder
        self.memory: Dict[str, Tuple[float, Any]] = {}

    def load(self, name: str, days: float) -> Optional[Any]:
        limit = time.time() - days * 86400
        hit = self.memory.get(name)
        if hit and hit[0] >= limit:
            return hit[1]
        path = self._path(name)
        if not path or not os.path.isfile(path) or os.path.getmtime(path) < limit:
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                value = json.load(f)
        except (OSError, ValueError):
            return None
        self.memory[name] = (os.path.getmtime(path), value)
        return value

    def save(self, name: str, value: Any) -> None:
        self.memory[name] = (time.time(), value)
        path = self._path(name)
        if not path:
            return
        os.makedirs(self.folder, exist_ok=True)
        partial = path + ".part"
        with open(partial, "w", encoding="utf-8") as f:
            json.dump(value, f)
        os.replace(partial, path)

    def _path(self, name: str) -> str:
        return os.path.join(self.folder, name + ".json") if self.folder else ""


class OnlineProvider(Provider):
    """A provider backed by a web API, with a cache folder of its own under the add-on's cache dir."""

    folder = ""

    #: How long a refusal is honoured, in days. Kept short: a 429 is usually a
    #: rate limit rather than a spent allowance, and the source is worth
    #: another try later in a long scan.
    REFUSAL_DAYS = 0.25
    #: How long a spent monthly allowance is honoured. Until the month is out.
    ALLOWANCE_DAYS = 31
    #: Cache document holding the refusal
    REFUSAL = "refused"

    def __init__(self, log: Log, cache_dir: str = ""):
        super().__init__(log)
        self.cache = Cache(os.path.join(cache_dir, self.folder) if cache_dir else "")
        self._refusal: Any = _UNSET

    @property
    def exhausted(self) -> bool:
        """Whether the source has asked not to be called for the time being."""
        if self._refusal is _UNSET:
            stored = self.cache.load(self.REFUSAL, self.ALLOWANCE_DAYS)
            self._refusal = stored if (isinstance(stored, dict)
                                       and stored.get("until", 0) > time.time()) else None
        return self._refusal is not None

    def stop_asking(self, message: str, days: Optional[float] = None) -> None:
        """Record that the source refused, and say so once.

        Written down rather than held in memory because a scrape is its own
        process: a flag on the object lasts one game, so the source would be
        asked, refused and logged again for every game left in the scan.
        """
        if self.exhausted:
            return
        wait = self.REFUSAL_DAYS if days is None else days
        self._refusal = {"until": time.time() + wait * 86400, "why": message}
        self.cache.save(self.REFUSAL, self._refusal)
        self.log(message, True)
