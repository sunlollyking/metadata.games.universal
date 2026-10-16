"""A file named for its part in a dump, like every GD-ROM's disc.gdi, names no game."""
import xml.etree.ElementTree as ET

from resources.lib import namer
from resources.lib.providers import Request
from resources.lib.providers import screenscraper as ss

BERSERK = ET.fromstring('<jeu id="78509"><noms><nom region="us">Sword of the Berserk: Guts\' Rage</nom></noms>'
                        '<rom><romfilename>disc.gdi</romfilename></rom></jeu>')


def request(**query):
    return Request(dict({"platform": "dreamcast", "platformids": '{"screenscraper": "23"}'}, **query), {})


def provider():
    return ss.ScreenScraperProvider(lambda *_: None)


def test_dump_part_names_are_generic():
    for name in ("disc.gdi", "DISC.GDI", "track01.bin", "track 03.raw", "disk1.img", "game.cue", "cd.iso"):
        assert namer.generic_name(name), name


def test_game_names_are_not_generic():
    for name in ("Crazy Taxi (USA).gdi", "Disc Station Vol. 1.cue", "Discworld (Europe).cue", "track.bin.zip"):
        assert not namer.generic_name(name), name


def test_a_generic_file_is_not_looked_up_by_name():
    identity = provider()._identity(request(title="Ecco II", filename="disc.gdi", size="144"))
    assert "romnom" not in identity and "romtaille" not in identity


def test_a_named_file_is_still_looked_up_by_name():
    identity = provider()._identity(request(title="Crazy Taxi", filename="Crazy Taxi (USA).gdi", size="144"))
    assert identity["romnom"] == "Crazy Taxi (USA).gdi"
    assert identity["romtaille"] == "144"


def test_a_shared_generic_file_name_does_not_match_another_game():
    assert not ss.name_matches(BERSERK, request(title="Ecco II Sentinels of the Universe", filename="disc.gdi"))


def test_the_title_still_matches():
    assert ss.name_matches(BERSERK, request(title="Sword of the Berserk: Guts' Rage", filename="disc.gdi"))
