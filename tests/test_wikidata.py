"""Wikidata: pictures of the machines, and nothing about games."""
import json
import os
import sys
import unittest
from unittest import mock

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, ADDON_DIR)

from resources.lib.providers import Request, wikidata  # noqa: E402


def no_log(message, error=False):
    pass


def request(platform="Sega Dreamcast", libretro="Sega - Dreamcast"):
    return Request({"platform": platform, "platformids": json.dumps({"libretro": libretro})}, {})


SEARCH = {"search": [{"id": "Q1", "description": "a fan game of the same name"},
                     {"id": "Q184198", "description": "sixth-generation home video game console"}]}
MACHINE = {"entities": {"Q184198": {"labels": {"mul": {"value": "Dreamcast"}},
                                    "claims": {
                                        "P18": [{"mainsnak": {"snaktype": "value", "datavalue": {
                                            "value": "Dreamcast Console Set.jpg"}}}],
                                        "P154": [{"mainsnak": {"snaktype": "value", "datavalue": {
                                            "value": "Dreamcast logo.svg"}}}],
                                        "P176": [{"mainsnak": {"snaktype": "value", "datavalue": {
                                            "value": {"id": "Q192541"}}}}],
                                        "P577": [{"mainsnak": {"snaktype": "value", "datavalue": {
                                            "value": {"time": "+1998-11-27T00:00:00Z"}}}}],
                                    }}}}
COMPANY = {"entities": {"Q192541": {"labels": {"en": {"value": "Sega"}},
                                    "claims": {"P154": [{"mainsnak": {"snaktype": "value", "datavalue": {
                                        "value": "SEGA logo.svg"}}}]}}}}


class WikidataTest(unittest.TestCase):

    def provider(self, answers):
        p = wikidata.WikidataProvider(no_log)
        p._get = mock.Mock(side_effect=answers)
        return p

    def test_describes_a_machine_and_its_pictures(self):
        p = self.provider([SEARCH, MACHINE, COMPANY])
        info = p.platform(request())
        self.assertEqual(info["name"], "Dreamcast")
        self.assertEqual(info["manufacturer"], "Sega")
        self.assertEqual(info["released"], 1998)
        self.assertEqual(sorted(info["art"]), ["clearlogo", "logo", "photo"])
        self.assertEqual(info["art"]["photo"][0]["url"],
                         "https://commons.wikimedia.org/wiki/Special:FilePath/"
                         "Dreamcast_Console_Set.jpg?width=1280")

    def test_skips_hits_that_are_not_machines(self):
        p = self.provider([SEARCH, MACHINE, COMPANY])
        p.platform(request())
        # the fan game was passed over: the first entity asked for is the console
        self.assertEqual(p._get.call_args_list[1].args[0]["ids"], "Q184198")

    def test_nothing_found_is_remembered_as_nothing(self):
        p = self.provider([{"search": []}, {"search": []}, {"search": []}])
        self.assertIsNone(p.platform(request()))

    def test_says_nothing_about_games(self):
        p = self.provider([])
        self.assertEqual(p.find(request()), [])
        self.assertIsNone(p.details("Q184198", request()))

    def test_a_missing_manufacturer_is_not_fatal(self):
        machine = json.loads(json.dumps(MACHINE))
        del machine["entities"]["Q184198"]["claims"]["P176"]
        p = self.provider([SEARCH, machine])
        info = p.platform(request())
        self.assertEqual(sorted(info["art"]), ["clearlogo", "photo"])
        self.assertNotIn("manufacturer", info)


if __name__ == "__main__":
    unittest.main()
