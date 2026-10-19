"""Regions as Kodi's game library sends and takes them, and as the providers name them.

Kodi writes a region as a BCP 47 region subtag: a country's ISO 3166-1 code
("US", "GB") or a UN M.49 area ("150" for Europe). A market no territory
names exactly keeps No-Intro's word, "World" or "Scandinavia". The providers
name regions in full, as No-Intro writes them, so a region becomes a name on
the way in and a code on the way out.
"""

from typing import Any, Optional

# No-Intro's names, and the codes Kodi's NoIntroNaming gives them
CODES = {
    "Argentina": "AR", "Asia": "142", "Australia": "AU", "Brazil": "BR", "Canada": "CA",
    "China": "CN", "Denmark": "DK", "Europe": "150", "Finland": "FI", "France": "FR",
    "Germany": "DE", "Greece": "GR", "Hong Kong": "HK", "India": "IN", "Israel": "IL",
    "Italy": "IT", "Japan": "JP", "Korea": "KR", "Latin America": "419", "Mexico": "MX",
    "Netherlands": "NL", "New Zealand": "NZ", "Norway": "NO", "Poland": "PL", "Portugal": "PT",
    "Russia": "RU", "Spain": "ES", "Sweden": "SE", "Taiwan": "TW", "United Kingdom": "GB",
    "USA": "US",
}
NAMES = {code: name for name, code in CODES.items()}
_BY_LOWER = {name.lower(): code for name, code in CODES.items()}


def name(code: str) -> str:
    """The provider's name for a region Kodi sent, or what was sent if it names none."""
    code = code.strip()
    return NAMES.get(code.upper(), code)


def code(region: str) -> Optional[str]:
    """Kodi's code for a provider's region name; None for a region the source doesn't know."""
    region = region.strip()
    if not region or region.lower() == "unknown":
        return None
    return _BY_LOWER.get(region.lower(), region)


def encode(value: Any) -> Any:
    """A result with every "region" and "regions" in it written as Kodi's codes."""
    if isinstance(value, list):
        return [encode(item) for item in value]
    if not isinstance(value, dict):
        return value
    out = {}
    for key, item in value.items():
        if key == "region" and isinstance(item, str):
            out[key] = code(item) or ""
        elif key == "regions" and isinstance(item, (list, str)):
            names = item.split(",") if isinstance(item, str) else item
            codes = [code(n) for n in names if isinstance(n, str)]
            out[key] = list(dict.fromkeys(c for c in codes if c))
        else:
            out[key] = encode(item)
    return out
