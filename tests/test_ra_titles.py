"""The names RetroAchievements puts on a set are not the names of games."""
from resources.lib.providers import retroachievements as ra


def test_set_kind_is_not_part_of_the_name():
    assert ra.set_title("~Hack~ Sonic Boom") == "Sonic Boom"
    assert ra.set_title("~Prototype~ Hoppin' Mad") == "Hoppin' Mad"
    assert ra.set_title("~Homebrew~ ~Demo~ Venetian Blinds") == "Venetian Blinds"
    assert ra.set_title("~Z~ Mario Bros. Special") == "Mario Bros. Special"


def test_an_ordinary_name_is_left_alone():
    assert ra.set_title("Super Mario Bros.") == "Super Mario Bros."
    assert ra.set_title("Ys: The Vanished Omens") == "Ys: The Vanished Omens"


def test_a_tilde_inside_a_name_survives():
    assert ra.set_title("Wow~ Fun") == "Wow~ Fun"


def test_the_non_game_marker_is_recognised():
    assert ra.is_not_a_game("ZZZ(notgame):#NONGAME")
    assert ra.is_not_a_game("zzz(notgame): AGS Aging Cartridge")
    assert not ra.is_not_a_game("Zanac")
    assert not ra.is_not_a_game("")


def test_a_non_game_is_never_offered_or_described():
    games = [{"ID": "1", "Title": "ZZZ(notgame):#NONGAME", "Hashes": ["abc"]}]
    assert [g for g in games if not ra.is_not_a_game(g["Title"])] == []


def test_a_hack_is_reachable_by_its_own_name_but_yields_to_the_plain_set():
    assert ra.name_score("Sonic the Hedgehog 2") == ra.NAME_SCORE
    assert ra.name_score("~Hack~ Sonic the Hedgehog 2") == ra.MARKED_NAME_SCORE
    assert ra.MARKED_NAME_SCORE < ra.NAME_SCORE
