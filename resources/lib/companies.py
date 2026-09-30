"""One name for each publisher and developer, whichever catalogue supplied it.

Catalogues credit several companies in one name ("Capcom, Sega", "Compile /
Sega"), add the company form ("SEGA Enterprises Ltd.") or a regional arm
("SEGA of America"), note a licence ("[Seibu Kaihatsu] (Taito license)"),
and disagree about case. A library built from them lists every variant as a
company of its own, and a filter on one finds a fraction of the games.
"""
import html
import re
from typing import Iterable, List

# Split on these, and on a comma not followed by a company form
_SEPARATORS = re.compile(r"\s*/\s*|\s*\|\s*|\s*;\s*")
_FORM = r"(?:inc|incorporated|ltd|limited|llc|co|corp|corporation|gmbh|s\.?a|s\.?r\.?l|k\.?k|plc|pty|bv|ag|ab|oy)\.?"
_COMMA = re.compile(
    r",(?!\s*(?:inc|incorporated|ltd|limited|llc|co|corp|corporation|gmbh|s\.?a|s\.?r\.?l|k\.?k|plc|pty|bv|ag|ab|oy)\b)\s*",
    re.IGNORECASE)

# A licence noted in brackets, and square brackets around a name
_LICENCE = re.compile(r"\s*\([^)]*licen[cs][^)]*\)", re.IGNORECASE)
_BOOTLEG = re.compile(r"^bootleg\s*\((.+)\)$", re.IGNORECASE)
_SQUARE = re.compile(r"\[([^\]]*)\]")

# The company form at the end of a name, as often as it repeats ("Co., Ltd.")
_TRAILING_FORM = re.compile(r"[\s,]+" + _FORM + r"\s*$", re.IGNORECASE)
# A regional arm of the company
_REGION = re.compile(
    r"\s+(?:of\s+(?:america|europe|japan)|america|europe|usa|u\.s\.a\.|uk|japan|germany|france)\s*$",
    re.IGNORECASE)

_NOT_A_NAME = {"", "unknown", "<unknown>", "n/a", "na", "none", "various", "-"}

# Keys are compared lowercased with spacing and punctuation removed
ALIASES = {
    "sega": "Sega", "segaenterprises": "Sega", "nintendo": "Nintendo", "capcom": "Capcom",
    "konami": "Konami", "namco": "Namco", "taito": "Taito", "hudson": "Hudson Soft",
    "hudsonsoft": "Hudson Soft", "atari": "Atari", "jaleco": "Jaleco", "irem": "Irem",
    "tecmo": "Tecmo", "koei": "Koei", "enix": "Enix", "squaresoft": "Square", "square": "Square",
    "ubisoft": "Ubisoft", "electronicarts": "Electronic Arts", "activision": "Activision",
}

_key_rx = re.compile(r"[^a-z0-9]+")


def key(name: str) -> str:
    return _key_rx.sub("", name.lower())


def _clean(name: str) -> str:
    name = html.unescape(name).strip()
    bootleg = _BOOTLEG.match(name)
    if bootleg:
        name = bootleg.group(1)
    name = _LICENCE.sub("", name)
    name = _SQUARE.sub(r"\1", name).strip(" ,")
    # The form and the region can each hide the other ("Taito Corporation Japan")
    while True:
        shorter = _TRAILING_FORM.sub("", name).strip(" ,")
        if len(_REGION.sub("", shorter).strip(" ,")) >= 3:
            shorter = _REGION.sub("", shorter).strip(" ,")
        if shorter == name or not shorter:
            break
        name = shorter
    return ALIASES.get(key(name), name)


def split(name: str) -> List[str]:
    """The companies credited in one catalogue name."""
    parts = []
    for piece in _SEPARATORS.split(html.unescape(name)):
        parts.extend(_COMMA.split(piece))
    return [p for p in (part.strip() for part in parts) if p]


def normalise(names: Iterable[str]) -> List[str]:
    """Each company once, under its one name."""
    out: List[str] = []
    seen = set()
    for name in names:
        for part in split(str(name or "")):
            clean = _clean(part)
            if clean.lower() in _NOT_A_NAME or key(clean) in seen:
                continue
            seen.add(key(clean))
            out.append(clean)
    return out
