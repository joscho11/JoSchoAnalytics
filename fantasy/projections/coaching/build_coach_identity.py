"""COACH IDENTITY TABLE — head coach / nominal OC / actual play-caller.

Governing prereg: PREREG_coach_quality_2026-07-28.md (§IDENTITY).

Four identities are maintained SEPARATELY and are never silently merged:

  head_coach          nflverse `load_schedules` home_coach/away_coach, GAME-BY-GAME 1999-2026.
                      Complete. Midseason HC changes appear naturally as a coach change between
                      weeks, so games are attributable to whoever actually held the job that week.

  nominal_oc          English Wikipedia "{season} {Team} season" article, Staff section
                      ("* Offensive coordinator - X"), SEASON level, 2013-2026. Partial coverage;
                      a blank is a real signal that the team named no OC that year, but it is NOT
                      evidence about who called plays.

  actual_play_caller  NOT AVAILABLE from any machine-readable source (verified 2026-07-28 against
                      the nflverse catalog, Pro Football Reference -- 403 to automated access --
                      and Wikipedia). Emitted as UNKNOWN for every team-season. Per prereg it is
                      NEVER inferred, neither from offensive performance nor from staff structure.

  hc_is_playcaller    UNKNOWN wherever actual_play_caller is unknown, i.e. everywhere.

WHY THE DISTINCTION IS LOAD-BEARING. Spot-checked cases where nominal OC != play-caller:
  2023 MIA  OC Frank Smith        -- Mike McDaniel (HC) called plays
  2019 LAR  no OC listed          -- Sean McVay (HC) called plays
  2016 KC   co-OCs Childress/Nagy -- Andy Reid (HC) called plays
Crediting the nominal OC in those seasons is exactly the mis-attribution the prereg forbids, which
is why `offensive_lead` below is a FROZEN, RATIFIED RULE rather than a guess dressed up as data.

Network use is cached to disk; re-runs are offline. Writes derived CSV only.
"""
import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
DATA.mkdir(parents=True, exist_ok=True)
CACHE = DATA / "wikipedia_team_season_cache.json"

UA = {"User-Agent": "JoSchoAnalytics-research/1.0 (joseph.schoenbaum@gmail.com)"}
FIRST_SEASON = 2013          # one season before the 2014 panel start, so 2014 has a prior year
DEPLOY = 2026

# Era-correct Wikipedia article names. nflverse uses one canonical code per franchise; Wikipedia
# titles the article with the name the franchise carried THAT season, so relocations/renames need
# a per-season resolver or ~40 team-seasons silently 404 into "no OC listed".
TEAM_NAMES = {
    "ARI": [(0, "Arizona Cardinals")], "ATL": [(0, "Atlanta Falcons")],
    "BAL": [(0, "Baltimore Ravens")], "BUF": [(0, "Buffalo Bills")],
    "CAR": [(0, "Carolina Panthers")], "CHI": [(0, "Chicago Bears")],
    "CIN": [(0, "Cincinnati Bengals")], "CLE": [(0, "Cleveland Browns")],
    "DAL": [(0, "Dallas Cowboys")], "DEN": [(0, "Denver Broncos")],
    "DET": [(0, "Detroit Lions")], "GB": [(0, "Green Bay Packers")],
    "HOU": [(0, "Houston Texans")], "IND": [(0, "Indianapolis Colts")],
    "JAX": [(0, "Jacksonville Jaguars")], "KC": [(0, "Kansas City Chiefs")],
    "LA":  [(0, "St. Louis Rams"), (2016, "Los Angeles Rams")],
    "LAC": [(0, "San Diego Chargers"), (2017, "Los Angeles Chargers")],
    "LV":  [(0, "Oakland Raiders"), (2020, "Las Vegas Raiders")],
    "MIA": [(0, "Miami Dolphins")], "MIN": [(0, "Minnesota Vikings")],
    "NE":  [(0, "New England Patriots")], "NO": [(0, "New Orleans Saints")],
    "NYG": [(0, "New York Giants")], "NYJ": [(0, "New York Jets")],
    "PHI": [(0, "Philadelphia Eagles")], "PIT": [(0, "Pittsburgh Steelers")],
    "SEA": [(0, "Seattle Seahawks")], "SF": [(0, "San Francisco 49ers")],
    "TB":  [(0, "Tampa Bay Buccaneers")], "TEN": [(0, "Tennessee Titans")],
    "WAS": [(0, "Washington Redskins"), (2020, "Washington Football Team"),
            (2022, "Washington Commanders")],
}
# Same canonicalization the season_dataset uses, so every join keys on one code per franchise.
TEAM_CANON = {"ARZ": "ARI", "AZ": "ARI", "BLT": "BAL", "CLV": "CLE", "HST": "HOU",
              "SL": "LA", "STL": "LA", "SD": "LAC", "OAK": "LV"}


