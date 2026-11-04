"""The characters in a game reach Kodi with their pictures."""
import json
import os
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, ADDON_DIR)
import kodistubs  # noqa: E402

kodistubs.install()

from resources.lib.providers import Request  # noqa: E402
from resources.lib.providers import igdb  # noqa: E402
from resources.lib.providers import wikidata  # noqa: E402


def no_log(message, error=False):
    pass


class Scripted(igdb.IgdbProvider):
    def __init__(self, answers, wikidata_names=None, wikidata_fails=False):
        super().__init__(no_log)
        self.answers = answers
        self.asked = []
        self.wikidata_names = wikidata_names or {}
        self.wikidata_fails = wikidata_fails
        self.wikidata_asked = []

    def _wikidata_characters(self, slugs, request):
        def characters_in_games(wanted, log):
            self.wikidata_asked.append(list(wanted))
            return None if self.wikidata_fails else {s: self.wikidata_names.get(s, []) for s in wanted}

        real = wikidata.characters_in_games
        wikidata.characters_in_games = characters_in_games
        try:
            return super()._wikidata_characters(slugs, request)
        finally:
            wikidata.characters_in_games = real

    def _platform_id(self, request):
        return "18"

    def _query(self, endpoint, fields, body, request):
        self.asked.append((endpoint, body))
        return self.answers.get(endpoint, [])


def request(title):
    return Request({"title": title, "platform": "nes"}, {"provider_order": "igdb"})


SMB3 = {"id": 1068, "name": "Super Mario Bros. 3"}
SMB2 = {"id": 1074, "name": "Super Mario Bros. 2"}
MARIO = {"name": "Mario", "games": [1068, 1074], "mug_shot": {"image_id": "mario"}}
BOWSER = {"name": "Bowser", "games": [1068]}


class CharacterTest(unittest.TestCase):
    def test_characters_come_with_their_pictures(self):
        provider = Scripted({"games": [SMB3], "characters": [MARIO, BOWSER]})
        details = provider.details("1068", request("Super Mario Bros. 3"))
        self.assertEqual(details["characters"], [
            {"name": "Mario", "thumb": igdb.IMAGE_URL.format("cover_big", "mario")},
            {"name": "Bowser"}])

    def test_a_batch_shares_one_request_between_its_games(self):
        provider = Scripted({"games": [SMB3, SMB2], "characters": [MARIO, BOWSER]})
        provider.prefetch([request("Super Mario Bros. 3"), request("Super Mario Bros. 2")])
        smb2 = provider.details("1074", request("Super Mario Bros. 2"))
        self.assertEqual([c["name"] for c in smb2["characters"]], ["Mario"])
        asked = [e for e, _ in provider.asked if e == "characters"]
        self.assertEqual(len(asked), 1)

    def test_a_game_with_no_characters_has_none(self):
        provider = Scripted({"games": [SMB3]})
        self.assertNotIn("characters", provider.details("1068", request("Super Mario Bros. 3")))

    def test_wikidata_names_the_characters_igdb_does_not(self):
        smb3 = dict(SMB3, slug="super-mario-bros-3")
        provider = Scripted({"games": [smb3], "characters": [MARIO]},
                            {"super-mario-bros-3": ["mario", "Luigi", "Princess Peach"]})
        details = provider.details("1068", request("Super Mario Bros. 3"))
        self.assertEqual(details["characters"], [
            {"name": "Mario", "thumb": igdb.IMAGE_URL.format("cover_big", "mario")},
            {"name": "Luigi"}, {"name": "Princess Peach"}])

    def test_a_batch_asks_wikidata_once(self):
        games = [dict(SMB3, slug="super-mario-bros-3"), dict(SMB2, slug="super-mario-bros-2")]
        provider = Scripted({"games": games, "characters": [MARIO]},
                            {"super-mario-bros-2": ["Luigi"]})
        provider.prefetch([request("Super Mario Bros. 3"), request("Super Mario Bros. 2")])
        smb2 = provider.details("1074", request("Super Mario Bros. 2"))
        self.assertEqual([c["name"] for c in smb2["characters"]], ["Mario", "Luigi"])
        self.assertEqual(provider.wikidata_asked, [["super-mario-bros-3", "super-mario-bros-2"]])

    def test_without_wikidata_igdbs_characters_stand(self):
        provider = Scripted({"games": [dict(SMB3, slug="super-mario-bros-3")], "characters": [MARIO]},
                            wikidata_fails=True)
        details = provider.details("1068", request("Super Mario Bros. 3"))
        self.assertEqual([c["name"] for c in details["characters"]], ["Mario"])
        # Not remembered as having none, so the next game asks again
        provider._wikidata_characters(["super-mario-bros-3"], request("Super Mario Bros. 3"))
        self.assertEqual(len(provider.wikidata_asked), 2)

    def test_no_more_characters_than_the_limit(self):
        names = ["Character {}".format(i) for i in range(igdb.MAX_CHARACTERS + 5)]
        self.assertEqual(len(igdb.with_names([], names)), igdb.MAX_CHARACTERS)


class WikidataAnswerTest(unittest.TestCase):
    def test_names_come_by_slug_without_unnamed_items(self):
        answer = {"results": {"bindings": [
            {"slug": {"value": "metal-gear"}, "characterLabel": {"value": "Solid Snake"}},
            {"slug": {"value": "metal-gear"}, "characterLabel": {"value": "Q1995422"}},
            {"slug": {"value": "metal-gear"}, "characterLabel": {"value": "Solid Snake"}},
            {"slug": {"value": "metal-gear"}, "characterLabel": {"value": "Big Boss"}}]}}

        class Reply:
            def __init__(self, body):
                self.body = body

            def read(self):
                return self.body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        real = wikidata.urllib.request.urlopen
        wikidata.urllib.request.urlopen = lambda req, timeout: Reply(json.dumps(answer).encode())
        try:
            names = wikidata.characters_in_games(["metal-gear", "bad slug!"], no_log)
        finally:
            wikidata.urllib.request.urlopen = real
        self.assertEqual(names, {"metal-gear": ["Solid Snake", "Big Boss"]})


if __name__ == "__main__":
    unittest.main()
