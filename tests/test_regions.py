"""Regions arrive from Kodi as codes and leave for it as codes; the providers name them."""
import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TESTS_DIR))

from resources.lib import regions  # noqa: E402


def test_a_code_from_kodi_is_the_providers_name():
    assert [regions.name(c) for c in ("US", "150", "GB", "142")] == [
        "USA", "Europe", "United Kingdom", "Asia"]


def test_a_market_passes_through_both_ways():
    assert regions.name("World") == "World"
    assert regions.code("World") == "World"
    assert regions.code("Scandinavia") == "Scandinavia"


def test_a_region_the_source_doesnt_know_is_left_out():
    assert regions.code("Unknown") is None
    assert regions.encode({"regions": ["Unknown", "USA"]}) == {"regions": ["US"]}


def test_every_region_in_a_result_is_written_as_a_code():
    details = {"title": "Game", "regions": "USA,Europe,usa",
               "releases": [{"title": "Game (Japan)", "regions": ["Japan"]}],
               "art": {"boxfront": [{"url": "a.png", "region": "United Kingdom"},
                                    {"url": "b.png", "region": "ScreenScraper"}]}}
    assert regions.encode(details) == {
        "title": "Game", "regions": ["US", "150"],
        "releases": [{"title": "Game (Japan)", "regions": ["JP"]}],
        "art": {"boxfront": [{"url": "a.png", "region": "GB"},
                             {"url": "b.png", "region": "ScreenScraper"}]}}
