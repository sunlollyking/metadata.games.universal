"""IGDB still finds a game whose name the catalogues space differently."""
import os
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, ADDON_DIR)
import kodistubs  # noqa: E402

kodistubs.install()

from resources.lib import namer  # noqa: E402
from resources.lib.providers import Request  # noqa: E402
from resources.lib.providers import igdb  # noqa: E402


def no_log(message, error=False):
    pass


class Scripted(igdb.IgdbProvider):
    """IGDB with its queries answered from a script rather than the network."""

    def __init__(self, answers):
        super().__init__(no_log)
        self.answers = answers
        self.bodies = []

    def _platform_id(self, request):
        return "18"

    def _query(self, endpoint, fields, body, request):
        self.bodies.append(body)
        for needle, rows in self.answers:
            if needle in body:
                return rows
        return []


def request(title):
    return Request({"title": title, "platform": "nes"}, {"provider_order": "igdb"})


class SpacingVariantTest(unittest.TestCase):
    def test_a_two_word_name_offers_the_closed_up_form(self):
        self.assertEqual(namer.spacing_variants("Castle Quest"), ["CastleQuest"])

    def test_a_name_with_no_spaces_offers_nothing(self):
        self.assertEqual(namer.spacing_variants("Castlequest"), [])

    def test_a_search_that_finds_nothing_asks_by_name(self):
        provider = Scripted([('name ~ "CastleQuest"', [{"id": 1, "name": "Castlequest"}])])
        self.assertEqual([c["id"] for c in provider.find(request("Castle Quest"))], ["1"])

    def test_the_fallback_uses_the_case_insensitive_operator(self):
        # Plain equality is case-sensitive, so "CastleQuest" would miss
        provider = Scripted([('name ~ "CastleQuest"', [{"id": 1, "name": "Castlequest"}])])
        provider.find(request("Castle Quest"))
        self.assertTrue(any('name ~ "CastleQuest"' in body for body in provider.bodies))

    def test_a_search_that_answers_is_not_asked_again(self):
        provider = Scripted([('search "Castlequest"', [{"id": 1, "name": "Castlequest"}])])
        self.assertEqual([c["id"] for c in provider.find(request("Castlequest"))], ["1"])
        self.assertEqual(len(provider.bodies), 1)

    def test_a_different_game_is_still_refused(self):
        provider = Scripted([('name ~ "CastleQuest"', [{"id": 2, "name": "Castlevania"}])])
        self.assertEqual(provider.find(request("Castle Quest")), [])


if __name__ == "__main__":
    unittest.main()


class EditionTest(unittest.TestCase):
    def test_a_port_says_so(self):
        details = igdb.game_details({"id": 1, "name": "Castlequest", "game_type": 11}, "18")
        self.assertEqual(details["edition"], "Port")

    def test_a_mod_says_so(self):
        details = igdb.game_details({"id": 1, "name": "Hack", "game_type": 5}, "18")
        self.assertEqual(details["edition"], "Mod")

    def test_the_game_itself_says_nothing(self):
        details = igdb.game_details({"id": 1, "name": "Contra", "game_type": 0}, "18")
        self.assertNotIn("edition", details)

    def test_a_port_is_still_the_game(self):
        self.assertTrue(igdb.is_the_game({"game_type": 11}))
        self.assertTrue(igdb.is_the_game({"game_type": 5}))

    def test_an_add_on_is_not(self):
        self.assertFalse(igdb.is_the_game({"game_type": 1}))   # dlc
        self.assertFalse(igdb.is_the_game({"game_type": 2}))   # expansion
        self.assertFalse(igdb.is_the_game({"game_type": 6}))   # episode


class WiderCaptureTest(unittest.TestCase):
    def test_keywords_perspectives_and_engines_become_tags(self):
        details = igdb.game_details({
            "id": 1, "name": "G",
            "keywords": [{"name": "platformer"}],
            "player_perspectives": [{"name": "Side view"}],
            "game_engines": [{"name": "Unity"}],
        }, "18")
        self.assertEqual(details["tags"], ["platformer", "Side view", "Unity"])

    def test_the_critic_score_is_a_rating_of_its_own(self):
        details = igdb.game_details({"id": 1, "name": "G", "aggregated_rating": 82.4,
                                     "aggregated_rating_count": 9}, "18")
        self.assertEqual(details["ratings"]["igdbcritic"],
                         {"rating": 82.4, "max": 100, "votes": 9})

    def test_what_has_no_home_yet_is_kept_together(self):
        details = igdb.game_details({
            "id": 1, "name": "G",
            "alternative_names": [{"name": "Castle Excellent"}],
            "language_supports": [{"language": {"name": "English"}}],
            "websites": [{"url": "https://example.invalid/g"}],
            "videos": [{"video_id": "abc123"}],
            "status": 0,
        }, "18")
        extra = details["igdb"]
        self.assertEqual(extra["alsoknownas"], ["Castle Excellent"])
        self.assertEqual(extra["languages"], ["English"])
        self.assertEqual(extra["websites"], ["https://example.invalid/g"])
        self.assertEqual(extra["videos"], ["https://www.youtube.com/watch?v=abc123"])

    def test_the_trailer_is_one_kodi_can_play(self):
        details = igdb.game_details({"id": 1, "name": "G", "videos": [
            {"video_id": "gameplay1", "name": "Gameplay video"},
            {"video_id": "trailer1", "name": "Launch Trailer"}]}, "18")
        self.assertEqual(details["trailer"], "plugin://plugin.video.youtube/play/?video_id=trailer1")

    def test_a_game_with_nothing_extra_carries_nothing(self):
        self.assertNotIn("igdb", igdb.game_details({"id": 1, "name": "G"}, "18"))


