"""Parse a ROM file name into a title plus release attributes.

Handles No-Intro / Redump (Title (Region) (Langs) (Rev 1) (Beta) ...),
TOSEC (Title (1985)(Publisher)[a][cr Group]) and GoodTools ([!] [b1] [h1]).
Everything recognised is stripped into fields; what is left is the title.
"""
import re
from typing import Any, Dict, List

REGIONS = {
    "usa": "USA", "us": "USA", "u": "USA", "canada": "Canada",
    "europe": "Europe", "eu": "Europe", "e": "Europe",
    "japan": "Japan", "jp": "Japan", "j": "Japan",
    "world": "World", "w": "World", "asia": "Asia",
    "australia": "Australia", "brazil": "Brazil", "china": "China", "france": "France",
    "germany": "Germany", "italy": "Italy", "spain": "Spain", "netherlands": "Netherlands",
    "sweden": "Sweden", "korea": "Korea", "taiwan": "Taiwan", "hong kong": "Hong Kong",
    "uk": "United Kingdom", "united kingdom": "United Kingdom", "russia": "Russia",
    "poland": "Poland", "finland": "Finland", "denmark": "Denmark", "norway": "Norway",
    "portugal": "Portugal", "greece": "Greece", "israel": "Israel", "india": "India",
    "mexico": "Mexico", "argentina": "Argentina", "unknown": "Unknown",
    "scandinavia": "Scandinavia", "latin america": "Latin America",
}
LANGS = {"en", "ja", "fr", "de", "es", "it", "nl", "pt", "sv", "no", "da", "fi", "zh",
         "ko", "pl", "ru", "cs", "hu", "el", "tr", "ar", "he", "ca", "th", "hr", "ro", "bg",
         "uk", "sk", "sl", "lt", "lv", "et", "ga", "eu", "gl", "id", "ms", "vi", "fa"}
DEVSTATUS = [
    (re.compile(r"^beta( ?\d+)?$", re.I), "beta"),
    (re.compile(r"^proto(type)?( ?\d+)?$", re.I), "proto"),
    (re.compile(r"^sample$", re.I), "sample"),
    (re.compile(r"^(demo|kiosk|preview|trial|taikenban|kiosk demo|demo \d+)(.*)$", re.I), "demo"),
    (re.compile(r"^alpha$", re.I), "alpha"),
    (re.compile(r"^debug( version)?$", re.I), "debug"),
    (re.compile(r"^(program|check program|sample program|test program)$", re.I), "program"),
]
LICENCE = [
    (re.compile(r"^unl(icensed)?$", re.I), "unlicensed"),
    (re.compile(r"^(pirate|bootleg( of .*)?)$", re.I), "pirate"),
    (re.compile(r"^aftermarket$", re.I), "aftermarket"),
    (re.compile(r"^homebrew$", re.I), "homebrew"),
    (re.compile(r"^pd$", re.I), "homebrew"),
]
REV = re.compile(r"^(rev|revision|version|v)\.? ?([0-9][0-9a-z.]*|[a-z])$", re.I)
ALT = re.compile(r"^alt( ?\d+)?$", re.I)
# TOSEC writes the version bare after the title: "Abuse v2.9 (1990)(...)"
BARE_VERSION = re.compile(r"\s+(v\d+(?:[._]\d+)*[a-z]?)$")
DISC = re.compile(r"^(disc|disk|side|tape|cd|cart|part) ?([0-9a-z]+)( of (\d+))?$", re.I)
TOSEC_YEAR = re.compile(r"^(19|20)\d\d(-\d\d(-\d\d)?)?$|^(19|20)[x?][x?]$|^(19|20)\d[x?]$")
BRACKET_TAGS = re.compile(r"\[([^\]]*)\]")
PAREN_TAGS = re.compile(r"\(([^()]*)\)")
# How to boot it, not what it is: "{V1 mode}", "{4MHz}", "{hold @+GRPH}"
BRACE_TAGS = re.compile(r"\{([^}]*)\}")
EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,4}$")
LEADING_NUMBER = re.compile(r"^0\d{2,4}\s+-?\s*")
ARTICLE = re.compile(r"^([^-]*?), (The|A|An|Le|La|Les|Der|Die|Das|El|Los|Las)((?: - .*)?)$", re.I)
NOISE = {"gb compatible", "sgb enhanced", "enhancement chip", "rumble version",
         "virtual console", "nintendo power", "np", "st", "mb", "wii virtual console",
         "3ds virtual console", "wii u virtual console", "switch online", "en,ja"}


