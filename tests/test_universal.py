"""Orchestration tests with scripted providers: order, precedence, merging and availability."""
import os
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, ADDON_DIR)
import kodistubs  # noqa: E402

kodistubs.install()

from resources.lib import universal  # noqa: E402
from resources.lib.providers import OnlineProvider, Provider, Request  # noqa: E402
from resources.lib.providers import igdb, retroachievements, screenscraper, thegamesdb  # noqa: E402

ALL = "a,b,c"


def no_log(msg, error=False):
    pass


def cand(local_id, matchedby, title="Game"):
    return {"id": local_id, "title": title, "score": 1.0 if matchedby != "name" else 0.9, "matchedby": matchedby}


class Scripted(Provider):
    def __init__(self, name, candidates=(), details=None, platform=None, keys=()):
        super().__init__(no_log)
        self.name = name
        self.required_settings = tuple(keys)
        self.candidates = list(candidates)
        self.detail_records = dict(details or {})
        self.platform_record = platform
        self.calls = []

    def find(self, request):
        self.calls.append("find")
        return [dict(c) for c in self.candidates]

    def details(self, candidate_id, request):
        self.calls.append("details:" + candidate_id)
        record = self.detail_records.get(candidate_id)
        return dict(record) if record else None

    def platform(self, request):
        self.calls.append("platform")
        return dict(self.platform_record) if self.platform_record else None


def request(order=ALL, **settings):
    conf = {"provider_order": order}
    conf.update(settings)
    return Request({"title": "Game", "crc32": "deadbeef"}, conf)


class FindTest(unittest.TestCase):
    def test_provider_order_honoured(self):
        a = Scripted("a", [cand("1", "hash")])
        b = Scripted("b", [cand("2", "hash")])
        scraper = universal.Universal([a, b], no_log)
        self.assertEqual([c["id"] for c in scraper.find(request("a,b"))], ["a:1"])
        self.assertEqual([c["id"] for c in scraper.find(request("b,a"))], ["b:2"])
        self.assertEqual([c["id"] for c in scraper.find(request("b"))], ["b:2"])

    def test_first_hash_match_stops_the_search(self):
        a = Scripted("a", [cand("1", "hash")])
        b = Scripted("b", [cand("2", "hash")])
        universal.Universal([a, b], no_log).find(request("a,b"))
        self.assertEqual(b.calls, [])

    def test_name_match_does_not_override_later_hash_match(self):
        a = Scripted("a", [cand("n1", "name"), cand("n2", "name")])
        b = Scripted("b", [cand("h", "serial")])
        found = universal.Universal([a, b], no_log).find(request("a,b"))
        self.assertEqual([c["id"] for c in found], ["b:h"])
        self.assertEqual(found[0]["matchedby"], "serial")

    def test_name_matches_come_from_the_first_provider_that_has_any(self):
        a = Scripted("a", [])
        b = Scripted("b", [cand("n1", "name"), cand("n2", "name")])
        c = Scripted("c", [cand("n3", "name")])
        found = universal.Universal([a, b, c], no_log).find(request())
        self.assertEqual([x["id"] for x in found], ["b:n1", "b:n2"])

    def test_only_identity_matches_are_returned_from_a_hash_hit(self):
        a = Scripted("a", [cand("h", "hash"), cand("n", "name")])
        found = universal.Universal([a], no_log).find(request())
        self.assertEqual([x["id"] for x in found], ["a:h"])

    def test_candidate_payload_keeps_the_provider_fields(self):
        a = Scripted("a", [{"id": 5, "title": "T", "year": 1999, "score": 1.0, "matchedby": "hash"}])
        found = universal.Universal([a], no_log).find(request())
        self.assertEqual(found, [{"id": "a:5", "title": "T", "year": 1999, "score": 1.0,
                                  "matchedby": "hash", "provider": "a"}])
        self.assertEqual(a.candidates[0]["id"], 5)

    def test_a_lone_free_provider_answers_find_with_the_details_attached(self):
        a = Scripted("a", [cand("1", "hash")], details={"1": {"title": "T"}})
        a.details_are_free = True
        found = universal.Universal([a], no_log).find(request())
        self.assertEqual(found[0]["details"], {"title": "T"})

    def test_details_are_not_attached_when_another_provider_could_add_to_them(self):
        a = Scripted("a", [cand("1", "hash")], details={"1": {"title": "T"}})
        a.details_are_free = True
        b = Scripted("b", [])
        found = universal.Universal([a, b], no_log).find(request(order="a,b"))
        self.assertNotIn("details", found[0])

    def test_unavailable_and_unlisted_providers_are_not_asked(self):
        a = Scripted("a", [cand("1", "hash")], keys=("a_key",))
        b = Scripted("b", [cand("2", "hash")])
        c = Scripted("c", [cand("3", "hash")])
        scraper = universal.Universal([a, b, c], no_log)
        self.assertEqual([x["id"] for x in scraper.find(request("a,b"))], ["b:2"])
        self.assertEqual(a.calls, [])
        self.assertEqual(c.calls, [])
        self.assertEqual([x["id"] for x in scraper.find(request("a,b", a_key="k"))], ["a:1"])

    def test_nothing_matches(self):
        self.assertEqual(universal.Universal([Scripted("a"), Scripted("b")], no_log).find(request()), [])


