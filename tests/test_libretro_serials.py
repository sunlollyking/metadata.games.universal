"""A disc and a catalogue rarely spell a serial the same way."""
import os
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, ADDON_DIR)

from resources.lib.providers.libretro import Catalogue, serial_keys  # noqa: E402


class SerialKeyTest(unittest.TestCase):
    def test_a_sega_disc_is_also_looked_up_without_its_prefix(self):
        # The disc header says MK-51035, the catalogue records 51035
        self.assertEqual(serial_keys("MK51035"), ["MK51035", "51035"])

    def test_a_catalogue_number_is_also_indexed_with_the_prefix(self):
        self.assertEqual(serial_keys("81800"), ["81800", "MK81800"])

    def test_a_third_party_serial_is_left_alone(self):
        self.assertEqual(serial_keys("T40201N"), ["T40201N"])

    def test_a_disc_number_the_catalogue_adds_is_dropped(self):
        self.assertEqual(serial_keys("T33005G1"), ["T33005G1", "T33005G"])

    def test_nothing_is_made_of_nothing(self):
        self.assertEqual(serial_keys(""), [])


class CatalogueSerialTest(unittest.TestCase):
    def catalogue(self, records):
        cat = Catalogue("Sega - Dreamcast")
        for rec in records:
            cat.add(rec)
        return cat

    def test_a_disc_finds_the_entry_recorded_without_the_prefix(self):
        cat = self.catalogue([{"name": "Crazy Taxi (USA) (En,Ja)", "serial": "51035"}])
        found = cat.find({"serial": "MK-51035"})
        self.assertEqual([c["matchedby"] for c in found], ["serial"])
        self.assertEqual(found[0]["title"], "Crazy Taxi")

    def test_a_disc_finds_an_entry_recorded_with_a_hyphen(self):
        cat = self.catalogue([{"name": "Armada (USA)", "serial": "T-40301N"}])
        self.assertEqual(len(cat.find({"serial": "T40301N"})), 1)

    def test_an_unknown_serial_finds_nothing(self):
        cat = self.catalogue([{"name": "Armada (USA)", "serial": "T-40301N"}])
        self.assertEqual(cat.find({"serial": "T-99999Z"}), [])


if __name__ == "__main__":
    unittest.main()


class LeadingNumberTest(unittest.TestCase):
    def catalogue(self, *names):
        cat = Catalogue("Nintendo - Nintendo 64")
        for name in names:
            cat.add({"name": name})
        return cat

    def test_a_number_moved_to_the_front_still_finds_the_game(self):
        cat = self.catalogue("GoldenEye 007 (USA)")
        found = cat.find({"title": "GoldenEye", "filename": "007 - GoldenEye.v64"})
        self.assertEqual([c["title"] for c in found], ["GoldenEye 007"])

    def test_a_catalogue_number_is_still_dropped(self):
        cat = self.catalogue("Some DS Game (USA)")
        found = cat.find({"title": "Some DS Game", "filename": "0123 - Some DS Game (USA).nds"})
        self.assertEqual([c["title"] for c in found], ["Some DS Game"])

    def test_the_plain_title_wins_where_both_could_match(self):
        cat = self.catalogue("GoldenEye (USA)", "GoldenEye 007 (USA)")
        found = cat.find({"title": "GoldenEye", "filename": "007 - GoldenEye.v64"})
        self.assertEqual([c["title"] for c in found], ["GoldenEye"])
