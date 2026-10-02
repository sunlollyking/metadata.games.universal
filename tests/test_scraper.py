"""Protocol tests for the universal scraper, driven end to end against the local RDB files."""
import json
import os
import sys
import unittest
from unittest import mock
from urllib.parse import urlencode

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(TESTS_DIR)
RDB_DIR = os.environ.get("KODI_GAME_LIBRARY_RDB_DIR", "/home/chris/kodi-game-library/rdb")

sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, ADDON_DIR)
import kodistubs  # noqa: E402

kodistubs.install()
os.environ["METADATA_GAMES_LIBRETRO_CACHE_DIR"] = RDB_DIR

import scraper  # noqa: E402
from resources.lib.providers import libretro  # noqa: E402

MEGADRIVE = {"screenscraper": "1", "libretro": "Sega - Mega Drive - Genesis", "esde": "megadrive"}
PSX = {"screenscraper": "57", "libretro": "Sony - PlayStation", "retroachievements": "12"}
SONIC2_WORLD = "Sonic The Hedgehog 2 (World)"
SONIC2_ID = "libretro:" + SONIC2_WORLD
BASE = "plugin://metadata.games.universal/"
HANDLE = 7


def run(action, platform, platformids, download=False, settings=None, **params):
    conf = {"download": download, "cache_days": 30}
    conf.update(settings or {})
    query = {"action": action, "platform": platform, "platformids": json.dumps(platformids),
             "pathSettings": json.dumps(conf), "protocol": "1"}
    query.update(params)
    scraper.main([BASE, str(HANDLE), "?" + urlencode(query)])


def candidates():
    out = []
    for url, item, is_folder in kodistubs.added.get(HANDLE, []):
        payload = json.loads(item.getProperty("gamelibrary.candidate"))
        out.append((url, item.getLabel(), is_folder, payload))
    return out


def resolved(prop):
    succeeded, item = kodistubs.resolved[HANDLE]
    return succeeded, (json.loads(item.getProperty(prop)) if item.getProperty(prop) else None)


