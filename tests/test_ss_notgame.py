"""A record ScreenScraper files as not a game describes no game."""
import xml.etree.ElementTree as ET

from resources.lib.providers import screenscraper as ss


def jeu(**attrs):
    return ET.fromstring('<jeu {}><noms><nom region="ss">ZZZ(notgame):#NONGAME</nom></noms></jeu>'.format(
        " ".join('{}="{}"'.format(k, v) for k, v in attrs.items())))


def test_the_flag_is_recognised():
    assert ss.not_a_game(jeu(id="1", notgame="true"))
    assert ss.not_a_game(jeu(id="1", notgame="TRUE"))
    assert ss.not_a_game(jeu(id="1", notgame=" true "))


def test_an_ordinary_record_is_not_flagged():
    assert not ss.not_a_game(jeu(id="1"))
    assert not ss.not_a_game(jeu(id="1", notgame="false"))
    assert not ss.not_a_game(jeu(id="1", notgame=""))