def parse(filename: str, strip_extension: bool = True) -> Dict[str, Any]:
    """Split a file or catalogue name into title and tags.

    Catalogue names carry no extension, so callers pass strip_extension=False
    for them to keep a trailing ".2" of a version number intact.
    """
    name = filename
    if strip_extension:
        name = EXTENSION.sub("", name)
    # "0123 - Game" is a catalogue number a DS set puts in front of the title,
    # but "007 - GoldenEye" is the game's own name with its number moved to the
    # front. The number is taken off and kept, so a match can be tried both ways.
    leading = LEADING_NUMBER.match(name)
    catalogue_number = leading.group(0).strip(" -") if leading else ""
    name = LEADING_NUMBER.sub("", name)
    out = {
        "title": None, "regions": [], "languages": [], "revision": None,
        "devstatus": "retail", "licence": "licensed", "alt": False, "bad": False,
        "verified": False, "hack": False, "modified": False, "translation": None, "disc": None,
        "discs": None, "year": None, "publisher": None, "unknown": [],
        "number": catalogue_number,
    }
    for tag in BRACKET_TAGS.findall(name):
        t = tag.strip()
        tl = t.lower()
        if tl == "!":
            out["verified"] = True
        elif re.match(r"^b\d*$", tl):
            out["bad"] = True
        # A game made from another. "[h1]" or "[h Vimm]" alone is a modified dump
        # of the game itself - a crack intro, a header or title fix.
        elif tl == "hack" or tl.startswith("h of "):
            out["hack"] = True
        # GoodTools and TOSEC write these in lower case, where "[HD]" is a hard
        # disk version
        elif re.match(r"^[hfopt](\d|[A-Z]|\s|$)", t) and not tl.startswith("t-") and not tl.startswith("t+"):
            if tl[0] == "h":
                out["modified"] = True
            elif tl[0] == "p":
                out["licence"] = "pirate"
            elif tl[0] == "t":
                out["unknown"].append(t)
        elif re.match(r"^a\d*$", tl):
            out["alt"] = True
        elif tl.startswith("t+") or tl.startswith("t-"):
            out["translation"] = t[2:4].lower()
        elif tl.startswith("cr ") or tl.startswith("cr-"):
            out["unknown"].append(t)
        elif tl == "bios":
            out["devstatus"] = "bios"
        else:
            out["unknown"].append(t)
    name = BRACKET_TAGS.sub("", name)
    out["unknown"].extend(t.strip() for t in BRACE_TAGS.findall(name))
    name = BRACE_TAGS.sub("", name)

    for tag in PAREN_TAGS.findall(name):
        t = tag.strip()
        tl = t.lower()
        parts = [p.strip() for p in t.split(",")]
        pl = [p.lower() for p in parts]
        if all(p in REGIONS for p in pl):
            out["regions"].extend(REGIONS[p] for p in pl)
            continue
        if all(p in LANGS for p in pl) and len(pl) >= 1 and all(len(p) == 2 for p in pl):
            out["languages"].extend(pl)
            continue
        if REV.match(t):
            out["revision"] = t
            continue
        m = DISC.match(t)
        if m:
            out["disc"] = m.group(2)
            out["discs"] = m.group(4)
            continue
        hit = False
        for rx, val in DEVSTATUS:
            if rx.match(t):
                out["devstatus"] = val
                hit = True
                break
        if hit:
            continue
        for rx, val in LICENCE:
            if rx.match(t):
                # "(Aftermarket) (Unl)": the more particular tag is the one kept
                if out["licence"] not in ("aftermarket", "homebrew"):
                    out["licence"] = val
                hit = True
                break
        if hit:
            continue
        if ALT.match(t):
            out["alt"] = True
            continue
        # "(S2 Hack)": a hack, and of which game
        if tl in ("hack", "hacked") or tl.endswith(" hack"):
            out["hack"] = True
            continue
        if TOSEC_YEAR.match(t):
            out["year"] = t[:4] if t[:4].isdigit() else None
            out["_tosec"] = True
            continue
        if tl in NOISE:
            continue
        if out.get("_tosec") and out["publisher"] is None and not any(ch.isdigit() for ch in t[:1]):
            out["publisher"] = t
            continue
        out["unknown"].append(t)
    name = PAREN_TAGS.sub("", name)
    title = re.sub(r"\s+", " ", name).strip(" -_")
    version = BARE_VERSION.search(title)
    if version:
        out["revision"] = out["revision"] or version.group(1)
        title = title[:version.start()].strip(" -_")
    out["title"] = title
    out["display"] = display_title(title)
    return out


