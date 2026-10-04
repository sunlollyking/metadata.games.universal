"""The LaunchBox provider, against a slice of the published catalogue."""
import os
import shutil
import tempfile
import unittest

from resources.lib.providers import Request
from resources.lib.providers import launchbox

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "launchbox_metadata.zip")
GENESIS = {"launchbox": "Sega Genesis", "libretro": "Sega - Mega Drive - Genesis"}


def request(title, platform_ids=None, **extra):
    query = {"title": title, "platformids": __import__("json").dumps(platform_ids or GENESIS)}
    query.update(extra)
    return Request(query, {})


class LaunchBoxTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.logged = []
        self.provider = launchbox.LaunchBoxProvider(
            lambda message, notable: self.logged.append(message), self.dir)
        # Build straight from the fixture rather than the network
        self.provider.index._download = lambda target: shutil.copyfile(FIXTURE, target)
        self.provider.prefetch([])

    def tearDown(self):
        self.provider.index.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_the_index_is_built_once_from_the_archive(self):
        self.assertTrue(os.path.exists(self.provider.index.path))
        self.assertTrue(any("indexed 3 games" in m for m in self.logged))

    def test_a_game_is_found_by_name_on_its_platform(self):
        found = self.provider.find(request("Ecco the Dolphin"))
        self.assertEqual([(c["id"], c["title"]) for c in found], [("2900", "Ecco the Dolphin")])

    def test_a_name_from_another_platform_is_not_offered(self):
        self.assertEqual(self.provider.find(request("Ecco the Dolphin", {"launchbox": "Atari 800"})), [])

    def test_a_name_that_is_not_in_the_catalogue_is_not_offered(self):
        self.assertEqual(self.provider.find(request("No Such Game At All")), [])

    def test_details_carry_the_prose_and_the_companies(self):
        details = self.provider.details("2900", request("Ecco the Dolphin"))
        self.assertEqual(details["title"], "Ecco the Dolphin")
        self.assertTrue(details["overview"])
        self.assertEqual(details["uniqueids"], {"launchbox": "2900"})
        self.assertTrue(details["developers"])
        self.assertTrue(details["publishers"])
        self.assertEqual(details["year"], 1992)

    def test_cooperative_play_is_reported_on_its_own(self):
        self.provider.index.connect().execute("UPDATE game SET players = 2, cooperative = 1 WHERE id = 2900")
        details = self.provider.details("2900", request("Ecco the Dolphin"))
        self.assertEqual(details["players"], {"min": 1, "max": 2})
        self.assertIs(details["coop"], True)

    def test_a_game_not_filed_as_cooperative_says_nothing_about_it(self):
        self.assertNotIn("coop", self.provider.details("2900", request("Ecco the Dolphin")))

    def test_pictures_become_library_names_with_full_urls(self):
        art = self.provider.details("2900", request("Ecco the Dolphin"))["art"]
        self.assertIn("boxfront", art)
        self.assertTrue(art["boxfront"][0]["url"].startswith("https://images.launchbox-app.com/"))
        for pictures in art.values():
            for picture in pictures:
                self.assertNotIn("None", picture["url"])

    def test_a_real_scan_is_offered_before_a_reconstruction_or_fan_art(self):
        self.assertLess(launchbox.ART_RANK["Box - Front"],
                        launchbox.ART_RANK["Box - Front - Reconstructed"])
        self.assertLess(launchbox.ART_RANK["Box - Front - Reconstructed"],
                        launchbox.ART_RANK["Fanart - Box - Front"])

    def test_an_unknown_id_describes_nothing(self):
        self.assertIsNone(self.provider.details("999999999", request("Whatever")))

    def test_details_cost_nothing_once_a_game_is_found(self):
        self.assertTrue(self.provider.details_are_free)

    def test_turning_the_catalogue_off_makes_the_provider_unavailable(self):
        self.assertTrue(self.provider.available({}))
        self.assertTrue(self.provider.available({"launchbox_bulk": "true"}))
        self.assertFalse(self.provider.available({"launchbox_bulk": "false"}))

    def test_a_failed_build_is_not_retried_for_every_game(self):
        provider = launchbox.LaunchBoxProvider(lambda m, n: self.logged.append(m),
                                               os.path.join(self.dir, "broken"))
        calls = []

        def explode(target):
            calls.append(target)
            raise OSError("no network")

        provider.index._download = explode
        self.assertEqual(provider.find(request("Ecco the Dolphin")), [])
        self.assertEqual(provider.find(request("Sonic the Hedgehog")), [])
        self.assertEqual(len(calls), 1)


class YearTest(unittest.TestCase):
    def test_a_year_is_read_from_either_a_date_or_a_year(self):
        self.assertEqual(launchbox.year_of("1992-05-29"), 1992)
        self.assertEqual(launchbox.year_of("1992"), 1992)
        self.assertEqual(launchbox.year_of(""), 0)
        self.assertEqual(launchbox.year_of("not a date"), 0)


if __name__ == "__main__":
    unittest.main()
