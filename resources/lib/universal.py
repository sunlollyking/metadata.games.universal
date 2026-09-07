"""Orchestrates the providers: ordered lookup, namespaced candidate ids and field merging.

Candidate ids are ``<provider>:<local id>``. A hash or serial match from any
provider beats a name match from an earlier one, so find asks every
available provider before settling for name matches. Details come from the
candidate's own provider; the others may fill fields it left empty and add
art types it lacks, never replacing what is already there.
"""
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .budget import Budget
from . import namer
from .providers import Log, OnlineProvider, Provider, Request

IDENTITY_MATCHES = ("hash", "serial")
#: What a second provider may fill in where the first said nothing. Art and
#: unique ids are merged separately, type by type.
DETAIL_FIELDS = ("overview", "developers", "publishers", "genres", "collections",
                 "players", "ratings", "ageratings", "releasedate", "year",
                 "achievements", "manual", "trailer", "originaltitle", "edition", "tags")
PLATFORM_FIELDS = ("name", "manufacturer", "released", "discontinued", "overview")


def split_id(candidate_id: str) -> Tuple[str, str]:
    provider, sep, local = candidate_id.partition(":")
    return (provider, local) if sep else ("", candidate_id)


def join_id(provider_name: str, local_id: str) -> str:
    return "{}:{}".format(provider_name, local_id)


def is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def merge(base: Dict[str, Any], extra: Dict[str, Any], fields: Sequence[str]) -> None:
    """Copy into base the listed fields it lacks, new uniqueids keys and missing art types."""
    for field in fields:
        if is_empty(base.get(field)) and not is_empty(extra.get(field)):
            base[field] = extra[field]
    for source, uid in (extra.get("uniqueids") or {}).items():
        if uid and not (base.get("uniqueids") or {}).get(source):
            base.setdefault("uniqueids", {})[source] = uid
    # Pictures add up rather than replace: a game keeps the box the first
    # source gave and the screenshots the second one has as well
    for art_type, entries in (extra.get("art") or {}).items():
        if not entries:
            continue
        held = base.setdefault("art", {}).setdefault(art_type, [])
        seen = {e.get("url") for e in held if isinstance(e, dict)}
        for entry in entries:
            url = entry.get("url") if isinstance(entry, dict) else None
            if url and url not in seen:
                held.append(entry)
                seen.add(url)


def is_just_the_title(overview: Any, title: str) -> bool:
    """Whether an overview says nothing the title has not already said.

    Arcade and some cartridge catalogues put the game's own name in their
    description field -- "Panzer Dragoon (USA) (5S)". Kodi refuses those, but
    by then it is too late: an overview that is really a name still counts as
    one while sources are merged, so it keeps out the source that has real
    prose and the game ends up with no description at all.
    """
    text = str(overview or "").strip()
    if not text or not title:
        return False
    bare = namer.parse(text, strip_extension=False).get("title") or text
    return namer.normalise(bare) == namer.normalise(title)


def provider_order(settings: Dict[str, Any]) -> List[str]:
    raw = settings.get("provider_order") or ""
    return [name.strip().lower() for name in str(raw).split(",") if name.strip()]


