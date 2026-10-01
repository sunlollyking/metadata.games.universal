"""A file's own tags say when a game is homebrew or a demo; a hack is a version of its game."""
import os
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, os.path.dirname(TESTS_DIR))
import kodistubs  # noqa: E402

kodistubs.install()

from resources.lib.universal import file_category  # noqa: E402


class FileCategoryTest(unittest.TestCase):
    def test_tags_raise_retail(self):
        self.assertEqual(file_category("retail", "Cool Game (PD).tap"), "homebrew")
        self.assertEqual(file_category("retail", "Zaku (USA) (Aftermarket) (Unl).zip"), "homebrew")
        self.assertEqual(file_category("retail", "Game (Europe) (Demo).iso"), "demo")

    def test_a_hack_leaves_the_game_it_was_made_from_as_it_is(self):
        for name in ("Taxman [h mod-keyset].dsk", "Madden NFL 98 (USA)[h3].bin",
                     "Angel Dive [HD].zip", "Redux Dark Matters [HUCAST].cdi",
                     "Valis (Disk 1) [hack].d88", "Sperm Invaders [h of Space Invaders].atr"):
            self.assertEqual(file_category("retail", name), "retail", name)

    def test_era_software_stays_retail(self):
        for name in ("Pier Solar (USA) (Unl).cue", "Game (USA) (Proto).zip", "Game (USA).nes"):
            self.assertEqual(file_category("retail", name), "retail", name)

    def test_a_tag_never_lowers_a_category(self):
        self.assertEqual(file_category("bios", "System [hack].rom"), "bios")
        self.assertEqual(file_category("hack", "Game (Demo).nes"), "hack")


if __name__ == "__main__":
    unittest.main()
