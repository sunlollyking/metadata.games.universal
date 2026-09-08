# metadata.games.universal

A game metadata scraper for Kodi that treats eight catalogues as one.

It identifies a ROM or disc image by checksum, serial or exact name, then
gathers the details and artwork from every source that recognises it. No single
catalogue covers a whole shelf: libretro knows the dumps, RetroAchievements
knows the hashes, IGDB writes the best prose, ScreenScraper has the deepest
art, and LaunchBox fills the gaps the rest leave on home computers. Asking all
of them and merging the answers gets further than picking one.

## How it decides

Sources are consulted in the order you set. The first to recognise a file wins
the identity; the rest fill in whatever it left empty, field by field, so a box
front from one catalogue and a description from another end up on the same
game.

Identification is exact by design. A checksum or serial match is trusted
outright; a name match must be exact after normalisation. Nothing is matched
approximately, because a confidently wrong game is worse than no game.

## Sources

| Source | Needs | Identifies by | Notes |
|---|---|---|---|
| libretro-database | nothing | hash, serial, name | Offline. One file per platform, refreshed by age |
| RetroAchievements | account name and API key | RetroAchievements hash, name | Also reports how far you have got in a game |
| Wikidata | nothing | name | Pictures of the machines themselves |
| IGDB | free client id and secret | name | The fullest descriptions and release data |
| ScreenScraper | account and dev credentials | hash, serial, name | The most artwork, and the most kinds of it |
| TheGamesDB | free API key | hash, name | A thousand lookups a month; budgeted, see below |
| REG-Vault | nothing | name | Box art and fanart. Single games only, not scans |
| LaunchBox | nothing | name | One bulk download, then answered offline |

Only libretro, Wikidata, REG-Vault and LaunchBox work without credentials. A
source whose keys are missing is skipped, and says so once per scan rather than
silently doing nothing.

REG-Vault and TheGamesDB ask not to be scraped in bulk, so a folder scan leaves
them out and a game you refresh yourself still uses them.

## Two sources that work differently

**LaunchBox** publishes its whole database as a single zip, regenerated daily,
and has no per-game API at all. The add-on downloads it about once a month and
parses it straight out of the archive into a local SQLite index — roughly ten
seconds for 188,000 games and 1.3 million pictures. Every game after that costs
two indexed lookups and nothing on the network, which makes it the cheapest
source here to run across a whole library. Its catalogue is written by its
users, so a scan, a reconstruction and a piece of fan art are all offered for
the same game; real scans are preferred where a game has one.

**TheGamesDB** allows a public key a thousand requests a month and a game costs
two or three of them. A scan spends the share you set and then leaves it alone
until next month, while a game you refresh yourself is always looked up. When a
source asks not to be called, the refusal is written down rather than held in
memory, because every scrape is its own process — otherwise the source would be
asked, refused and logged again for every remaining game in the scan.

## Settings

Provider order, the cache lifetime and each source's credentials live in the
add-on's settings. Leaving a name out of the provider order turns that source
off. Credentials are never written to the log.

## Development

    python3 -m pytest tests/

The suite runs offline against recorded fixtures; no key is needed and nothing
touches the network.

## Licence

GPL-2.0-or-later. See [LICENSE](LICENSE).
