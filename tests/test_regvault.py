"""REG-Vault: free, hash-keyed, and deliberately kept out of scans."""
import json
import os
import sys
import unittest
from unittest import mock

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, ADDON_DIR)

from resources.lib.providers import Request, regvault  # noqa: E402


def no_log(message, error=False):
    pass


ENTRY = {
    "title_en": "Super Mario Bros.",
    "description_en": "Jump on turtle soldiers.",
    "year": 1985,
    "developer": "Nintendo",
    "publisher": "Nintendo",
    "genre": ["Platform"],
    "has_manual": True,
    "assets": {"box_front": "/assets/smb-box.png", "fanart": "/assets/smb-fan.jpg"},
}


def request(**query):
    base = {"platform": "nes", "platformids": json.dumps({"regvault": "nes"}),
            "md5": "aabbccdd", "title": "Super Mario Bros."}
    base.update(query)
    return Request(base, {})


class Answer:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class RegVaultTest(unittest.TestCase):
    def setUp(self):
        self.provider = regvault.RegVaultProvider(no_log)
        self.provider._last_request = 0.0
        # The pacing is real; the tests do not need to wait it out
        self.provider._wait_turn = lambda: None

    def test_it_needs_no_credentials(self):
        self.assertTrue(self.provider.available({}))

    def test_it_stays_out_of_a_scan(self):
        self.assertFalse(self.provider.bulk_safe)

    def test_a_known_hash_is_an_identity_match(self):
        with mock.patch("urllib.request.urlopen", return_value=Answer(ENTRY)):
            found = self.provider.find(request())
        self.assertEqual([(c["title"], c["matchedby"]) for c in found],
                         [("Super Mario Bros.", "hash")])

    def test_without_a_hash_nothing_is_asked(self):
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("asked anyway")):
            self.assertEqual(self.provider.find(request(md5="")), [])

    def test_details_carry_the_description_the_art_and_the_manual(self):
        with mock.patch("urllib.request.urlopen", return_value=Answer(ENTRY)):
            details = self.provider.details("nes/aabbccdd", request())
        self.assertEqual(details["title"], "Super Mario Bros.")
        self.assertEqual(details["year"], 1985)
        self.assertEqual(details["genres"], ["Platform"])
        self.assertEqual(details["developers"], ["Nintendo"])
        self.assertEqual(details["art"]["boxfront"][0]["url"],
                         "https://api.regvault.org/assets/smb-box.png")
        self.assertTrue(details["manual"].endswith("/nes/aabbccdd/manual"))

    def test_a_year_the_machine_could_not_have_carried_is_dropped(self):
        entry = dict(ENTRY, year=2013)
        with mock.patch("urllib.request.urlopen", return_value=Answer(entry)):
            details = self.provider.details("nes/aabbccdd", request())
        self.assertNotIn("year", details)

    def test_a_genre_written_as_one_string_is_split(self):
        entry = dict(ENTRY, genre="Action,Platformer")
        with mock.patch("urllib.request.urlopen", return_value=Answer(entry)):
            details = self.provider.details("nes/aabbccdd", request())
        self.assertEqual(details["genres"], ["Action", "Platformer"])

    def test_a_game_it_does_not_know_finds_nothing(self):
        import urllib.error
        error = urllib.error.HTTPError("u", 404, "not found", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=error):
            self.assertEqual(self.provider.find(request()), [])


if __name__ == "__main__":
    unittest.main()