def team_article(abbr, season):
    eras = TEAM_NAMES[abbr]
    name = eras[0][1]
    for start, nm in eras:
        if season >= start:
            name = nm
    return f"{season} {name} season"


# ------------------------------------------------------------------ head coach (complete)
def head_coach_table():
    """Game-by-game head coach, 1999-DEPLOY. One row per (season, week, team, head_coach).

    Game-level (not season-level) so a midseason firing splits the season between the two men and
    each is charged only with the games he actually coached -- the prereg's effective-date rule.
    """
    import nflreadpy as nfl
    s = nfl.load_schedules().to_pandas()
    s = s[s["game_type"] == "REG"].copy()
    home = s[["season", "week", "home_team", "home_coach", "game_id"]].rename(
        columns={"home_team": "team", "home_coach": "head_coach"})
    away = s[["season", "week", "away_team", "away_coach", "game_id"]].rename(
        columns={"away_team": "team", "away_coach": "head_coach"})
    hc = pd.concat([home, away], ignore_index=True)
    hc["team"] = hc["team"].replace(TEAM_CANON)
    hc = hc.dropna(subset=["head_coach"])
    hc["head_coach"] = hc["head_coach"].astype(str).str.strip()
    return hc.sort_values(["season", "week", "team"]).reset_index(drop=True)


# ------------------------------------------------------------------ nominal OC (partial)
def _load_cache():
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def _fetch_wikitext(title, cache, sleep=0.15):
    if title in cache:
        return cache[title]
    url = ("https://en.wikipedia.org/w/api.php?"
           + urllib.parse.urlencode({"action": "parse", "page": title,
                                     "prop": "wikitext", "format": "json"}))
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()
        txt = json.loads(raw)["parse"]["wikitext"]["*"]
    except Exception as exc:                      # 404 for a not-yet-written season article, etc.
        txt = f"__ERR__{type(exc).__name__}"
    cache[title] = txt
    time.sleep(sleep)
    return txt


_OC_PAT = re.compile(
    r"^\s*\*+\s*(?:\[\[)?(?:Co-)?[Oo]ffensive [Cc]oordinator(?:\]\])?"
    r"(?:[^\n]*?)\s*[–—-]\s*(?:\[\[)?([^\]\n|<{]+)", re.M)


def parse_oc(wikitext):
    """Return (list_of_named_OCs, raw_lines). Multiple hits = co-OCs or a midseason change; the
    prereg treats a team-season with >1 named OC as AMBIGUOUS rather than picking one."""
    if not wikitext or wikitext.startswith("__ERR__"):
        return [], []
    names, raws = [], []
    for m in _OC_PAT.finditer(wikitext):
        raw = m.group(0).strip()
        nm = m.group(1).strip()
        nm = re.sub(r"\s*\((?:American football|American football coach|"
                    r"American football, born \d{4}|coach)\)\s*$", "", nm).strip()
        if nm and nm.lower() not in ("tbd", "vacant", "none"):
            names.append(nm)
            raws.append(raw[:160])
    # de-dup, preserve order
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out, raws


# The "{season} {Team} season" articles carry no Staff section until the season is underway, so
# the DEPLOY season parses as 100% none_listed. The maintained list page below is the deploy-season
# source: 32 rows, each with an inline citation to the club's own hiring announcement.
_CUR_ROW = re.compile(r"^\|\s*\[\[([^\]|]+)(?:\|[^\]]*)?\]\]\s*\|\|\s*(.+?)\s*\|\|", re.M)


