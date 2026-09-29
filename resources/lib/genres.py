"""One name for each genre, whichever catalogue supplied it.

Catalogues spell the same genre several ways ("Role Playing Game", "RPG",
"Role-playing (RPG)"), nest it ("Sports - Golf", "Action » Shooter"), or join
several with commas that other code then splits mid-name. A library built from
more than one of them lists every spelling as its own genre, and a filter on
one finds a fraction of the games.
"""
import re
from typing import Iterable, List

# Keys are compared lowercased with spacing and punctuation removed
CANONICAL = {
    "action": "Action",
    "adventure": "Adventure",
    "actionadventure": "Action-Adventure",
    "actionadventuregame": "Action-Adventure",
    "platform": "Platform",
    "climbing": "Platform",
    "platformer": "Platform",
    "platformgame": "Platform",
    "platforming": "Platform",
    "2dplatforming": "Platform",
    "3dplatforming": "Platform",
    "25dplatforming": "Platform",
    "platformingsidescrolling": "Platform",
    "platforming3d": "Platform",
    "actionplatforming": "Platform",
    "platformrunjump": "Platform",
    "puzzleplatforming": "Platform",
    "cinematicplatforming": "Platform",
    "collectathon": "Platform",
    "metroidvania": "Metroidvania",
    "shooter": "Shooter",
    "firstpersonshooter": "First-Person Shooter",
    "thirdpersonshooter": "Third-Person Shooter",
    "shootemup": "Shoot 'em Up",
    "shmup": "Shoot 'em Up",
    "bullethell": "Shoot 'em Up",
    "spaceshooter": "Shoot 'em Up",
    "galleryshooter": "Shoot 'em Up",
    "twinstickshooter": "Shooter",
    "runandgun": "Run and Gun",
    "rungun": "Run and Gun",
    "runandgunshooter": "Run and Gun",
    "railshooter": "Rail Shooter",
    "shooterrail": "Rail Shooter",
    "lightgun": "Light Gun",
    "lightgunshooter": "Light Gun",
    "gun": "Light Gun",
    "tacticalshooting": "Shooter",
    "shootertopview": "Shooter",
    "beatemup": "Beat 'em Up",
    "sidescrollingbeatemup": "Beat 'em Up",
    "hackandslashbeatemup": "Beat 'em Up",
    "hackandslash": "Hack and Slash",
    "hackslash": "Hack and Slash",
    "fighting": "Fighting",
    "fighter": "Fighting",
    "2dfighting": "Fighting",
    "3dfighting": "Fighting",
    "arenafighting": "Fighting",
    "platformfighting": "Fighting",
    "racing": "Racing",
    "racingdriving": "Racing",
    "driving": "Racing",
    "arcaderacing": "Racing",
    "kartracing": "Racing",
    "racingsimulation": "Racing",
    "combatracing": "Vehicular Combat",
    "vehicularcombat": "Vehicular Combat",
    "vehiclecombat": "Vehicular Combat",
    "sports": "Sports",
    "sport": "Sports",
    "sportswithanimals": "Sports",
    "football": "Sports",
    "basketball": "Sports",
    "tennis": "Sports",
    "boxing": "Sports",
    "wrestling": "Sports",
    "extremesports": "Sports",
    "huntingandfishing": "Sports",
    "roleplayinggame": "Role-Playing (RPG)",
    "roleplayingrpg": "Role-Playing (RPG)",
    "roleplaying": "Role-Playing (RPG)",
    "rpg": "Role-Playing (RPG)",
    "turnbasedrpg": "Role-Playing (RPG)",
    "crpg": "Role-Playing (RPG)",
    "crpgwesternrpg": "Role-Playing (RPG)",
    "actionrpg": "Action RPG",
    "tacticalrpg": "Tactical RPG",
    "dungeoncrawl": "Dungeon Crawler",
    "dungeoncrawler": "Dungeon Crawler",
    "roguelike": "Roguelike",
    "strategy": "Strategy",
    "tactical": "Strategy",
    "tactics": "Strategy",
    "strategytactics": "Strategy",
    "turnbasedstrategy": "Turn-Based Strategy",
    "turnbasedstrategytbs": "Turn-Based Strategy",
    "realtimestrategy": "Real-Time Strategy",
    "realtimestrategyrts": "Real-Time Strategy",
    "4xexploreexpandexploitandexterminate": "4X",
    "4x": "4X",
    "grandstrategy": "Strategy",
    "artillery": "Strategy",
    "puzzle": "Puzzle",
    "thinking": "Puzzle",
    "logicpuzzle": "Puzzle",
    "jigsawpuzzle": "Puzzle",
    "slidingpuzzle": "Puzzle",
    "physicspuzzle": "Puzzle",
    "wordpuzzle": "Puzzle",
    "nonogram": "Puzzle",
    "sudoku": "Puzzle",
    "kakuro": "Puzzle",
    "sokoban": "Puzzle",
    "hiddenobject": "Puzzle",
    "tilematching": "Puzzle",
    "fallingblockpuzzle": "Puzzle",
    "marblepopper": "Puzzle",
    "mahjongsolitaire": "Puzzle",
    "brickbreakers": "Breakout",
    "breakout": "Breakout",
    "paddleandball3dglassesoptional": "Breakout",
    "maze": "Maze",
    "mazechase": "Maze",
    "actionlabyrinth": "Maze",
    "simulation": "Simulation",
    "simulator": "Simulation",
    "lifesimulation": "Simulation",
    "lifesimulationbusinessstrategy": "Simulation",
    "petsimulation": "Simulation",
    "cookingsimulation": "Simulation",
    "cookingsimulator": "Simulation",
    "cooking": "Simulation",
    "jobsimulation": "Simulation",
    "datingsimulation": "Simulation",
    "vehiclesimulation": "Simulation",
    "managementsimulation": "Management",
    "managementsim": "Management",
    "constructionandmanagementsimulation": "Management",
    "business": "Management",
    "constructing": "Management",
    "flightsimulation": "Flight Simulation",
    "flightsimulator": "Flight Simulation",
    "combatflightsimulation": "Flight Simulation",
    "combatflightsimulator": "Flight Simulation",
    "noncombatflightsimulation": "Flight Simulation",
    "spaceflightsimulation": "Flight Simulation",
    "sandbox": "Sandbox",
    "openworld": "Open World",
    "survival": "Survival",
    "survivalhorror": "Survival Horror",
    "stealth": "Stealth",
    "pointandclick": "Point-and-Click",
    "pointandclickadventure": "Point-and-Click",
    "textadventure": "Text Adventure",
    "visualnovel": "Visual Novel",
    "interactivemovie": "Interactive Movie",
    "fmv": "Interactive Movie",
    "quicktimeevents": "Interactive Movie",
    "interactivecomic": "Visual Novel",
    "interactivebook": "Visual Novel",
    "board": "Board Game",
    "boardgame": "Board Game",
    "asiaticboardgame": "Board Game",
    "chess": "Board Game",
    "cardboardgame": "Board Game",
    "card": "Card Game",
    "cardgame": "Card Game",
    "playingcards": "Card Game",
    "collectiblecardgame": "Card Game",
    "casino": "Casino",
    "gambling": "Casino",
    "poker": "Casino",
    "pachinko": "Casino",
    "casinoslotmachine": "Casino",
    "pinball": "Pinball",
    "quiz": "Quiz",
    "quiztrivia": "Quiz",
    "trivia": "Quiz",
    "gameshow": "Quiz",
    "music": "Music and Rhythm",
    "musicanddancing": "Music and Rhythm",
    "dancing": "Music and Rhythm",
    "rhythm": "Music and Rhythm",
    "party": "Party",
    "minigames": "Party",
    "casualgame": "Casual",
    "educational": "Educational",
    "education": "Educational",
    "colouringbook": "Educational",
    "colouringgame": "Educational",
    "kids": "Kids",
    "compilation": "Compilation",
    "adults": "Adult",
    "adult": "Adult",
    "erotic": "Adult",
    "arcade": "Arcade",
    "indie": "Indie",
    "sciencefiction": "Science Fiction",
    "fantasy": "Fantasy",
    "historical": "Historical",
    "warfare": "War",
    "comedy": "Comedy",
    "horror": "Horror",
    "psychologicalhorror": "Horror",
    "mystery": "Mystery",
    "thriller": "Thriller",
    "drama": "Drama",
    "romance": "Romance",
    "nonfiction": "Non-Fiction",
    "demo": "Demo",
    "utility": "Utility",
    "trainer": "Utility",
    "footballsoccer": "Sports",
    "soccer": "Sports",
    "golf": "Sports",
    "combat": "Action",
    "simonsays": "Party",
    "rockpaperscissors": "Party",
}

