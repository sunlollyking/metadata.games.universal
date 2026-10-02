"""ArcadeDB, for the pictures and write-up of an arcade set that others lack.

ArcadeDB (adb.arcadeitalia.net) holds MAME's own title and gameplay captures,
flyers and marquees for every set MAME knows, and Arcade History's text about
it. Most of what it describes is also in the other catalogues; what only it has
is the long tail -- mahjong and quiz boards, medal games, prototypes -- where
nothing else has a picture.

It is only asked about a set the arcade provider has already identified, by
the set's MAME name, and it comes last: its text fills a game no other
catalogue describes rather than replacing one that does.
"""
import re
from typing import Any, Dict, List, Optional

from .. import net
from . import OnlineProvider, Request

API = "https://adb.arcadeitalia.net/service_scraper.php"
#: Seconds between two calls, so that a scan does not hammer a site run by one person
MIN_INTERVAL = 1.0
#: The picture each of ArcadeDB's fields holds, by the library's name for it
ART_FIELDS = (
    ("titlescreen", "url_image_title"),
    ("screenshot", "url_image_ingame"),
    ("flyer", "url_image_flyer"),
    ("marquee", "url_image_marquee"),
    ("cabinet", "url_image_cabinet"),
)
#: Shorter than this, Arcade History's text is a label rather than a description
MIN_OVERVIEW = 40
SECTION = re.compile(r"\n- [A-Z][A-Z /&]+ -\n")
#: The line naming the game, its year and maker: "Galaga (c) 1981 Namco."
CREDIT = re.compile(r"\(c\) [0-9?x]{4}")


def overview(history: str) -> str:
    """Arcade History's description of a game, without its headings and lists.

    An entry opens with what kind of machine it is and a line crediting the
    game, then describes it, then runs through sections -- TECHNICAL, TRIVIA,
    STAFF -- of which only the description reads as a plot.
    """
    text = (history or "").replace("\r\n", "\n")
    body = SECTION.split("\n" + text)[0]
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    # The first paragraph says what kind of machine this is, and one credits it
    kept = [p for p in paragraphs[1:] if not CREDIT.search(p)
            and not re.match(r"(?i)see the (original|parent)", p)]
    result = "\n\n".join(kept)
    return result if len(result) >= MIN_OVERVIEW else ""


class ArcadeDbProvider(OnlineProvider):
    name = "arcadedb"
    folder = "arcadedb"

    def find(self, request: Request) -> List[dict]:
        romset = request.get("romset")
        row = self._row(romset, request) if romset else None
        if not row:
            return []
        return [{"id": romset, "title": request.get("title") or row.get("title", ""),
                 "score": 1.0, "matchedby": "hash"}]

    def details(self, candidate_id: str, request: Request) -> Optional[Dict[str, Any]]:
        row = self._row(candidate_id, request)
        if not row:
            return None
        out: Dict[str, Any] = {"version": 1}
        text = overview(row.get("history", ""))
        if text:
            out["overview"] = text
        art = {art_type: [{"url": row[field]}] for art_type, field in ART_FIELDS if row.get(field)}
        if art:
            out["art"] = art
        return out

    def _row(self, romset: str, request: Request) -> Optional[Dict[str, Any]]:
        """ArcadeDB's entry for one set, from the cache when it has been asked before."""
        key = "set-" + re.sub(r"[^a-z0-9_]", "_", romset.lower())
        cached = self.cache.load(key, request.cache_days())
        if cached is not None:
            return cached or None
        try:
            answer = net.get_json(API, {"ajax": "query_mame", "game_name": romset, "lang": "en"},
                                  log=self.log, min_interval=MIN_INTERVAL)
        except net.Error as err:
            if err.status in (429, 503):
                self.stop_asking("ArcadeDB asked for a pause: {}".format(err))
            else:
                self.log("ArcadeDB: {}".format(err), False)
            return None
        except ValueError:
            self.log("ArcadeDB answered {} with something other than JSON".format(romset), False)
            return None
        rows = [r for r in (answer or {}).get("result") or []
                if isinstance(r, dict) and r.get("game_name") == romset]
        row = rows[0] if rows else {}
        # Remembered either way, so a set ArcadeDB does not know is not asked again
        self.cache.save(key, row)
        return row or None
