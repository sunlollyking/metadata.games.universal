"""A source that asks not to be called stays uncalled after the scrape ends.

Each scrape runs as its own process, so a flag on the provider object lasts a
single game. Before this was written down, a source that answered 429 on the
first game of a scan was asked, refused and logged again for every game after
it -- a full network round trip each time, and a log line saying it would not
ask again.
"""
import os
import sys
import tempfile
import time
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, ADDON_DIR)

from resources.lib.providers import OnlineProvider  # noqa: E402


class Refusable(OnlineProvider):
    name = "refusable"
    folder = "refusable"

    def __init__(self, cache_dir, said):
        super().__init__(lambda message, error=False: said.append(message), cache_dir)


class RefusalOutlivesTheProcess(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.said = []

    def test_a_fresh_provider_still_knows_it_was_refused(self):
        first = Refusable(self.dir, self.said)
        self.assertFalse(first.exhausted)
        first.stop_asking("turning requests away")
        self.assertTrue(first.exhausted)

        # A new object stands in for the next scrape, which is a new process
        second = Refusable(self.dir, self.said)
        self.assertTrue(second.exhausted)

    def test_it_is_said_once_however_many_scrapes_follow(self):
        Refusable(self.dir, self.said).stop_asking("turning requests away")
        for _ in range(5):
            Refusable(self.dir, self.said).stop_asking("turning requests away")
        self.assertEqual(self.said, ["turning requests away"])

    def test_the_refusal_lapses_so_a_rate_limit_is_not_permanent(self):
        provider = Refusable(self.dir, self.said)
        provider.stop_asking("turning requests away", days=-1)  # already elapsed
        self.assertFalse(Refusable(self.dir, self.said).exhausted)

    def test_a_spent_allowance_is_held_longer_than_a_rate_limit(self):
        provider = Refusable(self.dir, self.said)
        provider.stop_asking("allowance used up", provider.ALLOWANCE_DAYS)
        held = provider._refusal["until"] - time.time()
        self.assertGreater(held, Refusable.REFUSAL_DAYS * 86400)

    def test_without_a_cache_folder_it_still_refuses_within_the_scrape(self):
        provider = Refusable("", self.said)
        provider.stop_asking("turning requests away")
        self.assertTrue(provider.exhausted)


if __name__ == "__main__":
    unittest.main()