# Words that say nothing about the game, and pieces of names split mid-way
NOT_GENRES = {
    "", "other", "others", "various", "miscellaneous", "misc", "general", "unknown", "na",
    "data", "picture", "literature", "photography", "runner", "topdown", "realtime",
    "2d", "3d", "scrolling", "parlor", "issewingmachineagenre", "adobeaftereffects",
    "wehavemegamitenseiathome",
}

KNOWN = set(CANONICAL.values())

SPORTS = re.compile(r"^(extreme\s+)?sports?\b|^olympic", re.I)
SIMULATION = re.compile(r"\bsimulat(or|ion)$", re.I)
COMPILATION = re.compile(r"^multicart\b", re.I)
SUFFIX = re.compile(r"\s*\([^()]*\)$")
NESTED = re.compile(r"\s*(?:»|>)\s*")


def key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def canonical(name: str) -> str:
    """The genre's one name, the name as given when it is not known, or "" to drop it."""
    name = name.strip().strip("\"'")
    if not name:
        return ""
    # A name split at a comma inside its brackets: "Sports (Football" still
    # says Sports, "Soccer)" says nothing on its own
    if name.count("(") > name.count(")"):
        return canonical(name[:name.index("(")])
    if name.count(")") > name.count("("):
        return ""
    # "Action » Shooter » Shoot-'Em-Up » Horizontal": the most specific known level
    levels = [level for level in NESTED.split(name) if level]
    if len(levels) > 1:
        known = [found for found in map(canonical, levels) if found in KNOWN]
        return known[-1] if known else ""
    k = key(name)
    if k in NOT_GENRES or len(k) < 2:
        return ""
    if k in CANONICAL:
        return CANONICAL[k]
    if SPORTS.match(name):
        return "Sports"
    if SIMULATION.search(name):
        return "Simulation"
    if COMPILATION.match(name):
        return "Compilation"
    # "Action (Digging)": the genre, with a note on it
    bare = SUFFIX.sub("", name)
    if bare != name:
        found = canonical(bare)
        if found:
            return found
    return name


def split(text: str, separators: str = ",/") -> List[str]:
    """Split a list of genres on separators outside parentheses.

    "Platforming (Side-Scrolling, 2.5D), Action" is two genres, not three.
    """
    out, depth, current = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
        if ch in separators and depth == 0:
            out.append("".join(current))
            current = []
        else:
            current.append(ch)
    out.append("".join(current))
    return [part.strip() for part in out if part.strip()]


def normalise(genres: Iterable[str]) -> List[str]:
    """Each genre by its one name, junk dropped, duplicates removed, order kept."""
    out: List[str] = []
    for genre in genres:
        # Some catalogues hand over a whole path as one name, "Sports,
        # Traditional,Golf,Sim", of which only the known parts are genres
        parts = split(str(genre), ",")
        for part in parts:
            name = canonical(part)
            if name and (len(parts) == 1 or name in KNOWN) and name not in out:
                out.append(name)
    return out