class DetailsTest(unittest.TestCase):
    def setUp(self):
        self.primary = {"version": 1, "title": "Game", "overview": "", "developers": [], "genres": ["Action"],
                        "players": {"min": 1, "max": 1}, "uniqueids": {"a": "1"},
                        "art": {"boxfront": [{"url": "a-box"}], "screenshot": []}}
        self.extra = {"version": 1, "title": "Other Title", "overview": "From b", "developers": ["Dev B"],
                      "genres": ["Platform"], "players": {"min": 1, "max": 4}, "releasedate": "1999-01-01",
                      "ratings": {"b": {"rating": 7.0, "max": 10, "votes": 3}}, "uniqueids": {"a": "9", "b": "2"},
                      "art": {"boxfront": [{"url": "b-box"}], "screenshot": [{"url": "b-shot"}],
                              "fanart": [{"url": "b-fanart"}]}}

    def test_merge_fills_only_empty_fields(self):
        a = Scripted("a", [cand("1", "hash")], {"1": self.primary})
        b = Scripted("b", [cand("2", "hash")], {"2": self.extra})
        details = universal.Universal([a, b], no_log).details("a:1", request("a,b"))
        self.assertEqual(details["title"], "Game")
        self.assertEqual(details["overview"], "From b")
        self.assertEqual(details["developers"], ["Dev B"])
        self.assertEqual(details["genres"], ["Action"])
        self.assertEqual(details["players"], {"min": 1, "max": 1})
        self.assertEqual(details["releasedate"], "1999-01-01")
        self.assertEqual(details["ratings"], {"b": {"rating": 7.0, "max": 10, "votes": 3}})
        self.assertEqual(details["uniqueids"], {"a": "1", "b": "2"})
        # Pictures add up: the second source's box joins the first one's
        self.assertEqual(details["art"], {"boxfront": [{"url": "a-box"}, {"url": "b-box"}],
                                          "screenshot": [{"url": "b-shot"}],
                                          "fanart": [{"url": "b-fanart"}]})
        self.assertEqual(b.calls, ["find", "details:2"])

    def test_primary_is_the_candidate_provider_regardless_of_order(self):
        a = Scripted("a", [cand("1", "hash")], {"1": self.primary})
        b = Scripted("b", [cand("2", "hash")], {"2": self.extra})
        details = universal.Universal([a, b], no_log).details("a:1", request("b,a"))
        self.assertEqual(details["title"], "Game")
        self.assertEqual(details["overview"], "From b")

    def test_several_of_one_title_still_supplement(self):
        # The title has already matched, so these are re-releases of one game
        # rather than different games; the best-placed one is taken
        a = Scripted("a", [cand("1", "hash")], {"1": dict(self.primary)})
        b = Scripted("b", [cand("2", "name"), cand("3", "name")], {"2": self.extra, "3": self.extra})
        details = universal.Universal([a, b], no_log).details("a:1", request("a,b"))
        self.assertEqual(details["overview"], "From b")
        self.assertEqual(b.calls, ["find", "details:2"])

    def test_the_one_whose_year_agrees_is_preferred(self):
        primary = dict(self.primary)
        primary["year"] = 1994
        wanted = dict(self.extra)
        wanted["overview"] = "The 1994 one"
        a = Scripted("a", [cand("1", "hash")], {"1": primary})
        b = Scripted("b",
                     [dict(cand("2", "name"), year=1999), dict(cand("3", "name"), year=1994)],
                     {"2": self.extra, "3": wanted})
        details = universal.Universal([a, b], no_log).details("a:1", request("a,b"))
        self.assertEqual(details["overview"], "The 1994 one")
        self.assertEqual(b.calls, ["find", "details:3"])

    def test_single_name_match_supplements(self):
        a = Scripted("a", [cand("1", "hash")], {"1": dict(self.primary)})
        b = Scripted("b", [cand("2", "name")], {"2": self.extra})
        details = universal.Universal([a, b], no_log).details("a:1", request("a,b"))
        self.assertEqual(details["overview"], "From b")

    def test_unknown_provider_or_record_gives_none(self):
        a = Scripted("a", [cand("1", "hash")], {"1": self.primary})
        scraper = universal.Universal([a], no_log)
        self.assertIsNone(scraper.details("z:1", request()))
        self.assertIsNone(scraper.details("1", request()))
        self.assertIsNone(scraper.details("a:missing", request()))

    def test_local_id_may_contain_colons(self):
        a = Scripted("a", [], {"x:y": self.primary})
        self.assertEqual(universal.split_id("a:x:y"), ("a", "x:y"))
        self.assertIsNotNone(universal.Universal([a], no_log).details("a:x:y", request()))


