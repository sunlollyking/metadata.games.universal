"""A number at the front of a name: a scene set's release number, or part of the title."""
from resources.lib import namer


def test_keeps_a_number_that_is_part_of_the_title():
    assert namer.parse("007 - The World Is Not Enough (USA).z64")["title"] == "007 - The World Is Not Enough"
    assert namer.parse("007 Racing (USA).cue")["title"] == "007 Racing"
    assert namer.parse("1943 Kai (Japan).zip")["title"] == "1943 Kai"
    assert namer.parse("007 - The Living Daylights (United Kingdom)", strip_extension=False)["title"] == \
        "007 - The Living Daylights"


def test_drops_a_scene_release_number():
    parsed = namer.parse("0001 Electroplankton (JP).zip")
    assert parsed["title"] == "Electroplankton"
    assert parsed["number"] == "0001"
    assert namer.parse("4737 Super Robot Taisen OG Saga (JP).zip")["title"] == "Super Robot Taisen OG Saga"
    assert namer.parse("0414 My Pet Hotel (EU)(M2).zip")["title"] == "My Pet Hotel"


def test_a_publisher_named_like_a_demo_is_not_one():
    assert namer.parse("Savage (1988)(Demonware).adf")["devstatus"] == "retail"
    assert namer.parse("Savage (Demo 2).adf")["devstatus"] == "demo"
    assert namer.parse("Savage (Kiosk Demo).adf")["devstatus"] == "demo"


def test_keeps_the_number_of_a_title_that_starts_with_one():
    assert namer.parse("007 - GoldenEye.v64")["number"] == "007"


def test_a_dumps_file_name_titles_its_release():
    assert namer.dump_title("0105 - Castlevania - Dawn of Sorrow (E)(Legacy).nds") == \
        "Castlevania - Dawn of Sorrow (E)(Legacy)"
    assert namer.dump_title("Castlevania - Dawn of Sorrow (USA).nds") == "Castlevania - Dawn of Sorrow (USA)"
    assert namer.dump_title("0108 - FIFA 06 (Europe) (En,Fr,De,Es,It,Nl).nds") == \
        "FIFA 06 (Europe) (En,Fr,De,Es,It,Nl)"
    assert namer.dump_title("Mizuiro Blood (J)(iMPAcT).nds.zip") == "Mizuiro Blood (J)(iMPAcT)"
    # A number that is part of the title stays
    assert namer.dump_title("2010 - The Graphic Action Game (USA).col") == "2010 - The Graphic Action Game (USA)"
    assert namer.dump_title("1942 (1986)(Elite)(GB).tap") == "1942 (1986)(Elite)(GB)"
