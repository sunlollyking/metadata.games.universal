"""Arcade sets identified by the CRCs inside the zip, against small romset lists."""
import json
import os
import shutil
import tempfile
import unittest
import zipfile

from resources.lib.providers import Request
from resources.lib.providers import arcade, launchbox
from resources.lib.universal import Universal

FBNEO = """<?xml version="1.0"?>
<datafile>
  <game name="neogeo" isbios="yes"><description>Neo Geo</description>
    <rom name="sp-s2.sp1" size="131072" crc="9036d879"/></game>
  <game name="aodk" romof="neogeo"><description>Aggressors of Dark Kombat / Tsuukai GANGAN Koushinkyoku (ADM-008 ~ ADH-008)</description>
    <year>1994</year><manufacturer>ADK / SNK</manufacturer>
    <rom name="074-p1.p1" size="2097152" crc="62369553"/>
    <rom name="074-c1.c1" size="2097152" crc="a0b39344"/>
    <rom name="sp-s2.sp1" merge="sp-s2.sp1" size="131072" crc="9036d879"/></game>
  <game name="kof95" romof="neogeo"><description>The King of Fighters '95 (NGM-084)</description>
    <year>1995</year><manufacturer>SNK</manufacturer>
    <rom name="084-p1.p1" size="2097152" crc="2cba2716"/>
    <rom name="084-c1.c1" size="4194304" crc="fe087e32"/></game>
  <game name="kof95h" cloneof="kof95" romof="kof95"><description>The King of Fighters '95 (NGH-084)</description>
    <year>1995</year><manufacturer>SNK</manufacturer>
    <rom name="084-pg1.p1" size="2097152" crc="5e54cf95"/>
    <rom name="084-c1.c1" merge="084-c1.c1" size="4194304" crc="fe087e32"/></game>
  <game name="kof96bl" cloneof="kof95" romof="kof95"><description>The King of Fighters '95 (bootleg)</description>
    <rom name="bl-p1.p1" size="2097152" crc="11111111"/>
    <rom name="084-c1.c1" merge="084-c1.c1" size="4194304" crc="fe087e32"/></game>
  <game name="kof95pl" cloneof="kof95" romof="kof95"><description>King of Fighters Plus (hack)</description>
    <rom name="pl-p1.p1" size="2097152" crc="55555555"/>
    <rom name="084-c1.c1" merge="084-c1.c1" size="4194304" crc="fe087e32"/></game>
  <game name="kof95rv" cloneof="kof95" romof="kof95"><description>Kings Revenge (NGM-085)</description>
    <rom name="rv-p1.p1" size="2097152" crc="33333333"/>
    <rom name="084-c1.c1" merge="084-c1.c1" size="4194304" crc="fe087e32"/></game>
  <game name="slots"><description>Lucky Slots (Japan)</description>
    <rom name="s.bin" size="1024" crc="22222222"/></game>
</datafile>
"""

# The same Aggressors set under another emulator's name for it
MAME2003 = """<?xml version="1.0"?>
<mame>
  <game name="aodkx" sourcefile="neogeo.c"><description>Aggressors of Dark Kombat</description>
    <year>1994</year><manufacturer>ADK</manufacturer>
    <rom name="074-p1.p1" size="2097152" crc="62369553"/>
    <rom name="074-c1.c1" size="2097152" crc="a0b39344"/>
    <rom name="sp-s2.sp1" merge="sp-s2.sp1" size="131072" crc="9036d879"/>
    <input players="2"/></game>
</mame>
"""

DATS = {"fbneo": FBNEO, "mame2003plus": MAME2003}

