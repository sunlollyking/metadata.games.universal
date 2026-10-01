"""ScreenScraper's names and pictures follow the player's regions before the dump's."""
import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, os.path.dirname(TESTS_DIR))
import kodistubs  # noqa: E402

kodistubs.install()

from resources.lib.providers import Request  # noqa: E402
from resources.lib.providers import screenscraper as ss  # noqa: E402


def test_the_players_regions_come_first_then_the_dumps():
    req = Request({"regions": "Japan", "preferredregions": "Europe,World,USA,Japan"}, {})
    assert ss.preference(req, ss.ART_REGIONS) == ["eu", "wor", "us", "jp"]


def test_a_country_falls_back_to_its_dump_and_the_usual_order():
    req = Request({"regions": "USA", "preferredregions": "United Kingdom,Europe"}, {})
    assert ss.preference(req, ss.ART_REGIONS)[:3] == ["uk", "eu", "us"]


def test_without_a_preference_the_dumps_region_leads():
    req = Request({"regions": "Japan"}, {})
    assert ss.preference(req, ss.ART_REGIONS) == ["jp", "wor", "us", "eu"]
