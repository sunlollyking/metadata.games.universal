"""ScreenScraper provider: identifies a ROM by hash or file name and returns its whole record in one call.

API v2, base https://api.screenscraper.fr/api2/. Every call carries the
developer credentials ``devid`` and ``devpassword`` (settings ss_devid,
ss_devpassword), ``softname=kodi``, the user's ``ssid`` and ``sspassword``
(settings ss_user, ss_password) and ``output=xml``.

* ``jeuInfos.php`` looks a ROM up by ``crc``, ``md5`` and ``sha1`` or by
  ``romnom`` and ``romtaille`` on one ``systemeid`` (the ``screenscraper``
  entry of platformids), or fetches a known ``gameid``. A miss is HTTP 404
  with a text body; 429 and 430 mean the account's thread limit was hit,
  and the call is retried once after a pause.
* ``systemesListe.php`` lists every system with its names, dates and media;
  it is cached and refreshed by age.

Candidate ids are ScreenScraper game ids. The record find fetched is kept
so details does not ask again. A record that came back for a file name is
only a candidate when its name or one of its ROM names is the file's:
ScreenScraper's own guess is never passed on. Names, dates and media exist
per region; the caller's ``regions`` come first, then ScreenScraper's
default region, world, US, Europe and Japan. Media URLs carry the
credentials ScreenScraper needs to serve them.
"""
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .. import namer
from .. import net
from . import OnlineProvider, Request, medium_art_type

BASE_URL = "https://api.screenscraper.fr/api2/"
GAME_INFO = "jeuInfos.php"
SYSTEM_LIST = "systemesListe.php"
SOFTNAME = "kodi"
THROTTLED = (429, 430)
RETRY_AFTER = 5.0
NAME_REGIONS = ("ss", "wor", "us", "eu", "jp")
ART_REGIONS = ("wor", "us", "eu", "jp")
# ScreenScraper writes regions as short codes; the library stores them in full
SS_REGION_NAMES = {
    "us": "USA", "eu": "Europe", "jp": "Japan", "wor": "World", "ss": "World", "asi": "Asia",
    "au": "Australia", "br": "Brazil", "ca": "Canada", "cn": "China", "de": "Germany",
    "dk": "Denmark", "es": "Spain", "fi": "Finland", "fr": "France", "gr": "Greece",
    "hk": "Hong Kong", "il": "Israel", "in": "India", "it": "Italy", "kr": "Korea",
    "mor": "Latin America", "mx": "Mexico", "nl": "Netherlands", "no": "Norway",
    "nz": "New Zealand", "pl": "Poland", "pt": "Portugal", "ru": "Russia", "se": "Sweden",
    "sw": "Scandinavia", "tw": "Taiwan", "uk": "United Kingdom", "ar": "Argentina",
}
SS_REGION_CODES = {name.lower(): code for code, name in SS_REGION_NAMES.items() if code != "ss"}
#: Everything the service offers a game, and what the library calls it. The
#: "support" pictures are of the medium itself and are named by the dump; see
#: MEDIUM_ART below.
ART = {
    "box-2D": "boxfront", "box-2D-back": "boxback", "box-2D-side": "boxspine", "box-texture": "boxfull",
    "box-3D": "box3d", "wheel": "clearlogo", "wheel-hd": "clearlogo", "wheel-carbon": "clearlogo",
    "wheel-steel": "clearlogo", "screenmarquee": "marquee", "screenmarqueesmall": "marquee",
    "marquee": "marquee", "ss": "screenshot", "sstitle": "titlescreen", "fanart": "fanart",
    "mixrbv1": "mix", "mixrbv2": "mix", "flyer": "flyer", "maps": "map", "bezel-16-9": "bezel",
    "steamgrid": "banner",
}

#: Pictures of the medium: the flat scan, its texture and the rendered one
MEDIUM_ART = ("support-2D", "support-texture", "support-3D")
ART_STRINGS = {"video": "trailer", "video-normalized": "trailer", "manuel": "manual"}
SYSTEM_ART = {"logo-monochrome": "logo", "wheel": "clearlogo", "photo": "photo", "illustration": "fanart",
              "controller": "controller", "icon": "icon"}
ROM_FLAGS = (("beta", "beta"), ("proto", "proto"), ("demo", "demo"))
STATUS_WORDS = {word for _, word in namer.DEVSTATUS}
PLAYERS = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d+))?\s*$")
DATE = re.compile(r"^\d{4}(-\d{2}){0,2}$")


