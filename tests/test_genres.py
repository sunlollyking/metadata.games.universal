"""Every catalogue's spelling of a genre ends up as one name."""
import os
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TESTS_DIR))

from resources.lib import genres  # noqa: E402


class GenreTest(unittest.TestCase):
    def test_spellings_of_one_genre_become_one(self):
        self.assertEqual(genres.normalise(["Role Playing Game", "RPG", "Role-playing (RPG)"]),
                         ["Role-Playing (RPG)"])
        self.assertEqual(genres.normalise(["Shoot'em Up", "Shoot 'em Up", "Shoot-'Em-Up"]),
                         ["Shoot 'em Up"])

    def test_a_sport_is_sports(self):
        self.assertEqual(genres.normalise(["Sports - Golf", "Sports (Tennis)",
                                           "Extreme Sports - BMX"]), ["Sports"])

    def test_a_nested_name_keeps_its_most_specific_known_level(self):
        self.assertEqual(genres.normalise(["Action » Shooter » Shoot-'Em-Up » Horizontal"]),
                         ["Shoot 'em Up"])

    def test_a_path_keeps_only_its_genres(self):
        self.assertEqual(genres.normalise(["Sports,Traditional,Golf,Sim"]), ["Sports"])

    def test_a_list_is_not_split_inside_brackets(self):
        self.assertEqual(genres.split("Platforming (Side-Scrolling, 2.5D), Action", ","),
                         ["Platforming (Side-Scrolling, 2.5D)", "Action"])

    def test_a_name_split_mid_bracket_keeps_what_it_says(self):
        self.assertEqual(genres.normalise(["Sports (Football", "Soccer)"]), ["Sports"])

    def test_words_that_say_nothing_are_dropped(self):
        self.assertEqual(genres.normalise(["Various", "Other", "Unknown", "Action"]), ["Action"])

    def test_every_clean_name_stays_as_it_is(self):
        for name in genres.KNOWN:
            self.assertEqual(genres.normalise([name]), [name], name)

    def test_an_unknown_genre_is_kept_as_written(self):
        self.assertEqual(genres.normalise(["Kaiju Wrangling"]), ["Kaiju Wrangling"])


if __name__ == "__main__":
    unittest.main()
