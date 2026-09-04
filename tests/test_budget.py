"""A capped source spends a share of its month and then steps aside."""
import os
import sys
import tempfile
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, ADDON_DIR)

from resources.lib import universal  # noqa: E402
from resources.lib.budget import Budget  # noqa: E402
from resources.lib.providers import Provider, Request  # noqa: E402


def no_log(message, error=False):
    pass


class Capped(Provider):
    name = "capped"
    bulk_safe = False
    monthly_budget = 2
    budget_setting = "capped_monthly_games"

    def __init__(self):
        super().__init__(no_log)
        self.asked = 0

    def find(self, request):
        self.asked += 1
        return [{"id": "1", "title": "T", "score": 1.0, "matchedby": "hash"}]


class Free(Provider):
    name = "free"

    def __init__(self):
        super().__init__(no_log)

    def find(self, request):
        return []


def request(bulk, folder, **settings):
    conf = {"provider_order": "free,capped"}
    conf.update(settings)
    return Request({"title": "Game"}, conf, bulk)


class BudgetTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_a_scan_spends_the_share_and_then_leaves_the_source_alone(self):
        capped = Capped()
        engine = universal.Universal([Free(), capped], no_log, self.dir)
        for _ in range(4):
            engine.find(request(True, self.dir))
        self.assertEqual(capped.asked, 2)

    def test_one_game_a_person_asked_about_is_always_looked_up(self):
        capped = Capped()
        engine = universal.Universal([Free(), capped], no_log, self.dir)
        for _ in range(4):
            engine.find(request(False, self.dir))
        self.assertEqual(capped.asked, 4)

    def test_a_share_of_none_keeps_the_source_out_of_scans(self):
        capped = Capped()
        engine = universal.Universal([Free(), capped], no_log, self.dir)
        engine.find(request(True, self.dir, capped_monthly_games=0))
        self.assertEqual(capped.asked, 0)

    def test_the_count_survives_a_new_process(self):
        Budget(self.dir, "capped", 2).spend()
        self.assertEqual(Budget(self.dir, "capped", 2).left(), 1)


if __name__ == "__main__":
    unittest.main()
