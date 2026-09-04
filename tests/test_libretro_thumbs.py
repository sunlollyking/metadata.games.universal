"""What the thumbnail repository holds decides which pictures are offered."""
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, ADDON_DIR)

from resources.lib.providers import libretro  # noqa: E402


def no_log(message, error=False):
    pass


class ArtUrlTest(unittest.TestCase):
    def test_every_kind_is_offered_when_the_repository_is_unknown(self):
        art = libretro.art_urls("Sega - Mega Drive - Genesis", "Sonic (World)", "World", None)
        self.assertEqual(sorted(art), ["boxfront", "screenshot", "titlescreen"])

    def test_only_the_pictures_the_repository_holds_are_offered(self):
        held = {"Named_Boxarts": {"Sonic (World)"}, "Named_Snaps": set(), "Named_Titles": set()}
        art = libretro.art_urls("Sega - Mega Drive - Genesis", "Sonic (World)", "World", held)
        self.assertEqual(sorted(art), ["boxfront"])
        self.assertIn("Named_Boxarts", art["boxfront"][0]["url"])

    def test_a_game_the_repository_does_not_hold_is_offered_nothing(self):
        held = {"Named_Boxarts": {"Something Else"}, "Named_Snaps": set(), "Named_Titles": set()}
        self.assertEqual(libretro.art_urls("Sega - Mega Drive - Genesis", "Sonic (World)", None, held), {})


class ThumbnailIndexTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.store = libretro.Store(self.dir, True, 30, no_log)

    def answer(self, payload):
        response = mock.MagicMock()
        response.read.return_value = json.dumps(payload).encode("utf-8")
        response.__enter__.return_value = response
        return response

    def test_the_listing_is_read_and_cached(self):
        payload = {"tree": [{"path": "Named_Boxarts/Sonic (World).png"},
                            {"path": "Named_Snaps/Sonic (World).png"},
                            {"path": "README.md"}]}
        with mock.patch("urllib.request.urlopen", return_value=self.answer(payload)) as opened:
            held = self.store.thumbnails("Sega - Mega Drive - Genesis")
        self.assertEqual(held["Named_Boxarts"], {"Sonic (World)"})
        self.assertEqual(held["Named_Snaps"], {"Sonic (World)"})
        self.assertEqual(held["Named_Titles"], set())
        self.assertEqual(opened.call_count, 1)

        # A second store reads the file rather than asking again
        again = libretro.Store(self.dir, True, 30, no_log)
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("asked twice")):
            self.assertEqual(again.thumbnails("Sega - Mega Drive - Genesis")["Named_Boxarts"],
                             {"Sonic (World)"})

    def test_a_truncated_listing_is_not_used(self):
        payload = {"truncated": True, "tree": [{"path": "Named_Boxarts/Sonic (World).png"}]}
        with mock.patch("urllib.request.urlopen", return_value=self.answer(payload)):
            self.assertIsNone(self.store.thumbnails("Sega - Mega Drive - Genesis"))

    def test_a_failed_request_leaves_the_question_unanswered(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("no network")):
            self.assertIsNone(self.store.thumbnails("Sega - Mega Drive - Genesis"))


if __name__ == "__main__":
    unittest.main()
