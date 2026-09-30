"""Age ratings and companies under one name, whichever catalogue supplied them."""
import unittest

from resources.lib import ageratings, companies
from resources.lib.providers import igdb


class AgeRatingTest(unittest.TestCase):
    def test_a_magazine_reference_is_not_a_rating(self):
        self.assertEqual(ageratings.normalise([{"board": "SEGA", "value": "pro_UK_01"},
                                               {"board": "SEGA", "value": "Force16UK"},
                                               {"board": "Tectoy", "value": "TI"}]),
                         [{"board": "Tectoy", "value": "TI"}])

    def test_boards_and_values_have_one_spelling(self):
        self.assertEqual(ageratings.normalise([{"board": "ClassInd", "value": "L"},
                                               {"board": "acb", "value": "MA 15+"},
                                               {"board": "CERO", "value": "free"},
                                               {"board": "GRAC", "value": "19+"}]),
                         [{"board": "CLASS_IND", "value": "L"}, {"board": "ACB", "value": "MA15+"},
                          {"board": "CERO", "value": "A"}, {"board": "GRAC", "value": "18"}])

    def test_the_first_catalogue_to_rate_a_board_stands(self):
        self.assertEqual(ageratings.normalise([{"board": "ESRB", "value": "E"},
                                               {"board": "ESRB", "value": "T"}]),
                         [{"board": "ESRB", "value": "E"}])

    def test_the_igdb_mix_up_is_undone(self):
        self.assertEqual(ageratings.repair_igdb([{"board": "ESRB", "value": "12"},
                                                 {"board": "PEGI", "value": "E10+"}]),
                         [{"board": "ESRB", "value": "E"}, {"board": "PEGI", "value": "7"}])
        self.assertEqual(ageratings.repair_igdb([{"board": "ESRB", "value": "RP"}]),
                         [{"board": "ESRB", "value": "M"}])

    def test_early_childhood_becomes_adults_only_only_beside_an_adult_rating(self):
        self.assertEqual(ageratings.repair_igdb([{"board": "ESRB", "value": "EC"}]),
                         [{"board": "ESRB", "value": "EC"}])
        self.assertEqual(ageratings.repair_igdb([{"board": "ESRB", "value": "EC"},
                                                 {"board": "PEGI", "value": "AO"}]),
                         [{"board": "ESRB", "value": "AO"}, {"board": "PEGI", "value": "18"}])

    def test_igdb_reads_the_current_categories_and_the_old_enum(self):
        current = {"age_ratings": [{"organization": 1, "rating_category": 3},
                                   {"organization": 2, "rating_category": 10}]}
        old = {"age_ratings": [{"category": 1, "rating": 8}, {"category": 2, "rating": 3}]}
        expected = [{"board": "ESRB", "value": "E", "descriptors": ""},
                    {"board": "PEGI", "value": "12", "descriptors": ""}]
        self.assertEqual(igdb.age_ratings(current), expected)
        self.assertEqual(igdb.age_ratings(old), expected)


class CompanyTest(unittest.TestCase):
    def test_several_companies_in_one_name_are_split(self):
        self.assertEqual(companies.normalise(["Koei | Tecmo, Scavenger", "Compile / Sega", "Sega/Gremlin"]),
                         ["Koei", "Tecmo", "Scavenger", "Compile", "Sega", "Gremlin"])

    def test_the_company_form_is_not_a_company(self):
        self.assertEqual(companies.normalise(["Hi Tech Expressions, Inc.", "Nintendo Co., Ltd."]),
                         ["Hi Tech Expressions", "Nintendo"])

    def test_a_regional_arm_is_its_company(self):
        self.assertEqual(companies.normalise(["SEGA of America", "SEGA Enterprises Ltd.", "Capcom U.S.A., Inc."]),
                         ["Sega", "Capcom"])

    def test_a_form_behind_a_region_is_removed_too(self):
        self.assertEqual(companies.normalise(["Taito Corporation Japan"]), ["Taito"])

    def test_licences_brackets_and_placeholders(self):
        self.assertEqual(companies.normalise(["[Seibu Kaihatsu] (Taito license)", "bootleg (Inder)",
                                              "&lt;unknown&gt;"]),
                         ["Seibu Kaihatsu", "Inder"])

    def test_an_ampersand_is_part_of_a_name(self):
        self.assertEqual(companies.normalise(["Source Research & Development Ltd."]),
                         ["Source Research & Development"])


if __name__ == "__main__":
    unittest.main()