class ScreenScraperProvider(OnlineProvider):
    name = "screenscraper"
    folder = "ss"
    required_settings = ("ss_devid", "ss_devpassword", "ss_user", "ss_password")

    def find(self, request: Request) -> List[dict]:
        system = request.platform_id(self.name)
        identity = self._identity(request)
        if not system or not identity:
            return []
        params = {"systemeid": system, "romtype": "rom"}
        params.update(identity)
        jeu = self._lookup(params, request)
        if jeu is None:
            return []
        if self._hash_matched(jeu, request):
            score, matchedby = 1.0, "hash"
        elif name_matches(jeu, request):
            score, matchedby = 0.9, "name"
        else:
            self.log("record {} {!r} is not {!r}; dropped".format(
                jeu.get("id"), game_name(jeu, NAME_REGIONS), request.title()), False)
            return []
        return [candidate(jeu, request, score, matchedby)]

    def details(self, candidate_id: str, request: Request) -> Optional[Dict[str, Any]]:
        jeu = self._cached(candidate_id, request)
        if jeu is None:
            params = {"gameid": candidate_id}
            system = request.platform_id(self.name)
            if system:
                params["systemeid"] = system
            jeu = self._lookup(params, request)
        return game_details(jeu, request) if jeu is not None else None

    def platform(self, request: Request) -> Optional[Dict[str, Any]]:
        system = request.platform_id(self.name)
        if not system:
            return None
        doc = self.cache.load("systems", request.cache_days())
        if doc is None:
            try:
                doc = {"xml": self._call(SYSTEM_LIST, {}, request)}
            except net.Error as err:
                if getattr(err, "status", None) == 429:
                    self.stop_asking("{} is turning requests away; not asking again "
                                     "for now".format(self.name))
                self.log("system list failed: {}".format(err), True)
                return None
            self.cache.save("systems", doc)
        root = parse(doc.get("xml", ""), self.log)
        if root is None:
            return None
        for systeme in root.iter("systeme"):
            if (systeme.findtext("id") or "").strip() == system:
                return system_info(systeme)
        return None

    def _identity(self, request: Request) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for param, key in (("crc", "crc32"), ("md5", "md5"), ("sha1", "sha1")):
            value = request.hashes().get(key)
            if value:
                out[param] = value
        filename = request.get("filename").strip()
        if filename:
            out["romnom"] = filename
            if request.get("size").strip().isdigit():
                out["romtaille"] = request.get("size").strip()
        return out

    def _hash_matched(self, jeu: ET.Element, request: Request) -> bool:
        sent = request.hashes()
        if not sent:
            return False
        rom = jeu.find("rom")
        if rom is None:
            return not request.get("filename").strip()
        for attr, key in (("romcrc", "crc32"), ("rommd5", "md5"), ("romsha1", "sha1")):
            if key in sent and field(rom, attr).lower() == sent[key]:
                return True
        return False

    def _lookup(self, params: Dict[str, Any], request: Request) -> Optional[ET.Element]:
        try:
            text = self._call(GAME_INFO, params, request)
        except net.Error as err:
            if err.status == 404:
                self.log("no ScreenScraper record for {!r}".format(request.get("filename") or params.get("gameid")), False)
            else:
                self.log("jeuInfos failed: {}".format(err), True)
            return None
        root = parse(text, self.log)
        jeu = root.find("jeu") if root is not None else None
        if jeu is None or not jeu.get("id"):
            return None
        self.cache.save("jeu_" + jeu.get("id"), {"xml": text})
        return jeu

    def _cached(self, game_id: str, request: Request) -> Optional[ET.Element]:
        doc = self.cache.load("jeu_" + game_id, request.cache_days())
        root = parse(doc.get("xml", ""), self.log) if isinstance(doc, dict) else None
        return root.find("jeu") if root is not None else None

    def _call(self, endpoint: str, params: Dict[str, Any], request: Request) -> str:
        settings = request.settings
        query: Dict[str, Any] = {
            "devid": settings.get("ss_devid"), "devpassword": settings.get("ss_devpassword"),
            "softname": SOFTNAME, "ssid": settings.get("ss_user"), "sspassword": settings.get("ss_password"),
            "output": "xml",
        }
        query.update(params)
        return net.get_text(BASE_URL + endpoint, query, log=self.log, throttled=THROTTLED, retry_after=RETRY_AFTER)