def _clean_person(cell):
    """Handle the three name encodings the list page mixes: {{sortname|First|Last}},
    {{sortname|First|Last|dab=...}}, and a bare [[Wiki Link]]."""
    m = re.search(r"\{\{\s*sortname\s*\|([^|}]+)\|([^|}]+)", cell)
    if m:
        return f"{m.group(1).strip()} {m.group(2).strip()}"
    m = re.search(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", cell)
    if m:
        nm = (m.group(2) or m.group(1)).strip()
        return re.sub(r"\s*\((?:American football|American football coach|coach)\)\s*$", "", nm)
    return None


def current_oc_table(season, cache):
    """Deploy-season nominal OC from 'List of current NFL offensive coordinators'."""
    name_to_abbr = {}
    for abbr, eras in TEAM_NAMES.items():
        for _, nm in eras:
            name_to_abbr[nm] = abbr
    wtxt = _fetch_wikitext("List of current NFL offensive coordinators", cache)
    rows = []
    for m in _CUR_ROW.finditer(wtxt):
        team_name, person_cell = m.group(1).strip(), m.group(2)
        abbr = name_to_abbr.get(team_name)
        person = _clean_person(person_cell)
        if abbr and person:
            rows.append(dict(season=season, team=abbr,
                             wiki_article="List of current NFL offensive coordinators",
                             nominal_oc=person, oc_candidates=person, n_oc_named=1,
                             oc_status="named", oc_raw=m.group(0)[:160]))
    return pd.DataFrame(rows)


def nominal_oc_table(seasons, refresh=False):
    cache = {} if refresh else _load_cache()
    rows = []
    n_new = 0
    for season in seasons:
        for abbr in sorted(TEAM_NAMES):
            title = team_article(abbr, season)
            had = title in cache
            wtxt = _fetch_wikitext(title, cache)
            n_new += (not had)
            ocs, raws = parse_oc(wtxt)
            rows.append(dict(
                season=season, team=abbr, wiki_article=title,
                nominal_oc=(ocs[0] if len(ocs) == 1 else None),
                oc_candidates="|".join(ocs),
                n_oc_named=len(ocs),
                oc_status=("named" if len(ocs) == 1
                           else "ambiguous_multi" if len(ocs) > 1
                           else "article_missing" if wtxt.startswith("__ERR__")
                           else "none_listed"),
                oc_raw=(raws[0] if raws else None),
            ))
            if n_new and n_new % 40 == 0:
                CACHE.write_text(json.dumps(cache), encoding="utf-8")
                print(f"    ...cached {len(cache)} articles")

    out = pd.DataFrame(rows)
    # deploy season: replace the (empty) season-article rows with the maintained list page
    if DEPLOY in seasons:
        cur = current_oc_table(DEPLOY, cache)
        if len(cur):
            out = pd.concat([out[out.season != DEPLOY], cur], ignore_index=True)
            print(f"  deploy season {DEPLOY}: {len(cur)}/32 OCs from the current-coordinators list")
    CACHE.write_text(json.dumps(cache), encoding="utf-8")
    print(f"  wikipedia: {len(cache)} articles cached ({n_new} fetched this run)")
    return out.sort_values(["season", "team"]).reset_index(drop=True)


# ------------------------------------------------------------------ assemble
def build(seasons=None, refresh=False):
    seasons = seasons or list(range(FIRST_SEASON, DEPLOY + 1))
    print("=" * 78)
    print("COACH IDENTITY BUILD — head coach (complete) + nominal OC (partial) + "
          "play-caller (UNKNOWN by construction)")
    print("=" * 78)

    hc = head_coach_table()
    hc.to_csv(DATA / "head_coach_games.csv", index=False)
    print(f"\nHEAD COACH: {len(hc):,} team-games, seasons {hc.season.min()}-{hc.season.max()}, "
          f"{hc.head_coach.nunique()} distinct coaches")

    hc_season = (hc.groupby(["season", "team"])
                   .agg(n_games=("game_id", "nunique"), n_hc=("head_coach", "nunique"))
                   .reset_index())
    mid = hc_season[hc_season.n_hc > 1]
    print(f"  team-seasons: {len(hc_season)} | with a midseason HC change: {len(mid)} "
          f"({100*len(mid)/len(hc_season):.1f}%)")

    print(f"\nNOMINAL OC: scraping {len(seasons)} seasons x 32 teams "
          f"= {len(seasons)*32} Wikipedia articles (cached)")
    oc = nominal_oc_table(seasons, refresh=refresh)

    # play-caller: unknown, by construction and on purpose
    oc["actual_play_caller"] = pd.NA
    oc["play_caller_status"] = "unknown_no_source"
    oc["hc_is_playcaller"] = pd.NA

    oc.to_csv(DATA / "coach_identity_team_season.csv", index=False)

    print("\n--- nominal OC coverage by status ---")
    print(oc.oc_status.value_counts().to_string())
    named = (oc.oc_status == "named").mean()
    print(f"\nsingle named OC: {100*named:.1f}% of {len(oc)} team-seasons")
    print("\nper-season coverage:")
    cov = oc.groupby("season").apply(
        lambda d: pd.Series({"named": int((d.oc_status == "named").sum()),
                             "none_listed": int((d.oc_status == "none_listed").sum()),
                             "ambiguous": int((d.oc_status == "ambiguous_multi").sum()),
                             "missing_article": int((d.oc_status == "article_missing").sum())}),
        include_groups=False)
    print(cov.to_string())

    print("\nPLAY-CALLER: 0.0% — no machine-readable source exists. Emitted UNKNOWN for all "
          f"{len(oc)} team-seasons; never inferred (prereg §IDENTITY).")
    print(f"\nwrote {DATA/'head_coach_games.csv'} + {DATA/'coach_identity_team_season.csv'}")
    return hc, oc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="ignore the wikipedia cache")
    a = ap.parse_args()
    if a.build:
        build(refresh=a.refresh)
    else:
        raise SystemExit("pass --build")


if __name__ == "__main__":
    main()