class AlternativeNameTest(unittest.TestCase):
    def test_a_game_answers_to_its_other_names(self):
        row = {"id": 1, "name": "Castlevania III: Dracula's Curse",
               "alternative_names": [{"name": "Akumajou Densetsu"}]}
        self.assertIn(igdb.namer.normalise("Akumajou Densetsu"), igdb.title_keys(row))
        self.assertIn(igdb.namer.normalise("Castlevania III: Dracula's Curse"),
                      igdb.title_keys(row))

    def test_a_japanese_dump_finds_the_western_entry(self):
        row = {"id": 1, "name": "Castlevania III: Dracula's Curse",
               "alternative_names": [{"name": "Akumajou Densetsu"}]}
        provider = Scripted([('search "Akumajou Densetsu"', [row])])
        self.assertEqual([c["id"] for c in provider.find(request("Akumajou Densetsu"))], ["1"])

    def test_an_unrelated_game_is_still_refused(self):
        row = {"id": 1, "name": "Contra", "alternative_names": [{"name": "Probotector"}]}
        provider = Scripted([('search "Gradius"', [row])])
        self.assertEqual(provider.find(request("Gradius")), [])


class OriginalTitleTest(unittest.TestCase):
    ALTS = [{"name": "Devil's Castle Legend", "comment": "Japanese title - translated"},
            {"name": "Akumajou Densetsu", "comment": "Japanese title - romanization"},
            {"name": "Castlevania 3", "comment": "Alternative spelling"},
            {"name": "Castlevania III", "comment": "Abbreviation"}]

    def test_the_romanisation_is_the_original(self):
        self.assertEqual(igdb.original_title({"alternative_names": self.ALTS}),
                         "Akumajou Densetsu")

    def test_a_respelling_is_not(self):
        self.assertEqual(igdb.original_title(
            {"alternative_names": [{"name": "Castlevania 3", "comment": "Alternative spelling"}]}), "")

    def test_a_plain_native_title_will_do(self):
        self.assertEqual(igdb.original_title(
            {"alternative_names": [{"name": "Contra", "comment": "Japanese title"}]}), "Contra")

    def test_details_carry_it(self):
        details = igdb.game_details(
            {"id": 1, "name": "Castlevania III: Dracula's Curse", "alternative_names": self.ALTS}, "18")
        self.assertEqual(details["originaltitle"], "Akumajou Densetsu")

    def test_a_game_that_is_known_by_one_name_says_nothing(self):
        self.assertNotIn("originaltitle", igdb.game_details({"id": 1, "name": "Contra"}, "18"))


class VsSystemTest(unittest.TestCase):
    def test_a_vs_title_is_recognised(self):
        self.assertTrue(igdb.is_vs_system(request("Vs. Gradius")))
        self.assertTrue(igdb.is_vs_system(request("Vs. Ice Climber")))

    def test_an_ordinary_console_game_is_not(self):
        self.assertFalse(igdb.is_vs_system(request("Gradius")))
        self.assertFalse(igdb.is_vs_system(request("Contra")))

    def test_a_cabinet_tag_in_the_file_name_counts(self):
        req = Request({"title": "Castlevania", "platform": "nes",
                       "filename": "Vs. Castlevania (VS UniSystem).nes"},
                      {"provider_order": "igdb"})
        self.assertTrue(igdb.is_vs_system(req))

    def test_the_cabinet_is_what_gets_said(self):
        provider = Scripted([("where id = 1", [{"id": 1, "name": "Vs. Gradius", "game_type": 11}])])
        self.assertEqual(provider.details("1", request("Vs. Gradius"))["edition"], "Arcade")

    def test_an_ordinary_port_still_says_port(self):
        provider = Scripted([("where id = 1", [{"id": 1, "name": "Gradius", "game_type": 11}])])
        self.assertEqual(provider.details("1", request("Gradius"))["edition"], "Port")


class CompilationTest(unittest.TestCase):
    def test_a_compilation_is_a_game_in_the_library(self):
        # One file on disk, so the library has to be able to describe it
        self.assertTrue(igdb.is_the_game({"game_type": 3}))
        self.assertTrue(igdb.is_the_game({"game_type": 13}))

    def test_it_says_what_it_is(self):
        details = igdb.game_details({"id": 1, "name": "The Ezio Collection", "game_type": 3}, "130")
        self.assertEqual(details["edition"], "Compilation")

    def test_an_add_on_is_still_refused(self):
        self.assertFalse(igdb.is_the_game({"game_type": 1}))   # dlc
        self.assertFalse(igdb.is_the_game({"game_type": 2}))   # expansion


class AliasTest(unittest.TestCase):
    def test_a_name_the_search_misses_is_found_through_an_alias(self):
        provider = Scripted([])
        provider.aliases = {("18", namer.normalise("ブラックレインボウ")): ["4242"]}
        found = provider.find(request("ブラックレインボウ"))
        self.assertEqual([(c["id"], c["matchedby"]) for c in found], [("4242", "alias")])
        # Answered without asking IGDB at all
        self.assertEqual(provider.bodies, [])