def parse(text: str, log) -> Optional[ET.Element]:
    try:
        return ET.fromstring(text)
    except ET.ParseError as err:
        log("ScreenScraper answer is not XML: {} ({})".format(err, " ".join(text.split())[:120]), True)
        return None


def region_name(code: str) -> str:
    """The full name for one of ScreenScraper's region codes."""
    code = (code or "").strip().lower()
    return SS_REGION_NAMES.get(code, code.upper() if code else "")


def preference(request: Request, fallback: Sequence[str]) -> List[str]:
    """The caller's regions as ScreenScraper's codes, then the usual fallbacks."""
    regions = [SS_REGION_CODES.get(r.lower(), r.lower()) for r in request.regions()]
    return regions + [r for r in fallback if r not in regions]


def text(elem: Optional[ET.Element]) -> str:
    return (elem.text or "").strip() if elem is not None else ""


def field(elem: ET.Element, key: str) -> str:
    """A ROM attribute, which older records carry as a child element instead."""
    value = elem.get(key)
    return value.strip() if value is not None else (elem.findtext(key) or "").strip()


def pick(elements: Sequence[ET.Element], attr: str, prefs: Sequence[str]) -> Optional[ET.Element]:
    for region in prefs:
        for elem in elements:
            if elem.get(attr) == region:
                return elem
    return elements[0] if elements else None


def game_name(jeu: ET.Element, prefs: Sequence[str]) -> str:
    return text(pick([n for n in jeu.findall("noms/nom") if text(n)], "region", prefs))


def name_matches(jeu: ET.Element, request: Request) -> bool:
    filename = request.get("filename").strip().casefold()
    if filename:
        roms = [jeu.find("rom")] + jeu.findall("roms/rom")
        if any(r is not None and field(r, "romfilename").casefold() == filename for r in roms):
            return True
    key = namer.normalise(request.title())
    return bool(key) and any(namer.normalise(text(n)) == key for n in jeu.findall("noms/nom"))


def candidate(jeu: ET.Element, request: Request, score: float, matchedby: str) -> dict:
    prefs = preference(request, NAME_REGIONS)
    out = {"id": jeu.get("id"), "title": game_name(jeu, prefs), "score": score, "matchedby": matchedby}
    date = release_date(jeu, prefs)
    if date:
        out["year"] = int(date[:4])
    return out


def release_date(jeu: ET.Element, prefs: Sequence[str]) -> str:
    dates = [d for d in jeu.findall("dates/date") if DATE.match(text(d))]
    chosen = pick(dates, "region", prefs)
    if chosen is None:
        return ""
    return min(text(d) for d in dates) if chosen.get("region") not in prefs else text(chosen)


def synopsis(jeu: ET.Element) -> str:
    return text(pick([s for s in jeu.findall("synopsis/synopsis") if text(s)], "langue", ("en",)))


def genres(jeu: ET.Element) -> List[str]:
    elems = [g for g in jeu.findall("genres/genre") if text(g)]
    if not elems:
        return []
    lang = "en" if any(g.get("langue") == "en" for g in elems) else elems[0].get("langue")
    same = [g for g in elems if g.get("langue") == lang]
    main = [g for g in same if g.get("principale") == "1"] or same
    return list(dict.fromkeys(text(g) for g in main))


def families(jeu: ET.Element) -> List[str]:
    names: Dict[str, str] = {}
    for fam in jeu.findall("familles/famille"):
        key = fam.get("id") or text(fam)
        if text(fam) and (key not in names or fam.get("langue") == "en"):
            names[key] = text(fam)
    return list(dict.fromkeys(names.values()))


def players(value: str) -> Optional[Dict[str, int]]:
    m = PLAYERS.match(value)
    if not m:
        return None
    low = int(m.group(1))
    high = int(m.group(2)) if m.group(2) else low
    return {"min": min(low, high), "max": max(low, high)} if high > 0 else None


def age_ratings(jeu: ET.Element) -> List[dict]:
    return [{"board": c.get("type"), "value": text(c), "descriptors": ""}
            for c in jeu.findall("classifications/classification") if c.get("type") and text(c)]


def rating(jeu: ET.Element) -> Optional[Dict[str, Any]]:
    try:
        note = float(text(jeu.find("note")) or 0)
    except ValueError:
        return None
    return {"screenscraper": {"rating": note, "max": 20, "votes": 0}} if note > 0 else None


