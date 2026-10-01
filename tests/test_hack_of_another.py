"""A hack, a fan translation or a reissue a catalogue files under its game is a version of it."""
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

SONIC2 = {"title": "Sonic the Hedgehog 2 Rev 1", "overview": "Sonic and Tails...", "genres": ["Platform"],
          "releases": [{"title": "Sonic the Hedgehog 2 Rev 1 [h11]", "crc32": "85486e22"},
                       {"title": "Sonic The Hedgehog 2 (World) (Rev A)", "crc32": "7b905383"}]}


def details(filename, dump):
    a = Scripted("a", [cand("1", "hash")], details={"1": dict(SONIC2, dump=dump)})
    req = Request({"filename": filename, "crc32": "85486e22"}, {"provider_order": "a"})
    return universal.Universal([a], no_log).details("a:1", req)


def test_a_hack_named_as_another_game_is_a_version_of_the_game_it_was_made_from():
    out = details("Sonic 2 Delta II.bin", {"name": "Sonic the Hedgehog 2 Rev 1 [h11]", "edition": "Mod"})
    assert out["title"] == "Sonic the Hedgehog 2"
    assert out["overview"] == "Sonic and Tails..."
    assert out["releases"][0] == {"title": "Sonic 2 Delta II", "edition": "Mod", "crc32": "85486e22"}
    # The catalogue's own entry for that dump is replaced, the others kept
    assert [r["crc32"] for r in out["releases"]] == ["85486e22", "7b905383"]
    assert "dump" not in out


def test_a_modified_dump_with_the_games_own_name_is_still_marked_a_hack():
    out = details("Sonic the Hedgehog 2 (W) [h1].bin",
                  {"name": "Sonic the Hedgehog 2 Rev 1 [h11]", "edition": "Mod"})
    assert out["releases"][0]["title"] == "Sonic the Hedgehog 2"
    assert out["releases"][0]["edition"] == "Mod"


def test_an_unlicensed_reissue_is_a_version_under_its_own_licence():
    out = details("Futbol Argentino 98.md", {"name": "x.md", "edition": "Unlicensed"})
    assert out["releases"][0]["licence"] == "unlicensed"
    assert "edition" not in out["releases"][0]


def test_an_ordinary_dump_adds_no_version():
    out = details("Sonic 2.bin", {"name": "Sonic The Hedgehog 2 (World) (Rev A)", "edition": ""})
    assert len(out["releases"]) == 2
    assert out["title"] == "Sonic the Hedgehog 2 Rev 1"


def test_the_tags_that_mark_a_hack():
    assert namer.parse("Sonic the Hedgehog 2 Rev 1 [h11]", strip_extension=False)["modified"]
    assert not namer.parse("Sonic the Hedgehog 2 Rev 1 [h11]", strip_extension=False)["hack"]
    assert namer.parse("Sonic Boom By Snkenjoi (S2 Hack).zip")["hack"]
    assert namer.parse("Sonic Boom By Snkenjoi (S2 Hack).zip")["title"] == "Sonic Boom By Snkenjoi"
    assert not namer.parse("Sonic The Hedgehog 2 (World) (Rev A).bin")["modified"]


def test_a_hack_is_named_by_whoever_names_it():
    # The catalogue names the dump as another work
    assert namer.hack_name("Mario Adventure [h][Super Mario Bros. 3]", "smb3-ma.nes",
                           "Super Mario Bros. 3") == "smb3-ma"
    assert namer.hack_name("Mario Adventure [h][Super Mario Bros. 3]", "",
                           "Super Mario Bros. 3") == "Mario Adventure"
    # A numbered GoodTools hack is named only by its file
    assert namer.hack_name("Sonic the Hedgehog 2 Rev 1 [h11]", "Sonic 2 Delta II.bin",
                           "Sonic The Hedgehog 2") == "Sonic 2 Delta II"
    # A group's tag is the game itself, whatever the file is called
    assert namer.hack_name("Steve Davis Snooker (United Kingdom)[h Homesoft]", "Snooker.atr",
                           "Steve Davis Snooker") == ""


def test_a_hack_another_catalogue_lists_as_a_game_stays_that_game():
    a = Scripted("a", [cand("1", "hash")], details={"1": dict(SONIC2, dump={
        "name": "Sonic Boom By Snkenjoi (S2 Hack).zip", "edition": "Mod"})})
    b = Scripted("b", [cand("18309", "hash", title="Sonic Boom")],
                 details={"18309": {"title": "Sonic Boom", "edition": "Mod"}})
    req = Request({"filename": "Sonic Boom.bin", "crc32": "aa903c50"}, {"provider_order": "a,b"})
    out = universal.Universal([a, b], no_log).details("a:1", req)
    assert out["title"] == "Sonic Boom"
    assert "releases" not in out or all(r.get("edition") != "Mod" for r in out["releases"])


def test_a_hack_no_other_catalogue_lists_is_a_version():
    a = Scripted("a", [cand("1", "hash")], details={"1": dict(SONIC2, dump={
        "name": "Sonic the Hedgehog 2 Rev 1 [h11]", "edition": "Mod"})})
    # The other catalogue knows the dump only as the game it was made from
    b = Scripted("b", [cand("3", "hash", title="Sonic The Hedgehog 2")],
                 details={"3": {"title": "Sonic The Hedgehog 2"}})
    req = Request({"filename": "Sonic 2 Delta II.bin", "crc32": "85486e22"}, {"provider_order": "a,b"})
    out = universal.Universal([a, b], no_log).details("a:1", req)
    assert out["title"] == "Sonic the Hedgehog 2"
    assert out["releases"][0]["title"] == "Sonic 2 Delta II"
