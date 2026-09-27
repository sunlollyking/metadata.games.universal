"""The player's ScreenScraper login never reaches the library."""
import xml.etree.ElementTree as ET

from resources.lib.providers import screenscraper as ss

MEDIA_URL = ("https://neoclone.screenscraper.fr/api2/mediaJeu.php?devid=dev&devpassword=devpass"
             "&softname=kodi&ssid=player&sspassword=secret&systemeid=29&jeuid=14347&media=ss(jp)")


def test_the_login_is_dropped_and_the_rest_kept_as_written():
    assert ss.public_url(MEDIA_URL) == (
        "https://neoclone.screenscraper.fr/api2/mediaJeu.php?devid=dev&devpassword=devpass"
        "&softname=kodi&systemeid=29&jeuid=14347&media=ss(jp)")


def test_a_url_without_a_login_is_unchanged():
    url = "https://neoclone.screenscraper.fr/api2/mediaJeu.php?devid=dev&jeuid=1&media=wheel"
    assert ss.public_url(url) == url


def test_a_url_without_a_query_is_unchanged():
    assert ss.public_url("https://example.org/a.png") == "https://example.org/a.png"


def test_art_from_a_record_carries_no_login():
    elements = ET.fromstring(
        '<medias><media type="wheel" region="wor">{}</media></medias>'.format(
            MEDIA_URL.replace("&", "&amp;"))).findall("media")
    art = ss.media(elements, {"wheel": "clearlogo"}, ["wor"])
    url = art["clearlogo"][0]["url"]
    assert "ssid=" not in url and "sspassword=" not in url
    assert "devid=dev" in url
