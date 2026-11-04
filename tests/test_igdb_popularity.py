"""IGDB's measures of interest in a game reach Kodi."""
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


def no_log(message, error=False):
    pass


class Scripted(igdb.IgdbProvider):
    def __init__(self, answers):
        super().__init__(no_log)
        self.answers = answers
        self.asked = []

    def _platform_id(self, request):
        return "18"

    def _query(self, endpoint, fields, body, request):
        self.asked.append((endpoint, body))
        return self.answers.get(endpoint, [])


def request(title):
    return Request({"title": title, "platform": "nes"}, {"provider_order": "igdb"})


TYPES = [{"id": 1, "name": "Visits"}, {"id": 2, "name": "Want to Play"},
         {"id": 5, "name": "24hr Peak Players"}]
GAME = {"id": 1068, "name": "Super Mario Bros. 3"}


class PopularityTest(unittest.TestCase):
    def test_visits_and_wanting_to_play_are_named(self):
        provider = Scripted({"games": [GAME], "popularity_types": TYPES, "popularity_primitives": [
            {"game_id": 1068, "popularity_type": 1, "value": 0.0042},
            {"game_id": 1068, "popularity_type": 2, "value": 0.01}]})
        details = provider.details("1068", request("Super Mario Bros. 3"))
        self.assertEqual(details["popularity"], {"visits": 0.0042, "wanttoplay": 0.01})

    def test_only_igdbs_own_measures_are_asked_for(self):
        provider = Scripted({"games": [GAME], "popularity_types": TYPES})
        provider.details("1068", request("Super Mario Bros. 3"))
        asked = [body for endpoint, body in provider.asked if endpoint == "popularity_primitives"]
        self.assertEqual(asked, ["where game_id = 1068 & popularity_type = (1,2); limit 20;"])

    def test_a_batch_asks_once_for_every_game(self):
        provider = Scripted({"games": [GAME, {"id": 1074, "name": "Super Mario Bros. 2"}],
                             "popularity_types": TYPES, "popularity_primitives": [
                                 {"game_id": 1068, "popularity_type": 1, "value": 0.5}]})
        provider.prefetch([request("Super Mario Bros. 3"), request("Super Mario Bros. 2")])
        provider.details("1068", request("Super Mario Bros. 3"))
        provider.details("1074", request("Super Mario Bros. 2"))
        asked = [body for endpoint, body in provider.asked if endpoint == "popularity_primitives"]
        self.assertEqual(len(asked), 1)
        self.assertNotIn("popularity", provider.details("1074", request("Super Mario Bros. 2")))


if __name__ == "__main__":
    unittest.main()
