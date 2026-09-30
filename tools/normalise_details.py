#!/usr/bin/env python3
"""Give every game in a Kodi games database its age ratings and companies by their one name.

Age ratings get the scraper's rules, and the IGDB mix-up that stored PEGI
letters and ESRB numbers is undone. Publishers and developers are split,
lose their company form and regional arm, and each company is then spelled
the way most of the library already spells it. Companies no game uses any
more are removed.

    normalise_details.py DATABASE [--apply]

DATABASE is Kodi's games database (userdata/Database/Games*.db); stop Kodi or
back it up first. Without --apply it only counts.
"""
import collections
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources", "lib"))
import ageratings  # noqa: E402
import companies  # noqa: E402

LIST_SEPARATOR = " / "
ROLES = (("publishers", "publisher_link"), ("developers", "developer_link"))


def ratings(db, apply):
    changed = 0
    games = collections.defaultdict(list)
    for game, board, value, descriptors in db.execute(
            "select media_id, board, value, coalesce(descriptors, '') from agerating "
            "where media_type = 'game' order by agerating_id"):
        games[game].append({"board": board, "value": value, "descriptors": descriptors})
    for game, old in games.items():
        new = ageratings.repair_igdb(old)
        if new == old:
            continue
        changed += 1
        if apply:
            db.execute("delete from agerating where media_type = 'game' and media_id = ?", (game,))
            db.executemany(
                "insert into agerating (media_id, media_type, board, value, descriptors) "
                "values (?, 'game', ?, ?, ?)",
                [(game, r["board"], r["value"], r["descriptors"]) for r in new])
    return changed


def company_lists(db):
    """Every game's normalised publishers and developers, and the spelling each company gets."""
    lists = {}
    spellings = collections.defaultdict(collections.Counter)
    for game, publishers, developers in db.execute(
            "select idGame, coalesce(publishers, ''), coalesce(developers, '') from game"):
        entry = {}
        for (column, _), text in zip(ROLES, (publishers, developers)):
            names = companies.normalise(n for n in text.split(LIST_SEPARATOR) if n)
            entry[column] = (text, names)
            for name in names:
                spellings[companies.key(name)][name] += 1
        lists[game] = entry
    spelling = {key: counts.most_common(1)[0][0] for key, counts in spellings.items()}
    return lists, spelling


def companies_pass(db, apply):
    lists, spelling = company_lists(db)
    ids = {name: cid for cid, name in db.execute("select idCompany, name from company")}
    changed = 0
    for game, entry in lists.items():
        for column, link in ROLES:
            text, names = entry[column]
            names = list(dict.fromkeys(spelling[companies.key(n)] for n in names))
            linked = [name for (name,) in db.execute(
                f"select c.name from company c join {link} l on l.idCompany = c.idCompany "
                "where l.idGame = ?", (game,))]
            if LIST_SEPARATOR.join(names) == text and set(linked) == set(names):
                continue
            changed += 1
            if not apply:
                continue
            db.execute(f"update game set {column} = ? where idGame = ?",
                       (LIST_SEPARATOR.join(names), game))
            db.execute(f"delete from {link} where idGame = ?", (game,))
            for name in names:
                if name not in ids:
                    ids[name] = db.execute("insert into company (name) values (?)", (name,)).lastrowid
                db.execute(f"insert or ignore into {link} (idCompany, idGame) values (?, ?)",
                           (ids[name], game))
    if apply:
        db.execute("delete from company where idCompany not in "
                   "(select idCompany from publisher_link union select idCompany from developer_link)")
    return changed


def main(argv):
    apply = "--apply" in argv
    args = [a for a in argv if a != "--apply"]
    if len(args) != 1:
        print(__doc__)
        return 2

    db = sqlite3.connect(args[0], timeout=60)
    before = db.execute("select count(*) from company").fetchone()[0]
    with db:
        rated = ratings(db, apply)
        credited = companies_pass(db, apply)
    after = db.execute("select count(*) from company").fetchone()[0]
    verb = "changed" if apply else "would change"
    print(f"{verb} the age ratings of {rated} games and {credited} company lists; "
          f"companies {before} -> {after if apply else '(unchanged, dry run)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