# Current MAME's own list: machines no emulator here has, and Aggressors again
# under yet another name, which the emulators' lists must win
MAME = """<?xml version="1.0"?>
<mame build="0.289">
  <machine name="aodkm" sourcefile="neogeo/neogeo.cpp"><description>Aggressors of Dark Kombat (MAME)</description>
    <rom name="074-p1.p1" size="2097152" crc="62369553"/>
    <rom name="074-c1.c1" size="2097152" crc="a0b39344"/>
    <input players="2" coins="2"/></machine>
  <machine name="jak_prhp" sourcefile="tvgames/generalplus_gpl32612.cpp">
    <description>Power Rangers Super Megaforce Hero Portal</description>
    <year>200?</year><manufacturer>JAKKS Pacific Inc</manufacturer>
    <rom name="prhp.bin" size="8388608" crc="aaaa0001"/><input players="1"/></machine>
  <machine name="hexaprs" sourcefile="misc/yuvomz80.cpp"><description>Hexa President (YM2610 set)</description>
    <year>2000</year><manufacturer>Yuvo</manufacturer>
    <rom name="hx.u1" size="1" crc="aaaa0002"/><input players="1" coins="2"/></machine>
  <machine name="cp31" sourcefile="devices/bus/vme/cp31.cpp" isdevice="yes" runnable="no">
    <description>Besta CP31 CPU board</description><rom name="cp31.bin" size="1" crc="aaaa0003"/></machine>
  <machine name="mysys" sourcefile="sega/mysys.cpp"><description>My System</description>
    <rom name="sys.bin" size="1" crc="aaaa0004"/><softwarelist name="mysys"/>
    <input players="2" coins="1"/></machine>
  <machine name="j_ewna" sourcefile="jpm/jpmsru.cpp" ismechanical="yes">
    <description>Each Way Nudger (JPM) (SRU)</description>
    <rom name="ew.bin" size="1" crc="aaaa0005"/><input players="1" coins="3"/></machine>
  <machine name="acheart" sourcefile="sega/naomi.cpp"><description>Arcana Heart</description>
    <rom name="ah1.ic1" size="4194304" crc="abcdef01"/>
    <rom name="ah1.ic2" size="4194304" crc="abcdef02"/><input players="2" coins="2"/></machine>
</mame>
"""

AODK = [["074-p1.p1", 2097152, "62369553"], ["074-c1.c1", 2097152, "a0b39344"]]


def request(members=None, filename="aggressorsofdarkkombat.zip", **extra):
    query = {"filename": filename, "title": "aggressorsofdarkkombat",
             "platformids": json.dumps({"launchbox": "SNK Neo Geo"})}
    if members is not None:
        query["members"] = json.dumps(members)
    query.update(extra)
    return Request(query, {"provider_order": "launchbox"})


def launchbox_zip(path):
    metadata = """<?xml version="1.0"?><LaunchBox>
      <Game><Name>Aggressors of Dark Kombat</Name><DatabaseID>77</DatabaseID>
        <Platform>Arcade</Platform><Overview>A brawler.</Overview><Genres>Fighting</Genres></Game>
    </LaunchBox>"""
    mame = """<?xml version="1.0"?><LaunchBox>
      <MameFile><FileName>aodk</FileName><Name>Aggressors of Dark Kombat</Name>
        <Genre>Fighter / Versus</Genre><Source>neogeo/neogeo.cpp</Source></MameFile>
      <MameFile><FileName>slots</FileName><Name>Lucky Slots</Name><IsCasino>true</IsCasino></MameFile>
      <MameFile><FileName>kof96bl</FileName><Name>KOF bootleg</Name><IsBootleg>true</IsBootleg></MameFile>
      <MameFile><FileName>acheart</FileName><Name>Arcana Heart</Name><Year>2005</Year>
        <Publisher>Examu</Publisher><Genre>Fighter / 2D</Genre><Source>sega/naomi.cpp</Source></MameFile>
      <MameFile><FileName>ac1club</FileName><Name>Club Money</Name><IsMechanical>true</IsMechanical>
        <IsCasino>true</IsCasino></MameFile>
      <MameFile><FileName>3cardpk</FileName><Name>3 Cards Poker</Name><Genre>Gambling / Poker</Genre></MameFile>
      <MameFile><FileName>22vp931</FileName><Name>Philips 22VP931</Name><Genre>System / Device</Genre></MameFile>
    </LaunchBox>"""
    files = """<?xml version="1.0"?><LaunchBox>
      <File><Platform>Arcade</Platform><FileName>aodk</FileName>
        <GameName>Aggressors of Dark Kombat</GameName></File>
    </LaunchBox>"""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Metadata.xml", metadata)
        z.writestr("Mame.xml", mame)
        z.writestr("Files.xml", files)


class ArcadeTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.logged = []
        self.fetched = []
        self.mame_available = True
        log = lambda message, notable: self.logged.append(message)  # noqa: E731

        def fetch(url, target):
            self.fetched.append(url)
            if url == arcade.MAME_RELEASE:
                if not self.mame_available:
                    raise OSError("rate limited")
                with zipfile.ZipFile(target, "w") as z:
                    z.writestr("mame0289.xml", MAME)
                return
            for name, dat in DATS.items():
                if name in url.replace("-", "").replace("%20", "").lower() or (
                        name == "mame2003plus" and "mame2003-plus" in url):
                    with open(target, "w") as f:
                        f.write(dat)
                    return
            raise OSError("no fixture for " + url)

        self.launchbox = launchbox.LaunchBoxProvider(log, self.dir)
        self.launchbox.index._download = lambda target: launchbox_zip(target)
        self.launchbox.prefetch([])
        self.fetch = fetch
        self.log = log
        self.provider = self.new_provider()

    def new_provider(self):
        """A provider as a fresh scraper run makes one"""
        return arcade.ArcadeProvider(
            self.log, self.dir, installed=lambda addon: addon in (
                "game.libretro.fbneo", "game.libretro.mame2003_plus"), fetch=self.fetch)

    def tearDown(self):
        self.provider.close()
        self.launchbox.index.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_renamed_zip_is_known_by_its_contents(self):
        found = self.provider.find(request(AODK))
        self.assertEqual(found[0]["id"], "aodk")
        self.assertEqual(found[0]["title"], "Aggressors of Dark Kombat")
        self.assertEqual(found[0]["matchedby"], "hash")

    def test_every_emulator_holding_the_set_is_named_with_its_own_name_for_it(self):
        details = self.provider.details("aodk", request(AODK))
        self.assertEqual(details["emulators"], [
            {"addon": "game.libretro.fbneo", "romset": "aodk", "requires": ["neogeo"]},
            {"addon": "game.libretro.mame2003_plus", "romset": "aodkx", "requires": []}])
        self.assertEqual(details["releases"][0]["romset"], "aodk")
        self.assertEqual(details["originaltitle"], "Tsuukai GANGAN Koushinkyoku")
        self.assertEqual(details["year"], 1994)

    def test_only_installed_emulators_lists_are_fetched(self):
        self.provider.identify(request(AODK))
        self.assertEqual(sorted(self.provider.index.sources()), ["fbneo", "mame", "mame2003plus"])

    def test_a_set_only_mame_knows_is_named_from_its_list(self):
        portal = [["prhp.bin", 8388608, "aaaa0001"]]
        found = self.provider.find(request(portal, filename="jak_prhp.zip"))
        self.assertEqual([(c["id"], c["title"], c["matchedby"]) for c in found],
                         [("jak_prhp", "Power Rangers Super Megaforce Hero Portal", "hash")])
        details = self.provider.details("jak_prhp", request(portal, filename="jak_prhp.zip"))
        self.assertEqual((details["publishers"], details["emulators"], details["category"]),
                         (["JAKKS Pacific Inc"], [], "nongame"))

    def test_a_set_mame_renamed_is_still_known_by_its_chips(self):
        board = [["cp31.bin", 1, "aaaa0003"]]
        found = self.provider.find(request(board, filename="besta88.zip"))
        self.assertEqual([(c["id"], c["title"]) for c in found], [("cp31", "Besta CP31 CPU board")])

    def test_mames_list_comes_after_the_emulators_and_launchbox(self):
        self.assertEqual(self.provider.find(request(AODK))[0]["id"], "aodk")
        newer = [["ah1.ic1", 4194304, "abcdef01"], ["ah1.ic2", 4194304, "abcdef02"]]
        self.assertEqual([c["matchedby"] for c in self.provider.find(request(newer, filename="acheart.zip"))],
                         ["filename"])

    def test_what_mame_says_of_a_machine_files_it(self):
        def category(romset, crc):
            chips = request([["x", 1, crc]], filename=romset + ".zip")
            return self.provider.details(romset, chips)["category"]
        self.assertEqual(category("hexaprs", "aaaa0002"), "retail")
        self.assertEqual(category("cp31", "aaaa0003"), "bios")
        self.assertEqual(category("mysys", "aaaa0004"), "nongame")
        self.assertEqual(category("j_ewna", "aaaa0005"), "nongame")

    def test_mames_list_failing_does_not_make_every_scrape_rebuild(self):
        self.provider.close()
        shutil.rmtree(os.path.join(self.dir, "arcade"), ignore_errors=True)
        self.mame_available = False
        self.provider = self.new_provider()
        self.assertEqual(self.provider.find(request(AODK))[0]["id"], "aodk")
        self.assertEqual(sorted(self.provider.index.sources()), ["fbneo", "mame2003plus"])
        fetches = len(self.fetched)
        self.provider.close()
        self.provider = self.new_provider()
        self.provider.find(request(AODK))
        self.assertEqual(len(self.fetched), fetches)

    def test_a_clone_is_a_release_of_its_parent(self):
        clone = [["084-pg1.p1", 2097152, "5e54cf95"], ["084-c1.c1", 4194304, "fe087e32"]]
        found = self.provider.find(request(clone, filename="kof95h.zip"))
        self.assertEqual(found[0]["id"], "kof95")
        details = self.provider.details("kof95", request(clone, filename="kof95h.zip"))
        self.assertEqual(details["title"], "The King of Fighters '95")
        self.assertEqual(details["releases"][0]["romset"], "kof95h")
        self.assertEqual(details["emulators"][0]["requires"], ["kof95", "neogeo"])
        self.assertEqual(details["releases"][0]["title"], "The King of Fighters '95 (NGH-084)")

    def test_a_clone_with_a_name_of_its_own_is_its_own_game(self):
        sequel = [["rv-p1.p1", 2097152, "33333333"], ["084-c1.c1", 4194304, "fe087e32"]]
        found = self.provider.find(request(sequel, filename="kof95rv.zip"))
        self.assertEqual((found[0]["id"], found[0]["title"]), ("kof95rv", "Kings Revenge"))

    def test_a_hack_named_otherwise_is_still_a_version_of_its_game(self):
        hack = [["pl-p1.p1", 2097152, "55555555"], ["084-c1.c1", 4194304, "fe087e32"]]
        found = self.provider.find(request(hack, filename="kof95pl.zip"))
        self.assertEqual(found[0]["id"], "kof95")
        details = self.provider.details("kof95", request(hack, filename="kof95pl.zip"))
        self.assertEqual(details["title"], "The King of Fighters '95")
        self.assertEqual(details["category"], "retail")
        self.assertEqual(details["releases"][0]["edition"], "Mod")
        self.assertEqual(details["releases"][0]["title"], "King of Fighters Plus (hack)")

    def test_a_merged_set_is_its_parent_whatever_clones_it_carries(self):
        merged = [["084-p1.p1", 2097152, "2cba2716"], ["084-c1.c1", 4194304, "fe087e32"],
                  ["084-pg1.p1", 2097152, "5e54cf95"], ["rv-p1.p1", 2097152, "33333333"],
                  ["newer-clone.p1", 2097152, "44444444"]]
        found = self.provider.find(request(merged, filename="kof95.zip"))
        self.assertEqual((found[0]["id"], found[0]["subtitle"]),
                         ("kof95", "The King of Fighters '95 (NGM-084)"))
        details = self.provider.details("kof95", request(merged, filename="kof95.zip"))
        self.assertEqual(details["emulators"], [
            {"addon": "game.libretro.fbneo", "romset": "kof95", "requires": ["neogeo"]}])

    def test_a_partial_set_is_named_but_no_emulator_is_offered(self):
        partial = [["074-p1.p1", 2097152, "62369553"], ["074-c1.c1", 2097152, "a0b39344"],
                   ["extra.bin", 16, "deadbeef"]]
        details = self.provider.details("aodk", request(partial))
        self.assertEqual(details["title"], "Aggressors of Dark Kombat")
        self.assertEqual(details["emulators"], [])

    def test_too_little_in_common_is_no_match(self):
        self.assertEqual(self.provider.find(request([["x", 1, "62369553"], ["y", 1, "00000001"],
                                                     ["z", 1, "00000002"]], filename="x.zip"))[0]
                         ["id"], "aodk")
        stray = [["a", 1, "0000000a"], ["b", 1, "0000000b"]]
        self.assertEqual(self.provider.find(request(stray, filename="stray.zip")), [])

    def test_a_set_no_emulator_lists_is_named_from_launchbox(self):
        newer = [["ah1.ic1", 4194304, "abcdef01"], ["ah1.ic2", 4194304, "abcdef02"]]
        found = self.provider.find(request(newer, filename="acheart.zip"))
        self.assertEqual([(c["id"], c["title"], c["matchedby"]) for c in found],
                         [("acheart", "Arcana Heart", "filename")])
        details = self.provider.details("acheart", request(newer, filename="acheart.zip"))
        self.assertEqual((details["year"], details["genres"], details["category"], details["emulators"]),
                         (2005, ["Fighter"], "retail", []))
        self.assertEqual(details["tags"], ["Sega Naomi"])

    def test_a_set_finds_libretros_pictures_by_mames_name_for_it(self):
        held = {"Named_Boxarts": {"Power Rangers Super Megaforce Hero Portal", "Arcana Heart"},
                "Named_Snaps": {"Arcana Heart"}, "Named_Titles": set()}
        provider = arcade.ArcadeProvider(self.log, self.dir, installed=lambda addon: True,
                                         fetch=self.fetch, thumbnails=lambda: held)
        self.addCleanup(provider.close)
        portal = [["prhp.bin", 8388608, "aaaa0001"]]
        art = provider.details("jak_prhp", request(portal, filename="jak_prhp.zip"))["art"]
        self.assertEqual(art, {"boxfront": [{"url": "https://raw.githubusercontent.com/libretro-thumbnails/"
                                                    "MAME/master/Named_Boxarts/Power%20Rangers%20Super%20"
                                                    "Megaforce%20Hero%20Portal.png"}]})
        # A set named from LaunchBox's list is found the same way
        newer = [["ah1.ic1", 4194304, "abcdef01"], ["ah1.ic2", 4194304, "abcdef02"]]
        art = provider.details("acheart", request(newer, filename="acheart.zip"))["art"]
        self.assertEqual(sorted(art), ["boxfront", "screenshot"])

    def test_a_set_libretro_has_no_pictures_of_gets_none(self):
        provider = arcade.ArcadeProvider(self.log, self.dir, installed=lambda addon: True,
                                         fetch=self.fetch, thumbnails=lambda: {"Named_Boxarts": set()})
        self.addCleanup(provider.close)
        portal = [["prhp.bin", 8388608, "aaaa0001"]]
        self.assertNotIn("art", provider.details("jak_prhp", request(portal, filename="jak_prhp.zip")))

    def test_a_fruit_machine_or_a_device_is_not_filed_as_a_game(self):
        chips = [["a", 1, "abcdef03"], ["b", 1, "abcdef04"]]
        self.assertEqual(self.provider.details("ac1club", request(chips, filename="ac1club.zip"))
                         ["category"], "nongame")
        self.assertEqual(self.provider.details("3cardpk", request(chips, filename="3cardpk.zip"))
                         ["category"], "nongame")
        self.assertEqual(self.provider.details("22vp931", request(chips, filename="22vp931.zip"))
                         ["category"], "bios")

    def test_a_one_chip_zip_on_the_arcade_platform_is_a_set(self):
        arcade_platform = json.dumps({"launchbox": "arcade"})
        single = request(filename="slots.zip", crc32="22222222", platformids=arcade_platform)
        self.assertEqual([c["id"] for c in self.provider.find(single)], ["slots"])
        elsewhere = request(filename="slots.zip", crc32="22222222")
        self.assertEqual(self.provider.find(elsewhere), [])

    def test_no_members_asks_nothing(self):
        self.assertEqual(self.provider.find(request()), [])
        self.assertFalse(os.path.exists(self.provider.index.path))

    def test_the_bios_is_not_a_game(self):
        bios = [["sp-s2.sp1", 131072, "9036d879"]]
        details = self.provider.details("neogeo", request(bios, filename="neogeo.zip"))
        self.assertEqual(details["category"], "bios")

    def test_a_set_named_as_a_bios_is_one(self):
        for description in ("ST-V Bios", "MegaTech - Bios", "PGM (Polygame Master) System BIOS"):
            self.assertEqual(arcade.ArcadeProvider._category(description, False, None), "bios")
        self.assertEqual(arcade.ArcadeProvider._category("Bioship Paladin", False, None), "retail")

    def test_a_bootleg_is_a_pirate_version_of_its_game_and_a_fruit_machine_no_game(self):
        bootleg = [["bl-p1.p1", 2097152, "11111111"], ["084-c1.c1", 4194304, "fe087e32"]]
        details = self.provider.details("kof95", request(bootleg))
        self.assertEqual(details["category"], "retail")
        self.assertEqual(details["releases"][0]["licence"], "pirate")
        self.assertEqual(details["releases"][0]["romset"], "kof96bl")
        slots = [["s.bin", 1024, "22222222"]]
        self.assertEqual(self.provider.details("slots", request(slots))["category"], "nongame")

    def test_the_board_and_genre_come_from_launchbox(self):
        details = self.provider.details("aodk", request(AODK))
        self.assertIn("Neo Geo MVS", details["tags"])
        self.assertEqual(details["genres"], ["Fighter"])

    def test_launchbox_finds_the_game_by_its_romset(self):
        found = self.launchbox.find(request(romset="aodk"))
        self.assertEqual([(c["id"], c["matchedby"]) for c in found], [("77", "serial")])

    def test_the_universal_scraper_asks_arcade_first_and_launchbox_by_romset(self):
        engine = Universal([self.launchbox, self.provider], lambda m, n: None, self.dir)
        found = engine.find(request(AODK))
        self.assertEqual(found[0]["id"], "arcade:aodk")
        details = engine.details("arcade:aodk", request(AODK))
        self.assertEqual(details["overview"], "A brawler.")
        self.assertEqual(details["uniqueids"], {"arcade": "aodk", "launchbox": "77"})


class TitleTest(unittest.TestCase):
    def test_clean_title(self):
        self.assertEqual(arcade.clean_title("Street Fighter II: The World Warrior (World 910522)"),
                         ("Street Fighter II: The World Warrior", ""))
        self.assertEqual(arcade.clean_title("Blue's Journey / Raguy (ALM-001 ~ ALH-001)"),
                         ("Blue's Journey", "Raguy"))

    def test_regions(self):
        self.assertEqual(arcade.regions_of("Street Fighter II (USA 910522)"), ["USA"])
        self.assertEqual(arcade.regions_of("Final Fight (World, set 1)"), ["World"])


if __name__ == "__main__":
    unittest.main()