def release(rom: ET.Element) -> Optional[dict]:
    filename = field(rom, "romfilename")
    if not filename or field(rom, "hack") == "1" or field(rom, "trad") == "1":
        return None
    tags = namer.parse(filename)
    regions = [region_name(r) for r in field(rom, "romregions").split(",") if r.strip()] or list(
        dict.fromkeys(tags["regions"]))
    status = next((word for flag, word in ROM_FLAGS if field(rom, flag) == "1"), "")
    if not status:
        status = tags["devstatus"] if tags["devstatus"] in STATUS_WORDS else "retail"
    licence = "unlicensed" if field(rom, "unl") == "1" else tags["licence"]
    return {
        "title": filename, "regions": regions, "languages": tags["languages"],
        "revision": tags["revision"] or "", "status": status, "licence": licence, "serial": "", "releasedate": "",
        "crc32": field(rom, "romcrc").lower(), "md5": field(rom, "rommd5").lower(),
        "sha1": field(rom, "romsha1").lower(),
        "size": int(field(rom, "romsize")) if field(rom, "romsize").isdigit() else 0,
    }


def media(elements: Sequence[ET.Element], mapping: Dict[str, str],
          prefs: Sequence[str]) -> Dict[str, List[Dict[str, str]]]:
    """Art entries by Kodi type, each type's regions in preference order."""
    art: Dict[str, List[Tuple[int, Dict[str, str]]]] = {}
    for m in elements:
        art_type = mapping.get(m.get("type") or "")
        url = text(m)
        if not art_type or not url:
            continue
        entry = {"url": url}
        region = m.get("region")
        if region:
            entry["region"] = region_name(region)
        rank = prefs.index(region) if region in prefs else len(prefs)
        art.setdefault(art_type, []).append((rank, entry))
    return {art_type: [e for _, e in sorted(entries, key=lambda x: x[0])] for art_type, entries in art.items()}


def game_details(jeu: ET.Element, request: Request) -> Dict[str, Any]:
    prefs = preference(request, NAME_REGIONS)
    art_prefs = preference(request, ART_REGIONS)
    medias = jeu.findall("medias/media")
    art_map = dict(ART, **{name: medium_art_type(request) for name in MEDIUM_ART})
    out: Dict[str, Any] = {
        "version": 1,
        "title": game_name(jeu, prefs),
        "originaltitle": game_name(jeu, ("ss",)),
        "overview": synopsis(jeu),
        "developers": [text(jeu.find("developpeur"))] if text(jeu.find("developpeur")) else [],
        "publishers": [text(jeu.find("editeur"))] if text(jeu.find("editeur")) else [],
        "genres": genres(jeu),
        "collections": families(jeu),
        "category": "retail",
        "ageratings": age_ratings(jeu),
        "uniqueids": {"screenscraper": jeu.get("id")},
        "releases": [r for r in (release(rom) for rom in jeu.findall("roms/rom")) if r],
        "art": media(medias, art_map, art_prefs),
    }
    date = release_date(jeu, prefs)
    if date:
        out["releasedate"] = date
        out["year"] = int(date[:4])
    count = players(text(jeu.find("joueurs")))
    if count:
        out["players"] = count
    ratings = rating(jeu)
    if ratings:
        out["ratings"] = ratings
    for name, entries in media(medias, ART_STRINGS, art_prefs).items():
        out[name] = entries[0]["url"]
    return out


def system_info(systeme: ET.Element) -> Dict[str, Any]:
    noms = systeme.find("noms")
    names = [text(noms.find(tag)) for tag in ("nom_eu", "nom_us")] if noms is not None else []
    names.append(text(noms.find("noms_commun")).split(",")[0].strip() if noms is not None else "")
    out: Dict[str, Any] = {"version": 1, "name": next((n for n in names if n), "")}
    manufacturer = text(systeme.find("compagnie"))
    if manufacturer:
        out["manufacturer"] = manufacturer
    for key, tag in (("released", "datedebut"), ("discontinued", "datefin")):
        value = text(systeme.find(tag))[:4]
        if value.isdigit():
            out[key] = int(value)
    art = media(systeme.findall("medias/media"), SYSTEM_ART, ART_REGIONS)
    if art:
        out["art"] = art
    return out
