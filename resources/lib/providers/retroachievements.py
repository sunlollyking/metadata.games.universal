"""RetroAchievements provider: identifies a file by its RetroAchievements hash and describes the game.

Web API, base https://retroachievements.org/API/. Every call carries the
user's web API key as ``y`` (settings ra_username, ra_api_key).

* ``API_GetGameList.php?i=<console id>&h=1&f=0`` lists a console's games
  with their hashes; ``i`` is the ``retroachievements`` entry of
  platformids. The list is cached per console and refreshed by age.
* ``API_GetGameExtended.php?i=<game id>`` adds publisher, developer, genre,
  release date, art and the achievement set.
* ``API_GetUserCompletionProgress.php`` lists every game the signed-in person
  has played, with how many of its achievements they have earned. That is
  about the person rather than about the game, so it is asked for on its own
  and not during a scan.

Identification uses the ``rahash`` query parameter. Without it the file's
MD5 stands in, but only on the consoles in MD5_CONSOLES, whose
RetroAchievements hash is the MD5 of the whole file; NES, SNES, N64, the
headered handhelds and the disc systems hash a transformed image instead.
Candidate ids are RetroAchievements game ids. Art paths are relative to
https://media.retroachievements.org/; the site's placeholder images are
left out.

Beyond the scraper protocol, details carry an ``achievements`` object:
``{"total": <achievements in the set>, "points": <points they award>}``.
"""
import re
from typing import Any, Dict, List, Optional

from .. import namer
from .. import net
from . import OnlineProvider, Request

BASE_URL = "https://retroachievements.org/API/"
GAME_LIST = "API_GetGameList.php"
GAME_EXTENDED = "API_GetGameExtended.php"
USER_PROGRESS = "API_GetUserCompletionProgress.php"
#: The most the service returns in one answer
PROGRESS_PAGE = 500
#: A person with more played games than this is not worth another round trip
PROGRESS_LIMIT = 10000
MEDIA_URL = "https://media.retroachievements.org/"
MIN_INTERVAL = 0.25
PLACEHOLDERS = ("/Images/000001.png", "/Images/000002.png")
MD5_CONSOLES = frozenset((
    "1", "4", "5", "6", "10", "11", "14", "15", "17", "23", "24", "25", "28", "29", "30", "31", "33",
    "34", "37", "38", "44", "45", "46", "47", "50", "52", "53", "55", "57", "59", "60", "63", "64",
    "65", "66", "68", "69", "72", "73", "74", "80",
))
ART = (("boxfront", "ImageBoxArt"), ("titlescreen", "ImageTitle"), ("screenshot", "ImageIngame"),
       ("icon", "ImageIcon"))
GENRE_SPLIT = re.compile(r"\s*/\s*|,\s*")