class ScraperTest(unittest.TestCase):
    def setUp(self):
        kodistubs.reset()
        self.no_network = mock.patch("urllib.request.urlopen", side_effect=AssertionError("network access"))
        self.no_network.start()

    def tearDown(self):
        self.no_network.stop()

    def test_the_arcade_provider_can_read_libretros_thumbnail_list(self):
        held = scraper.scraper().providers["arcade"].thumbnails()
        self.assertTrue(held is None or isinstance(held, dict))

    def test_crc_hit(self):
        run("find", "megadrive", MEGADRIVE, crc32="24ab4c3a", title="Something Else Entirely")
        found = candidates()
        self.assertEqual(len(found), 1)
        url, label, is_folder, payload = found[0]
        self.assertEqual(url, SONIC2_ID)
        self.assertFalse(is_folder)
        self.assertEqual(label, "Sonic The Hedgehog 2")
        self.assertEqual(payload, {"id": SONIC2_ID, "title": "Sonic The Hedgehog 2", "year": 1992,
                                   "platform": "megadrive", "score": 1.0, "matchedby": "hash",
                                   "provider": "libretro", "regions": ["World"],
                                   "subtitle": "Sonic The Hedgehog 2 (World)"})
        self.assertTrue(kodistubs.ended[HANDLE])

    def test_serial_hit(self):
        run("find", "psx", PSX, serial="SLUS00300")
        found = candidates()
        self.assertEqual([c[3]["id"] for c in found], ["libretro:Dare Devil Derby 3D (USA)"])
        self.assertEqual(found[0][3]["matchedby"], "serial")
        self.assertEqual(found[0][3]["score"], 1.0)

    def test_serial_normalisation(self):
        self.assertEqual(libretro.norm_serial(b"SLUS-00300"), "SLUS00300")
        self.assertEqual(libretro.norm_serial("slus_003.00"), "SLUS00300")
        self.assertEqual(libretro.norm_serial("GM MK-4407-00 V1.000"), "MK440700")
        self.assertEqual(libretro.norm_serial(None), "")

    def test_serial_fallback_drops_two_trailing_characters(self):
        kodistubs.reset()
        run("find", "psx", PSX, serial="SLUS0030000")
        self.assertEqual([c[3]["id"] for c in candidates()], ["libretro:Dare Devil Derby 3D (USA)"])

    def test_exact_name_hit_from_filename(self):
        run("find", "megadrive", MEGADRIVE, filename="Sonic The Hedgehog 2.bin", regions="World")
        found = candidates()
        ids = [c[3]["id"] for c in found]
        self.assertIn(SONIC2_ID, ids)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(c[3]["matchedby"] == "name" and c[3]["score"] == 0.9 for c in found))
        self.assertTrue(all(c[3]["title"].lower() == "sonic the hedgehog 2" for c in found))
        self.assertTrue(ids[0].startswith(SONIC2_ID))
        self.assertTrue(kodistubs.ended[HANDLE])

    def test_exact_name_hit_from_title_ignores_case_and_article(self):
        run("find", "megadrive", MEGADRIVE, title="sonic the hedgehog 2!")
        self.assertIn(SONIC2_ID, [c[3]["id"] for c in candidates()])

    def test_no_match_returns_nothing(self):
        run("find", "megadrive", MEGADRIVE, crc32="00000000", serial="ZZZZ99999",
            title="A Game That Does Not Exist Anywhere", filename="A Game That Does Not Exist Anywhere.bin")
        self.assertEqual(candidates(), [])
        self.assertTrue(kodistubs.ended[HANDLE])

    def test_platform_without_libretro_id_returns_nothing(self):
        run("find", "archimedes", {"screenscraper": "84"}, title="Zarch")
        self.assertEqual(candidates(), [])
        self.assertTrue(kodistubs.ended[HANDLE])

    def test_details_payload(self):
        run("getdetails", "megadrive", MEGADRIVE, id=SONIC2_ID, crc32="24ab4c3a")
        succeeded, details = resolved("gamelibrary.details")
        self.assertTrue(succeeded)
        self.assertEqual(details["version"], 1)
        self.assertEqual(details["title"], "Sonic The Hedgehog 2")
        # An original title is the game's name in the language it sold in, so a
        # game that went out under one name everywhere has none. The dump's own
        # name is on the release below, which is where it belongs
        self.assertNotIn("originaltitle", details)
        self.assertEqual(details["year"], 1992)
        self.assertEqual(details["releasedate"], "1992-11")
        self.assertEqual(details["developers"], ["Sega"])
        self.assertEqual(details["publishers"], ["Sega"])
        self.assertEqual(details["genres"], ["Action"])
        self.assertEqual(details["collections"], ["Sonic"])
        self.assertEqual(details["players"], {"min": 1, "max": 2})
        self.assertEqual(details["category"], "retail")
        self.assertEqual(details["ageratings"], [{"board": "ESRB", "value": "E", "descriptors": ""}])
        self.assertEqual(details["uniqueids"], {"libretro": SONIC2_WORLD})
        self.assertNotIn("ratings", details)
        self.assertEqual(len(details["releases"]), 1)
        release = details["releases"][0]
        self.assertEqual(release["title"], SONIC2_WORLD)
        self.assertEqual(release["regions"], ["World"])
        self.assertEqual(release["status"], "retail")
        self.assertEqual(release["licence"], "licensed")
        self.assertEqual(release["serial"], "00001051-00")
        self.assertEqual(release["crc32"], "24ab4c3a")
        self.assertEqual(release["md5"], "8e2c29a1e65111fe2078359e685e7943")
        self.assertEqual(release["sha1"], "14dd06fc3aa19a59a818ea1f6de150c9061b14d4")
        self.assertEqual(release["size"], 1048576)

    def test_details_release_tags(self):
        run("getdetails", "megadrive", MEGADRIVE, id="libretro:Sonic The Hedgehog 2 (World) (Rev A)")
        _, details = resolved("gamelibrary.details")
        self.assertEqual(details["releases"][0]["revision"], "Rev A")
        kodistubs.reset()
        run("getdetails", "megadrive", MEGADRIVE, id="libretro:Sonic The Hedgehog 2 (World) (Beta 4)")
        _, details = resolved("gamelibrary.details")
        self.assertEqual(details["releases"][0]["status"], "beta")

    def test_details_full_release_date(self):
        run("getdetails", "psx", PSX, id="libretro:Dare Devil Derby 3D (USA)")
        _, details = resolved("gamelibrary.details")
        self.assertRegex(details["releasedate"], r"^\d{4}-\d{2}(-\d{2})?$")
        self.assertEqual(libretro.release_date(1992, 11, 21), "1992-11-21")
        self.assertEqual(libretro.release_date(1992, 11, None), "1992-11")
        self.assertEqual(libretro.release_date(1992, None, 21), "")

    def test_details_prefers_record_matching_hash(self):
        run("getdetails", "psx", PSX, id="libretro:e-Jump (Japan) (Disc 1)")
        _, details = resolved("gamelibrary.details")
        self.assertTrue(details["releases"][0]["crc32"])

    def test_details_unknown_id_resolves_false(self):
        run("getdetails", "megadrive", MEGADRIVE, id="libretro:No Such Game (World)")
        succeeded, details = resolved("gamelibrary.details")
        self.assertFalse(succeeded)
        self.assertIsNone(details)

    def test_art_urls_use_underscore_rule(self):
        art = libretro.art_urls("Sega - Mega Drive - Genesis", 'Foo: Bar & Baz / Qux? <"*|`\\>', "USA")
        prefix = "https://raw.githubusercontent.com/libretro-thumbnails/Sega_-_Mega_Drive_-_Genesis/master/"
        name = "Foo_%20Bar%20_%20Baz%20_%20Qux_%20_______.png"
        self.assertEqual(art["boxfront"], [{"url": prefix + "Named_Boxarts/" + name, "region": "USA"}])
        self.assertEqual(art["titlescreen"], [{"url": prefix + "Named_Titles/" + name}])
        self.assertEqual(art["screenshot"], [{"url": prefix + "Named_Snaps/" + name}])

    def test_details_art(self):
        run("getdetails", "megadrive", MEGADRIVE, id=SONIC2_ID)
        _, details = resolved("gamelibrary.details")
        self.assertEqual(details["art"]["boxfront"][0], {
            "url": "https://raw.githubusercontent.com/libretro-thumbnails/Sega_-_Mega_Drive_-_Genesis/master/"
                   "Named_Boxarts/Sonic%20The%20Hedgehog%202%20%28World%29.png",
            "region": "World"})

    def test_getplatform(self):
        run("getplatform", "megadrive", MEGADRIVE)
        succeeded, info = resolved("gamelibrary.platform")
        self.assertTrue(succeeded)
        self.assertEqual(info, {"version": 1, "name": "Sega Mega Drive", "manufacturer": "Sega"})

    def test_stale_cache_survives_download_failure(self):
        scraper._universal = None
        run("find", "megadrive", MEGADRIVE, download=True, crc32="24ab4c3a")
        self.assertEqual([c[3]["id"] for c in candidates()], [SONIC2_ID])
        self.assertTrue(kodistubs.ended[HANDLE])

    def test_unknown_action_still_ends_directory(self):
        run("nonsense", "megadrive", MEGADRIVE)
        self.assertIs(kodistubs.ended[HANDLE], False)
        self.assertTrue(any(level == kodistubs.LOGERROR for level, _ in kodistubs.logged))

    def test_broken_details_request_resolves_false(self):
        scraper.main([BASE, str(HANDLE), "?action=getdetails&platformids=%7Bnot-json"])
        self.assertIs(kodistubs.resolved[HANDLE][0], False)

    def test_details_unnamespaced_id_resolves_false(self):
        run("getdetails", "megadrive", MEGADRIVE, id=SONIC2_WORLD)
        succeeded, details = resolved("gamelibrary.details")
        self.assertFalse(succeeded)
        self.assertIsNone(details)

    def test_details_from_unknown_provider_resolves_false(self):
        run("getdetails", "megadrive", MEGADRIVE, id="nosuchprovider:" + SONIC2_WORLD)
        self.assertIs(kodistubs.resolved[HANDLE][0], False)

    def test_online_providers_with_keys_stay_silent_offline(self):
        kodistubs.Addon.settings = {"ra_username": "someone", "ra_api_key": "k", "tgdb_api_key": "k",
                                    "ss_devid": "d", "ss_devpassword": "p", "ss_user": "u", "ss_password": "p",
                                    "igdb_client_id": "c", "igdb_client_secret": "s"}
        try:
            run("find", "megadrive", MEGADRIVE, crc32="24ab4c3a")
            self.assertEqual([c[3]["id"] for c in candidates()], [SONIC2_ID])
            kodistubs.reset()
            run("getdetails", "megadrive", MEGADRIVE, id=SONIC2_ID, crc32="24ab4c3a")
            _, details = resolved("gamelibrary.details")
            self.assertEqual(details["uniqueids"], {"libretro": SONIC2_WORLD})
        finally:
            kodistubs.Addon.settings = {}

    def test_provider_order_without_libretro_finds_nothing(self):
        run("find", "megadrive", MEGADRIVE, crc32="24ab4c3a", settings={"provider_order": "thegamesdb"})
        self.assertEqual(candidates(), [])
        self.assertTrue(kodistubs.ended[HANDLE])

    def test_settings_coercion(self):
        conf = scraper.settings({"pathSettings": json.dumps(
            {"download": "false", "cache_days": "7", "provider_order": " libretro , igdb ", "ra_api_key": ""})})
        self.assertIs(conf["download"], False)
        self.assertEqual(conf["cache_days"], 7)
        self.assertEqual(conf["provider_order"], "libretro , igdb")
        self.assertEqual(conf["ra_api_key"], "")
        self.assertEqual(scraper.settings({"pathSettings": "[1"})["cache_days"], 30)


if __name__ == "__main__":
    unittest.main()


class BatchQueryTest(unittest.TestCase):
    """What a batch carries reaches the providers as a URL would carry it."""

    def test_a_list_in_a_batch_arrives_as_json(self):
        import tempfile
        members = [["074-p1.p1", 2097152, "62369553"], ["074-c1.c1", 2097152, "a0b39344"]]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"version": 1, "queries": [{"filename": "aodk.zip", "members": members}]}, f)
            batch = f.name
        seen = []

        class Engine:
            def prefetch(self, requests):
                pass

            def begin_batch(self):
                pass

            def find(self, request):
                seen.append(request.query)
                return []

        try:
            with mock.patch.object(scraper, "scraper", return_value=Engine()):
                run("findmany", "neogeo", {}, batch=batch)
        finally:
            os.remove(batch)
        self.assertEqual(json.loads(seen[0]["members"]), members)
        self.assertEqual(seen[0]["filename"], "aodk.zip")
