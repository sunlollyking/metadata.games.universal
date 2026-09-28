"""Every setting the add-on declares reaches the scraper."""
import os
import sys
import unittest
import xml.etree.ElementTree as ET

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ADDON_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, TESTS_DIR)
sys.path.insert(0, ADDON_DIR)
import kodistubs  # noqa: E402

kodistubs.install()

import scraper  # noqa: E402


def declared():
    root = ET.parse(os.path.join(ADDON_DIR, "resources", "settings.xml")).getroot()
    return {s.get("id"): s.findtext("default") for s in root.iter("setting")}


class SettingsTest(unittest.TestCase):
    def test_every_declared_setting_is_read(self):
        # settings() reads only the keys in DEFAULTS, so one missing there is
        # silently ignored whatever the player sets it to
        missing = sorted(set(declared()) - set(scraper.DEFAULTS))
        self.assertEqual(missing, [])

    def test_defaults_match_the_declared_ones(self):
        for key, default in declared().items():
            if key in scraper.DEFAULTS and default is not None:
                self.assertEqual(scraper._coerce(default, scraper.DEFAULTS[key]),
                                 scraper.DEFAULTS[key], key)


if __name__ == "__main__":
    unittest.main()
