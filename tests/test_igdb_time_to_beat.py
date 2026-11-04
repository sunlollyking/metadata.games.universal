"""IGDB's players' times to beat a game reach Kodi under Kodi's names."""
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
    """IGDB with its queries answered from a script rather than the network."""

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


GAME = {"id": 1068, "name": "Super Mario Bros. 3"}
TIMES = {"game_id": 1068, "hastily": 18000, "normally": 25200, "completely": 39600}


class TimeToBeatTest(unittest.TestCase):
    def test_the_three_times_take_kodis_names(self):
        self.assertEqual(igdb.time_to_beat(TIMES),
                         {"main": 18000, "extras": 25200, "complete": 39600})

    def test_a_time_igdb_does_not_have_is_left_out(self):
        self.assertEqual(igdb.time_to_beat({"game_id": 1, "hastily": 3600, "completely": None}),
                         {"main": 3600})
        self.assertEqual(igdb.time_to_beat({"game_id": 1, "normally": 0, "completely": True}), {})

    def test_details_carry_the_times(self):
        provider = Scripted({"games": [GAME], "game_time_to_beats": [TIMES]})
        details = provider.details("1068", request("Super Mario Bros. 3"))
        self.assertEqual(details["timetobeat"], {"main": 18000, "extras": 25200, "complete": 39600})

    def test_a_game_with_no_times_carries_none(self):
        provider = Scripted({"games": [GAME]})
        self.assertNotIn("timetobeat", provider.details("1068", request("Super Mario Bros. 3")))

    def test_a_batch_asks_for_every_game_s_times_at_once(self):
        provider = Scripted({"games": [GAME, {"id": 1074, "name": "Super Mario Bros. 2"}],
                             "game_time_to_beats": [TIMES]})
        provider.prefetch([request("Super Mario Bros. 3"), request("Super Mario Bros. 2")])
        asked = [body for endpoint, body in provider.asked if endpoint == "game_time_to_beats"]
        self.assertEqual(asked, ["where game_id = (1068,1074); limit 500;"])

        provider.details("1068", request("Super Mario Bros. 3"))
        provider.details("1074", request("Super Mario Bros. 2"))
        asked = [body for endpoint, body in provider.asked if endpoint == "game_time_to_beats"]
        self.assertEqual(len(asked), 1)


if __name__ == "__main__":
    unittest.main()
