"""The characters in a game reach Kodi with their pictures."""
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


if __name__ == "__main__":
    unittest.main()