def display_title(title: str) -> str:
    """Restore a trailing article: "Legend of Zelda, The" -> "The Legend of Zelda"."""
    m = ARTICLE.match(title)
    if m:
        return "{} {}{}".format(m.group(2), m.group(1), m.group(3))
    return title


_norm_rx = re.compile(r"[^a-z0-9]+")


def alternate_titles(title: str) -> List[str]:
    """One game under both its names.

    A catalogue entry often carries the Western and Japanese title together,
    joined by a slash -- "Blue's Journey / Raguy". Either half identifies the
    game; the two of them run together identifies nothing.
    """
    parts = [p.strip() for p in re.split(r"\s*/\s*", title)]
    parts = [p for p in parts if p]
    return parts or [title]


def spacing_variants(title: str) -> List[str]:
    """The same name with its spacing closed up.

    Catalogues disagree about whether a compound name is one word or two --
    "Castlequest" against "Castle Quest" -- and a search for one does not find
    the other.
    """
    joined = re.sub(r"\s+", "", title)
    return [joined] if joined and joined != title else []


def subtitle_head(title: str) -> str:
    """"Galaxy Fight - Universal Warriors" -> "Galaxy Fight"; "" if there is none."""
    head = title.split(" - ")[0].strip()
    return head if head and head != title.strip() else ""


def normalise(title: str) -> str:
    """Key for exact comparison: lower, article-neutral, punctuation-free."""
    t = display_title(title).lower()
    t = t.replace("&", " and ")
    t = re.sub(r"\b(the|a|an)\b", " ", t)
    t = _norm_rx.sub("", t)
    return t


# GoodTools numbers every hack of a game under the game's own name, and names
# a hack after the revision it was made from: "Sonic the Hedgehog 2 Rev 1 [h11]"
_NUMBERED_HACK = re.compile(r"\[h\d+[a-z]?\]", re.IGNORECASE)
_TRAILING_REVISION = re.compile(r"\s+(?:rev\s*[a-z0-9]+|v\d+(?:\.\d+)*)$", re.IGNORECASE)


def without_revision(title: str) -> str:
    """A title without the revision a catalogue may end it with."""
    return _TRAILING_REVISION.sub("", title or "")


def hack_name(dump_name: str, filename: str, game_title: str) -> str:
    """The name a hack of game_title goes by, or "" where it is the game itself.

    A catalogue that names the dump as another work, "Mario Adventure", is
    believed, though the file's own name for it is kept where it names that
    work too. A numbered GoodTools hack says nothing, so only the file can name
    it, as "Sonic 2 Delta II". A group's tag, "[h Homesoft]", is a cracked or
    re-introduced copy of the game, whatever the file happens to be called.
    """
    game = normalise(without_revision(game_title))
    dumped = parse(dump_name or "", strip_extension=False)["display"] or ""
    own = parse(filename)["display"] if filename else ""
    if dumped and normalise(without_revision(dumped)) != game:
        return own if own and normalise(own) != game else dumped
    if dump_name and _NUMBERED_HACK.search(dump_name) and own and normalise(own) != game:
        return own
    return ""
