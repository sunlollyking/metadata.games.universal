"""One spelling for each age rating, whichever catalogue supplied it.

Catalogues name the same board and classification differently ("CLASS_IND"
and "ClassInd", "MA 15+" and "MA15+", CERO "free" for what is now "A"), and
ScreenScraper files things that are not ratings at all under a board: its
"SEGA" classifications include UK magazine review references such as
"pro_UK_01" (Sega Pro issue 1) and "Force16UK" (Sega Force issue 16).
"""
import re
from typing import Dict, Iterable, List, Optional

# Keys are compared lowercased with spacing and punctuation removed
BOARDS = {
    "esrb": "ESRB", "pegi": "PEGI", "cero": "CERO", "usk": "USK", "grac": "GRAC", "grb": "GRB",
    "classind": "CLASS_IND", "acb": "ACB", "oflc": "OFLC", "elspa": "ELSPA", "vrc": "VRC",
    "djctq": "DJCTQ", "csrr": "CSRR", "gsrr": "CSRR", "iarc": "IARC", "sell": "SELL", "aama": "AAMA",
    "hsrs": "HSRS", "esra": "ESRA", "sega": "SEGA", "tectoy": "Tectoy", "jv": "JV", "ss": "SS",
}

# Per board, spellings of a classification and the one used for it
VALUES = {
    "ESRB": {"kidstoadults": "KA", "ka": "KA", "notrated": "NOT RATED", "e10": "E10+"},
    "CERO": {"free": "A", "all": "A"},
    "GRAC": {"all": "All", "12": "12", "15": "15", "18": "18", "19": "18", "testing": "Testing"},
    "ACB": {"ma15": "MA15+", "r18": "R18+"},
    "CLASS_IND": {"livre": "L"},
}

# ScreenScraper writes its "JV" ages in French ("+12 ans"); they keep their board
# and take the "12+" form other boards use
_FRENCH_AGE = re.compile(r"^\+\s*(\d+)\s*ans?$", re.IGNORECASE)

# Not ratings: magazine review references ScreenScraper files under "SEGA"
NOT_A_RATING = re.compile(r"^(pro_uk_\d+|force\d+uk|forcemega\d+|masterforce\d+)$", re.IGNORECASE)

_key_rx = re.compile(r"[^a-z0-9]+")


def _key(text: str) -> str:
    return _key_rx.sub("", text.lower())


def board(name: str) -> str:
    """The board's one name, or the name as given for a board not listed."""
    return BOARDS.get(_key(name), name.strip())


def value(board_name: str, rating: str) -> Optional[str]:
    """The classification's one spelling, or None if it is not a rating."""
    rating = rating.strip()
    if not rating or NOT_A_RATING.match(rating):
        return None
    french = _FRENCH_AGE.match(rating)
    if board_name == "JV" and french:
        return french.group(1) + "+"
    return VALUES.get(board_name, {}).get(_key(rating), rating)


def normalise(ratings: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    """Each board once, under its one name, with its classification's one spelling.

    Where catalogues disagree about a board, the first to answer stands.
    """
    out: List[Dict[str, str]] = []
    seen = set()
    for rating in ratings:
        name = board(str(rating.get("board") or ""))
        text = value(name, str(rating.get("value") or ""))
        if not name or text is None or name in seen:
            continue
        seen.add(name)
        out.append({**rating, "board": name, "value": text})
    return out


# IGDB's current API numbers its rating categories ESRB-first, where the old
# enum numbered PEGI first, so reading one with the other's table stored
# PEGI letters and ESRB numbers. What each wrong value really was:
_IGDB_ESRB = {"3": "RP", "7": "EC", "12": "E", "16": "E10+", "18": "T", "RP": "M"}
_IGDB_PEGI = {"E": "3", "E10+": "7", "T": "12", "M": "16", "AO": "18"}
_ADULT = {("PEGI", "16"), ("PEGI", "18"), ("USK", "16"), ("USK", "18"), ("ACB", "MA15+"),
          ("ACB", "R18+"), ("CERO", "D"), ("CERO", "Z"), ("GRAC", "18"), ("ESRB", "M")}


def repair_igdb(ratings: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Undo the rating-table mix-up in ratings stored before it was fixed.

    Only for a library scraped with it: a PEGI letter or an ESRB number cannot
    be right, and IGDB's ESRB "M" was stored as "RP". "EC" stood for "AO", but
    it is a real rating too, so it becomes "AO" only where another board
    rates the game for adults.
    """
    fixed = []
    for rating in ratings:
        repaired = dict(rating)
        if rating["board"] == "ESRB" and rating["value"] != "EC":
            repaired["value"] = _IGDB_ESRB.get(rating["value"], rating["value"])
        elif rating["board"] == "PEGI":
            repaired["value"] = _IGDB_PEGI.get(rating["value"], rating["value"])
        fixed.append(repaired)

    if any((r["board"], r["value"]) in _ADULT for r in fixed):
        for rating in fixed:
            if rating["board"] == "ESRB" and rating["value"] == "EC":
                rating["value"] = "AO"
    return normalise(fixed)
