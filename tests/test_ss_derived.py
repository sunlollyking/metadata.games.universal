"""A dump made from another game is not that game."""
import xml.etree.ElementTree as ET

from resources.lib.providers import screenscraper as ss


def jeu(**romflags):
    flags = dict.fromkeys(("beta", "demo", "proto", "trad", "hack", "unl"), "0")
    flags.update({k: str(v) for k, v in romflags.items()})
    attrs = " ".join('{}="{}"'.format(k, v) for k, v in flags.items())
    return ET.fromstring(
        '<jeu id="109"><noms><nom region="wor">FIFA Soccer 95</nom></noms>'
        '<rom romfilename="x.md" {} /></jeu>'.format(attrs))


def test_a_hack_is_called_a_mod():
    assert ss.derived_edition(jeu(hack="1")) == "Mod"


def test_a_fan_translation_says_so():
    assert ss.derived_edition(jeu(trad="1")) == "Fan Translation"


def test_an_unlicensed_reissue_says_so():
    assert ss.derived_edition(jeu(unl="1")) == "Unlicensed"


def test_an_ordinary_dump_is_not_derived():
    assert ss.derived_edition(jeu()) == ""


def test_a_record_with_no_dump_decides_nothing():
    assert ss.derived_edition(ET.fromstring('<jeu id="1"><noms/></jeu>')) == ""
