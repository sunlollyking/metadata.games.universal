"""Whether a game is a spin-off of its series reaches Kodi."""
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


KART = {"id": 7, "name": "Mario Kart 64", "collections": [{"name": "Mario Kart"}]}


class SpinoffTest(unittest.TestCase):
    def test_a_spin_off_says_so(self):
        provider = Scripted({"games": [KART], "collection_memberships": [
            {"game": 7, "collection": {"name": "Mario Kart"}, "type": {"name": "Spin-off"}}]})
        self.assertTrue(provider.details("7", request("Mario Kart 64"))["spinoff"])

    def test_a_main_entry_says_so(self):
        provider = Scripted({"games": [KART], "collection_memberships": [
            {"game": 7, "collection": {"name": "Mario Kart"}, "type": {"name": "Main game"}}]})
        self.assertFalse(provider.details("7", request("Mario Kart 64"))["spinoff"])

    def test_only_the_series_counts(self):
        provider = Scripted({"games": [KART], "collection_memberships": [
            {"game": 7, "collection": {"name": "Mario"}, "type": {"name": "Spin-off"}}]})
        self.assertNotIn("spinoff", provider.details("7", request("Mario Kart 64")))

    def test_a_game_in_no_series_is_not_asked_about(self):
        provider = Scripted({"games": [{"id": 8, "name": "Alone"}]})
        self.assertNotIn("spinoff", provider.details("8", request("Alone")))
        self.assertFalse([e for e, _ in provider.asked if e == "collection_memberships"])


if __name__ == "__main__":
    unittest.main()
