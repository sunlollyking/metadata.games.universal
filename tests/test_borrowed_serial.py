"""A disc carrying another game's header is not that game."""
import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, os.path.dirname(TESTS_DIR))
import kodistubs  # noqa: E402

kodistubs.install()

from resources.lib import universal  # noqa: E402
from resources.lib.providers import Request  # noqa: E402
from test_universal import Scripted, cand, no_log  # noqa: E402


def borrowed(own, offered, matchedby="serial"):
    return universal.borrowed_serial({"title": offered, "matchedby": matchedby}, Request({"title": own}, {}))


def test_a_header_from_another_game_is_borrowed():
    # Each of these was filed as the other game by its serial
    assert borrowed("Half-Life", "Crazy Taxi")
    assert borrowed("Silpheed", "Double Switch")
    assert borrowed("Urban Chaos", "Threads of Fate")
    assert borrowed("Superbike 98", "San Francisco Rush - Extreme Racing")


def test_the_same_game_under_its_catalogue_name_is_not():
    assert not borrowed("Resident Evil - Code Veronica X", "Resident Evil - Code - Veronica")
    assert not borrowed("Crazy Taxi", "Crazy Taxi")
    assert not borrowed("D", "D")
    assert not borrowed("S.C.A.R.S.", "S.C.A.R.S.")
    assert not borrowed("Shenmue II", "Shenmue 2")


def test_a_shared_number_is_not_a_shared_name():
    assert borrowed("Tekken 2", "Ridge Racer 2")


def test_nothing_to_compare_trusts_the_serial():
    assert not borrowed("", "Crazy Taxi")
    assert not borrowed("disc", "Crazy Taxi")
    assert not borrowed("track01", "Crazy Taxi")


def test_a_hash_is_never_doubted():
    assert not borrowed("Half-Life", "Crazy Taxi", matchedby="hash")
    assert not borrowed("Half-Life", "Crazy Taxi", matchedby="name")


def test_a_borrowed_serial_falls_back_to_a_name_match():
    a = Scripted("a", [cand("taxi", "serial", "Crazy Taxi")])
    b = Scripted("b", [cand("hl", "name", "Half-Life")])
    req = Request({"title": "Half-Life", "serial": "MK51035"}, {"provider_order": "a,b"})
    found = universal.Universal([a, b], no_log).find(req)
    assert [c["id"] for c in found] == ["b:hl"]


def test_a_fitting_serial_still_settles_it():
    a = Scripted("a", [cand("taxi", "serial", "Crazy Taxi")])
    b = Scripted("b", [cand("other", "name", "Crazy Taxi 2")])
    req = Request({"title": "Crazy Taxi", "serial": "MK51035"}, {"provider_order": "a,b"})
    found = universal.Universal([a, b], no_log).find(req)
    assert [c["id"] for c in found] == ["a:taxi"]
    assert b.calls == []
