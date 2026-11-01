"""A game's names are written without the space ScreenScraper puts before a colon."""
import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, os.path.dirname(TESTS_DIR))
import kodistubs  # noqa: E402

kodistubs.install()

from resources.lib import namer, universal  # noqa: E402
from resources.lib.providers import Request  # noqa: E402
from test_universal import Scripted, cand, no_log  # noqa: E402


def test_the_space_before_a_colon_goes():
    assert namer.colon_spacing("Rance II : Hangyaku no Shoujotachi") == "Rance II: Hangyaku no Shoujotachi"
    assert namer.colon_spacing("Net Guardian :  Dai Kyo Utage") == "Net Guardian: Dai Kyo Utage"
    assert namer.colon_spacing("Sherlock Holmes : Consulting Detective : Vol. II") == \
        "Sherlock Holmes: Consulting Detective: Vol. II"
    assert namer.colon_spacing("Spider-Man: Shattered Dimensions") == "Spider-Man: Shattered Dimensions"
    assert namer.colon_spacing("Re:Zero") == "Re:Zero"


def test_a_games_title_original_title_and_releases_are_written_without_it():
    a = Scripted("a", [cand("1", "hash")], details={"1": {
        "title": "Last Window : The Secret of Cape West",
        "originaltitle": "Last Window : Mayonaka no Yakusoku",
        "releases": [{"title": "Last Window : The Secret of Cape West", "crc32": "4a1b2c3d"}]}})
    req = Request({"filename": "Last Window - The Secret of Cape West (Europe).nds"}, {"provider_order": "a"})
    out = universal.Universal([a], no_log).details("a:1", req)
    assert out["title"] == "Last Window: The Secret of Cape West"
    assert out["originaltitle"] == "Last Window: Mayonaka no Yakusoku"
    assert out["releases"][0]["title"] == "Last Window: The Secret of Cape West"