class Universal:
    """The scraper behind the entry point, built once per process from a provider list."""

    def __init__(self, providers: Sequence[Provider], log: Log, cache_dir: str = ""):
        self.providers: Dict[str, Provider] = {p.name: p for p in providers}
        self.log = log
        self.cache_dir = cache_dir
        self._budgets: Dict[str, Budget] = {}
        #: Sources that answered "no allowance left" during this run
        self._exhausted: set = set()
        self._unusable: set = set()
        #: Set when a batch has spent its time; what is left is read offline
        self._offline = False

    def ordered(self, settings: Dict[str, Any], bulk: bool = False) -> List[Provider]:
        """Available providers in the configured order; a provider left out of the order is not used.

        While a folder is being scanned, a provider that asks not to be
        scraped in bulk, or whose allowance is measured in hundreds a month,
        is left out. It is still used when one game is looked up.
        """
        out = []
        for name in provider_order(settings):
            provider = self.providers.get(name)
            if provider is None:
                self.log("provider_order names unknown provider {!r}".format(name), False)
            elif self._offline and isinstance(provider, OnlineProvider):
                continue
            elif provider.name in self._exhausted or getattr(provider, "exhausted", False):
                continue
            elif bulk and not provider.bulk_safe and not self._has_budget(provider, settings):
                self.log("{} has spent its share for this month; it is asked about single "
                         "games only".format(name), False)
            elif provider not in out and provider.available(settings):
                out.append(provider)
            elif not provider.available(settings):
                self._say_once(provider, settings)
        return out

    def _say_once(self, provider: Provider, settings: Dict[str, Any]) -> None:
        """Name a provider that is configured but cannot be used, once per run.

        A provider whose credentials are missing is simply skipped, which looks
        from the outside exactly like a provider that answered nothing: a whole
        library can be scanned against one catalogue without a word about the
        other five.
        """
        if provider.name in self._unusable:
            return
        self._unusable.add(provider.name)
        missing = [key for key in provider.required_settings if not settings.get(key)]
        if missing:
            # Said loudly rather than at debug: a provider that cannot be used is
            # indistinguishable from one that found nothing, and a whole library
            # can be scanned against a fraction of the catalogues without a word
            self.log("{} is in the provider order but {} {} not set, so it is not "
                     "being asked".format(provider.name, ", ".join(missing),
                                          "is" if len(missing) == 1 else "are"), True)

    def begin_batch(self) -> None:
        """Start this batch willing to go online again.

        The engine outlives any one batch, so without this a single slow batch
        would leave every later one reading the catalogue alone for the rest of
        the process.
        """
        self._offline = False

    def stay_offline(self) -> None:
        """Answer the rest of this run from the offline catalogue alone.

        A scan must finish. If the web sources are slow or unwell, waiting on
        them is worse than a library built from what is already on the disk,
        which a refresh can fill in later.
        """
        self._offline = True

    def prefetch(self, requests: Sequence[Request]) -> None:
        """Let every provider that can answer a whole batch at once do so."""
        if not requests:
            return
        settings = requests[0].settings
        for provider in self.ordered(settings, requests[0].bulk):
            try:
                provider.prefetch(requests)
            except Exception as err:  # a warm-up is optional; a failure is not fatal
                self.log("{} could not prepare for the batch: {}".format(provider.name, err), True)

    def find(self, request: Request) -> List[dict]:
        named: List[dict] = []
        available = self.ordered(request.settings, request.bulk)
        # With one provider there is nothing to merge, so a provider whose
        # details are free can answer both questions in this one call
        alone = len(available) == 1
        for provider in available:
            if request.bulk and not provider.bulk_safe:
                self._spend(provider, request.settings)
            candidates = self._ask(provider, "find", request) or []
            identity = [c for c in candidates if c.get("matchedby") in IDENTITY_MATCHES]
            if identity:
                return [self._namespaced(provider, c, alone, request) for c in identity]
            if candidates and not named:
                named = [self._namespaced(provider, c, alone, request) for c in candidates]
        return named

    def details(self, candidate_id: str, request: Request) -> Optional[Dict[str, Any]]:
        name, local_id = split_id(candidate_id)
        primary = self.providers.get(name)
        if primary is None:
            self.log("candidate {!r} names no known provider".format(candidate_id), True)
            return None
        details = primary.details(local_id, request)
        if details is None:
            return None
        if is_just_the_title(details.get("overview"), str(details.get("title") or request.title())):
            details.pop("overview", None)
        # The others are asked about the game the first one identified, not
        # about the file name. A scene-named dump reads "Crazy Taxi v1.004
        # (1999)(Sega)(US)[!][10S]"; once the disc's serial has named it "Crazy
        # Taxi", that is what the rest can find.
        refined = self._refine(request, details)
        for provider in self.ordered(request.settings, request.bulk):
            if provider is not primary:
                extra = self._lookup(provider, refined, details)
                if extra:
                    merge(details, extra, DETAIL_FIELDS)
        return details

    @staticmethod
    def _refine(request: Request, details: Dict[str, Any]) -> Request:
        """The same request, asking about the title the first provider settled on."""
        title = (details.get("title") or "").strip()
        if not title or title == request.get("title"):
            return request
        query = dict(request.query)
        query["title"] = title
        refined = Request(query, request.settings, request.bulk)
        return refined

    def platform(self, request: Request) -> Optional[Dict[str, Any]]:
        info: Optional[Dict[str, Any]] = None
        for provider in self.ordered(request.settings):
            extra = self._ask(provider, "platform", request)
            if extra is None:
                continue
            if info is None:
                info = extra
            else:
                merge(info, extra, PLATFORM_FIELDS)
        return info

    def progress(self, request: Request) -> Dict[str, Dict[str, int]]:
        """How far the signed-in person has got, from whichever source keeps it.

        Only RetroAchievements does today, so the first answer stands rather
        than being merged with anything.
        """
        for provider in self.ordered(request.settings):
            if not hasattr(provider, "progress"):
                continue
            answer = self._ask(provider, "progress", request)
            if answer:
                return answer
        return {}

    def _has_budget(self, provider: Provider, settings: Dict[str, Any]) -> bool:
        limit = provider.budget_limit(settings)
        if limit <= 0:
            return False
        return self._budget(provider, limit).left() > 0

    def _budget(self, provider: Provider, limit: int) -> Budget:
        key = provider.name
        if key not in self._budgets:
            self._budgets[key] = Budget(self.cache_dir, key, limit)
        return self._budgets[key]

    def _spend(self, provider: Provider, settings: Dict[str, Any]) -> None:
        limit = provider.budget_limit(settings)
        if limit > 0:
            self._budget(provider, limit).spend()

    def _lookup(self, provider: Provider,
                request: Request,
                known: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Details from a provider that was not asked by candidate id.

        A hash or a serial settles it. Failing that the title has already
        matched, so several candidates are re-releases of one game rather than
        different games: the one whose year agrees with what is already known
        is taken, and the best-placed one where nothing is known.
        """
        if request.bulk and not provider.bulk_safe:
            self._spend(provider, request.settings)

        candidates = self._ask(provider, "find", request) or []
        if not candidates:
            return None

        identity = [c for c in candidates if c.get("matchedby") in IDENTITY_MATCHES]
        if identity:
            chosen = identity[0]
        else:
            year = (known or {}).get("year")
            same_year = [c for c in candidates if year and c.get("year") == year]
            chosen = same_year[0] if same_year else candidates[0]

        return self._ask(provider, "details", chosen["id"], request)

    def _ask(self, provider: Provider, method: str, *args: Any) -> Any:
        """One provider call; a provider that raises answers nothing rather than sinking the others' answers."""
        if provider.name in self._exhausted:
            return None
        try:
            answer = getattr(provider, method)(*args)
            # A source that has just said it is turning requests away is not
            # asked again, in this run or the next one this period
            if getattr(provider, "exhausted", False) and provider.name not in self._exhausted:
                self._exhausted.add(provider.name)
                settings = args[-1].settings if args and isinstance(args[-1], Request) else {}
                limit = provider.budget_limit(settings)
                if limit > 0:
                    self._budget(provider, limit).spend(limit)
            return answer
        except Exception as err:
            # Being told to stop is not a failure to retry around. A source
            # whose allowance is gone is left alone for the rest of the run,
            # and its share is marked spent so the next run knows too.
            if getattr(err, "status", None) == 429:
                self._exhausted.add(provider.name)
                self.log("{} has no allowance left; leaving it alone".format(provider.name), True)
                limit = provider.budget_limit(args[-1].settings) if args and isinstance(
                    args[-1], Request) else provider.monthly_budget
                if limit > 0:
                    self._budget(provider, limit).spend(limit)
            else:
                self.log("{} {} failed: {!r}".format(provider.name, method, err), True)
            return None

    @staticmethod
    def _namespaced(provider: Provider,
                    candidate: dict,
                    with_details: bool = False,
                    request: Optional[Request] = None) -> dict:
        out = dict(candidate)
        local_id = str(candidate["id"])
        out["id"] = join_id(provider.name, local_id)
        out.setdefault("provider", provider.name)
        if with_details and provider.details_are_free and request is not None:
            details = provider.details(local_id, request)
            if details:
                out["details"] = details
        return out