class PlatformTest(unittest.TestCase):
    def test_platform_merges_in_order(self):
        a = Scripted("a", platform={"version": 1, "name": "Mega Drive", "manufacturer": "Sega",
                                    "art": {"clearlogo": [{"url": "a-logo"}]}})
        b = Scripted("b", platform={"version": 1, "name": "Genesis", "manufacturer": "SEGA", "released": 1988,
                                    "overview": "16-bit", "art": {"clearlogo": [{"url": "b-logo"}],
                                                                  "fanart": [{"url": "b-fanart"}]}})
        info = universal.Universal([a, b], no_log).platform(request("a,b"))
        self.assertEqual(info, {"version": 1, "name": "Mega Drive", "manufacturer": "Sega", "released": 1988,
                                "overview": "16-bit",
                                "art": {"clearlogo": [{"url": "a-logo"}, {"url": "b-logo"}],
                                        "fanart": [{"url": "b-fanart"}]}})
        self.assertEqual(universal.Universal([a, b], no_log).platform(request("b,a"))["name"], "Genesis")

    def test_platform_unknown_everywhere(self):
        self.assertIsNone(universal.Universal([Scripted("a"), Scripted("b")], no_log).platform(request()))


class StubProviderTest(unittest.TestCase):
    STUBS = (
        (retroachievements.RetroAchievementsProvider, "retroachievements", {"ra_username": "u", "ra_api_key": "k"}),
        (screenscraper.ScreenScraperProvider, "screenscraper",
         {"ss_devid": "d", "ss_devpassword": "p", "ss_user": "u", "ss_password": "p"}),
        (igdb.IgdbProvider, "igdb", {"igdb_client_id": "c", "igdb_client_secret": "s"}),
        (thegamesdb.TheGamesDbProvider, "thegamesdb", {"tgdb_api_key": "k"}),
    )

    def test_unavailable_without_keys(self):
        for cls, name, keys in self.STUBS:
            provider = cls(no_log)
            self.assertEqual(provider.name, name)
            self.assertFalse(provider.available({}))
            self.assertFalse(provider.available({k: "" for k in keys}))
            for missing in keys:
                partial = {k: v for k, v in keys.items() if k != missing}
                self.assertFalse(provider.available(partial), "{} without {}".format(name, missing))

    def test_available_with_keys_but_silent(self):
        for cls, name, keys in self.STUBS:
            provider = cls(no_log)
            self.assertTrue(provider.available(keys))
            self.assertEqual(provider.credentials(keys), keys)
            req = Request({"title": "Game", "crc32": "deadbeef", "platformids": '{"%s": "1"}' % name}, keys)
            self.assertEqual(provider.find(req), [])
            self.assertIsNone(provider.details("1", req))
            self.assertIsNone(provider.platform(req))

    def test_provider_order_default_covers_every_stub(self):
        import scraper
        names = universal.provider_order({"provider_order": scraper.DEFAULTS["provider_order"]})
        self.assertEqual(names, ["libretro", "retroachievements", "wikidata", "igdb", "screenscraper",
                                 "thegamesdb", "regvault"])
        for cls, _, _ in self.STUBS:
            self.assertIn(cls(no_log).name, names)