def int_or(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback

DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


class RetroAchievementsProvider(OnlineProvider):
    name = "retroachievements"
    folder = "ra"
    required_settings = ("ra_username", "ra_api_key")

    def progress(self, request: Request) -> Dict[str, Dict[str, int]]:
        """How far the signed-in person has got with every game they have played.

        Keyed by RetroAchievements game id. ``hardcore`` counts only the ones
        earned with savestates and rewind turned off, which is the number the
        site puts on a profile.
        """
        user = str(request.settings.get("ra_username") or "").strip()
        if not user:
            return {}

        out: Dict[str, Dict[str, int]] = {}
        offset = 0
        while offset < PROGRESS_LIMIT:
            try:
                answer = self._call(USER_PROGRESS, {"u": user, "c": PROGRESS_PAGE, "o": offset},
                                    request)
            except net.Error as err:
                self.log("achievement progress failed: {}".format(err), True)
                break
            results = (answer or {}).get("Results")
            if not isinstance(results, list) or not results:
                break
            for row in results:
                if not isinstance(row, dict):
                    continue
                game_id = str(row.get("GameID") or "")
                total = int_or(row.get("MaxPossible"))
                if not game_id or total <= 0:
                    continue
                out[game_id] = {"total": total,
                                "earned": int_or(row.get("NumAwarded")),
                                "hardcore": int_or(row.get("NumAwardedHardcore"))}
            if len(results) < PROGRESS_PAGE:
                break
            offset += PROGRESS_PAGE
        return out

    def find(self, request: Request) -> List[dict]:
        console = request.platform_id(self.name)
        if not console:
            return []
        games = self._game_list(console, request)
        if not games:
            return []
        rahash = request.get("rahash").strip().lower()
        if not rahash and console in MD5_CONSOLES:
            rahash = request.get("md5").strip().lower()
        if rahash:
            hits = [g for g in games if rahash in {str(h).lower() for h in g.get("Hashes") or []}]
            if hits:
                return [candidate(g, 1.0, "hash") for g in hits]
        key = namer.normalise(request.title())
        if not key:
            return []
        return [candidate(g, 0.9, "name") for g in games if namer.normalise(str(g.get("Title") or "")) == key]

    def details(self, candidate_id: str, request: Request) -> Optional[Dict[str, Any]]:
        game = self._game(candidate_id, request)
        if not isinstance(game, dict) or not game.get("Title"):
            return None
        out: Dict[str, Any] = {
            "version": 1,
            "title": str(game["Title"]),
            "developers": _one(game.get("Developer")),
            "publishers": _one(game.get("Publisher")),
            "genres": [g for g in GENRE_SPLIT.split(str(game.get("Genre") or "")) if g],
            "uniqueids": {self.name: str(game.get("ID") or candidate_id)},
            "art": {},
            "achievements": achievements(game),
        }
        released = release_date(game.get("Released"), game.get("ReleasedAtGranularity"))
        if released:
            out["releasedate"] = released
            out["year"] = int(released[:4])
        for art_type, field in ART:
            url = image_url(game.get(field))
            if url:
                out["art"][art_type] = [{"url": url}]
        return out

    def _game_list(self, console: str, request: Request) -> List[dict]:
        name = "console_" + console
        games = self.cache.load(name, request.cache_days())
        if games is None:
            try:
                games = self._call(GAME_LIST, {"i": console, "h": 1, "f": 0}, request)
            except net.Error as err:
                self.log("game list for console {} failed: {}".format(console, err), True)
                return []
            if not isinstance(games, list):
                self.log("game list for console {} is not a list".format(console), True)
                return []
            self.cache.save(name, games)
        return [g for g in games if isinstance(g, dict)]

    def _game(self, game_id: str, request: Request) -> Optional[dict]:
        name = "game_" + game_id
        game = self.cache.load(name, request.cache_days())
        if game is None:
            try:
                game = self._call(GAME_EXTENDED, {"i": game_id}, request)
            except net.Error as err:
                self.log("game {} failed: {}".format(game_id, err), True)
                return None
            if isinstance(game, dict) and game.get("Title"):
                self.cache.save(name, game)
        return game

    def _call(self, endpoint: str, params: Dict[str, Any], request: Request) -> Any:
        query = {"y": request.settings.get("ra_api_key")}
        query.update(params)
        return net.get_json(BASE_URL + endpoint, query, log=self.log, min_interval=MIN_INTERVAL)


def candidate(game: dict, score: float, matchedby: str) -> dict:
    return {"id": str(game.get("ID")), "title": str(game.get("Title") or ""), "score": score, "matchedby": matchedby}


def release_date(released: Any, granularity: Any) -> str:
    m = DATE.match(str(released or ""))
    if not m:
        return ""
    year, month, day = m.groups()
    grain = str(granularity or "day").lower()
    if grain == "year":
        return year
    if grain == "month":
        return "{}-{}".format(year, month)
    return "{}-{}-{}".format(year, month, day)


def image_url(path: Any) -> str:
    if not isinstance(path, str) or not path or path in PLACEHOLDERS:
        return ""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return MEDIA_URL + path.lstrip("/")


def achievements(game: dict) -> Dict[str, int]:
    entries = game.get("Achievements")
    items = list(entries.values()) if isinstance(entries, dict) else (entries if isinstance(entries, list) else [])
    points = 0
    for item in items:
        if isinstance(item, dict):
            try:
                points += int(item.get("Points") or 0)
            except (TypeError, ValueError):
                pass
    try:
        total = int(game.get("NumAchievements") or len(items))
    except (TypeError, ValueError):
        total = len(items)
    return {"total": total, "points": points}


def _one(value: Any) -> List[str]:
    text = str(value or "").strip()
    return [text] if text else []
