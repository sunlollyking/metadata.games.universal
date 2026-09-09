"""A service that files several dumps under one game answers about the wrong one."""
from resources.lib.universal import names_another_game


def test_a_pirate_copy_is_not_the_game_it_was_made_from():
    assert names_another_game("Futbol Argentino 98 - Pasion de Multitudes",
                              "FIFA Soccer 95", "pirate")
    assert names_another_game("Some Bootleg", "The Original", "unlicensed")
    assert names_another_game("Some Reissue", "The Original", "aftermarket")


def test_a_licensed_dump_under_another_name_is_left_alone():
    # Regional and language naming differ constantly and mean nothing
    assert not names_another_game("Akumajou Densetsu", "Castlevania III", "licensed")
    assert not names_another_game("Probotector", "Contra", "")


def test_one_of_a_series_is_not_another_of_it():
    assert names_another_game("Echo Night 2", "Echo Night", "licensed")
    assert names_another_game("Echo Night", "Echo Night 2", "licensed")
    assert names_another_game("Street Fighter 2", "Street Fighter 3", "licensed")


def test_the_same_game_is_the_same_game():
    assert not names_another_game("FIFA Soccer 95", "FIFA Soccer 95", "pirate")
    assert not names_another_game("Sonic the Hedgehog", "Sonic The Hedgehog", "licensed")


def test_nothing_to_compare_decides_nothing():
    assert not names_another_game("", "FIFA Soccer 95", "pirate")
    assert not names_another_game("FIFA Soccer 95", "", "pirate")


def test_a_number_inside_a_name_is_not_a_series_number():
    # "2 in 1" collections and the like share no stem, so they do not trip it
    assert not names_another_game("Sonic 2 in 1", "Mega Games 6", "licensed")