class RequestTest(unittest.TestCase):
    def test_platform_ids(self):
        req = Request({"platformids": '{"libretro": " Sega - Mega Drive - Genesis ", "screenscraper": 1}'}, {})
        self.assertEqual(req.platform_id("libretro"), "Sega - Mega Drive - Genesis")
        self.assertEqual(req.platform_id("screenscraper"), "")
        self.assertEqual(req.platform_id("igdb"), "")
        self.assertEqual(Request({"platformids": "{broken"}, {}).platformids, {})
        self.assertEqual(Request({"platformids": "[1]"}, {}).platformids, {})
        self.assertEqual(Request({}, {}).get("title", "x"), "x")


class ScriptedOnline(OnlineProvider):
    """A web-backed provider, which is what the offline fallback leaves out."""

    def __init__(self, name, candidates=()):
        super().__init__(no_log)
        self.name = name
        self.candidates = list(candidates)

    def find(self, request):
        return [dict(c) for c in self.candidates]


class OfflineFallbackTest(unittest.TestCase):
    def test_staying_offline_lasts_one_batch(self):
        online = ScriptedOnline("a", [cand("1", "hash")])
        engine = universal.Universal([online], no_log)
        self.assertEqual([c["id"] for c in engine.find(request("a"))], ["a:1"])

        engine.stay_offline()
        self.assertEqual(engine.find(request("a")), [])

        # The engine outlives the batch, so the next one has to go online again
        engine.begin_batch()
        self.assertEqual([c["id"] for c in engine.find(request("a"))], ["a:1"])


if __name__ == "__main__":
    unittest.main()


class NameOnlyOverviewTest(unittest.TestCase):
    def test_an_overview_that_is_the_file_name_counts_as_nothing(self):
        self.assertTrue(universal.is_just_the_title("Panzer Dragoon (USA) (5S)", "Panzer Dragoon"))
        self.assertTrue(universal.is_just_the_title(
            "Time Gal & Ninja Hayate (Japan) (En,Ja) (Disc 2)", "Time Gal & Ninja Hayate"))

    def test_real_prose_is_kept(self):
        self.assertFalse(universal.is_just_the_title(
            "A vertically scrolling shooter set in the Pacific.", "1942"))

    def test_an_empty_one_is_not_a_title(self):
        self.assertFalse(universal.is_just_the_title("", "1942"))
        self.assertFalse(universal.is_just_the_title(None, "1942"))

    def test_the_junk_gives_way_to_a_source_with_prose(self):
        first = Scripted("a", [cand("1", "hash")],
                         {"1": {"title": "Panzer Dragoon", "overview": "Panzer Dragoon (USA) (5S)"}})
        second = Scripted("b", [cand("2", "name")],
                          {"2": {"title": "Panzer Dragoon", "overview": "A rail shooter on the back of a dragon."}})
        engine = universal.Universal([first, second], no_log)
        details = engine.details("a:1", request("a,b"))
        self.assertEqual(details["overview"], "A rail shooter on the back of a dragon.")
