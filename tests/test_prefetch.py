"""A batch warms up the sources that can answer many titles at once."""
import os
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, ADDON_DIR)

from resources.lib import universal  # noqa: E402
from resources.lib.providers import Provider, Request  # noqa: E402


def no_log(message, error=False):
    pass


class Warmable(Provider):
    name = "warmable"

    def __init__(self):
        super().__init__(no_log)
        self.warmed = None
        self.finds = 0

    def prefetch(self, requests):
        self.warmed = [r.title() for r in requests]

    def find(self, request):
        self.finds += 1
        return []


class Broken(Provider):
    name = "broken"

    def __init__(self):
        super().__init__(no_log)

    def prefetch(self, requests):
        raise RuntimeError("no")


def requests(titles, bulk=True, order="warmable,broken"):
    return [Request({"title": t}, {"provider_order": order}, bulk) for t in titles]


class PrefetchTest(unittest.TestCase):
    def test_every_title_in_the_batch_is_offered_at_once(self):
        provider = Warmable()
        universal.Universal([provider], no_log).prefetch(requests(["A", "B", "C"]))
        self.assertEqual(provider.warmed, ["A", "B", "C"])
        self.assertEqual(provider.finds, 0)

    def test_a_warm_up_that_fails_does_not_stop_the_batch(self):
        provider = Warmable()
        engine = universal.Universal([provider, Broken()], no_log)
        engine.prefetch(requests(["A"]))
        self.assertEqual(provider.warmed, ["A"])

    def test_nothing_to_do_asks_nobody(self):
        provider = Warmable()
        universal.Universal([provider], no_log).prefetch([])
        self.assertIsNone(provider.warmed)


if __name__ == "__main__":
    unittest.main()
