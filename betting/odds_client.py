"""NFL odds via The Odds API (free tier) -> Closing Line Value tracking.

This fills the reserved `pick_line` / `closing_line` / `clv` columns in
`predictions_tracker.csv` with a real multi-book line at pick time and near
kickoff. CLV (did the market move toward your number after you bet?) is the best
available long-run-profit signal and the prerequisite for judging every model.

No scraping, no paid data: one bulk call returns all games (spreads+totals = 2
credits, free tier ~500/month). Books post lines months early, so this is fully
testable in the offseason.

    python betting/odds_client.py lines                 # current consensus board
    python betting/odds_client.py snapshot --which pick --season 2026 --week 1
    python betting/odds_client.py snapshot --which closing --season 2026 --week 1
    # --season/--week are REQUIRED (review L-16): an unscoped snapshot would walk the
    # whole tracker and can overwrite HISTORICAL rows whose matchup repeats on the
    # currently posted board.

The model's pick side comes from the tracker's `recommendation` column
("HOME (ATL)" / "AWAY (LA)" / "PASS"). Lines are home-relative, matching
`spread_line` already in the tracker.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from statistics import median
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

import pandas as pd

API_BASE = "https://api.the-odds-api.com/v4"
SPORT = "americanfootball_nfl"
ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / "betting" / "predictions_tracker.csv"

# The Odds API full name -> nflverse abbreviation (matches predictions_tracker).
NFL_TEAMS = {
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF", "Carolina Panthers": "CAR", "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE", "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC", "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LA", "Miami Dolphins": "MIA", "Minnesota Vikings": "MIN",
    "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
    "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF", "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN", "Washington Commanders": "WAS",
}


# ---- API plumbing --------------------------------------------------------
def load_dotenv() -> None:
    envp = ROOT / ".env"
    if not envp.exists():
        return
    for line in envp.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def api_key() -> str:
    load_dotenv()
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        sys.exit("ODDS_API_KEY not set (add it to .env or the environment).")
    return key


def api_get(path: str, **params) -> tuple[object, dict]:
    params["apiKey"] = api_key()
    url = f"{API_BASE}{path}?{urlencode(params)}"
    try:
        with urlopen(url, timeout=30) as r:
            raw = r.read()
            hdr = {"remaining": r.headers.get("x-requests-remaining"),
                   "used": r.headers.get("x-requests-used")}
        return json.loads(raw), hdr
    except HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        sys.exit(f"HTTP {e.code}: {body}")
    except URLError as e:
        sys.exit(f"Network error reaching The Odds API: {e.reason}")
    except json.JSONDecodeError as e:
        sys.exit(f"Malformed JSON from The Odds API: {e}")


# ---- line parsing --------------------------------------------------------
MIN_BOOKS = 3  # don't trust a "consensus" from one or two off-market books


def consensus(event: dict, min_books: int = MIN_BOOKS) -> dict | None:
    """One game -> consensus home spread and total (median across books), in
    nflverse sign (POSITIVE = home favored), matching the tracker's `spread_line`.
    The Odds API posts the home line in sportsbook sign (negative = home favored),
    so we negate. Returns None below `min_books` to avoid snapshotting a thin board."""
    home = NFL_TEAMS.get(event.get("home_team"))
    away = NFL_TEAMS.get(event.get("away_team"))
    if not home or not away:
        return None
    home_pts, totals = [], []
    for bk in event.get("bookmakers", []):
        for mk in bk.get("markets", []):
            if mk["key"] == "spreads":
                for oc in mk.get("outcomes", []):
                    if NFL_TEAMS.get(oc["name"]) == home and oc.get("point") is not None:
                        home_pts.append(oc["point"])
            elif mk["key"] == "totals":
                for oc in mk.get("outcomes", []):
                    if oc.get("name") == "Over" and oc.get("point") is not None:
                        totals.append(oc["point"])
    if len(home_pts) < min_books:
        return None
    return {"home_team": home, "away_team": away,
            "date": str(event.get("commence_time", ""))[:10],
            "spread": round(-median(home_pts), 2),  # negate -> nflverse sign; can be a quarter-point
            # totals gated on its OWN book count (review U4A-8): the spread guard
            # above says nothing about how many books quoted the total.
            "total": round(median(totals), 1) if len(totals) >= min_books else None,
            "n_books_total": len(totals),
            "n_books": len(home_pts)}


def fetch_lines() -> dict:
    """(home_abbr, away_abbr) -> consensus line dict, for all posted NFL games."""
    events, hdr = api_get(f"/sports/{SPORT}/odds/", regions="us",
                          markets="spreads,totals", oddsFormat="decimal")
    out = {}
    for ev in events:
        c = consensus(ev)
        if c:
            out[(c["home_team"], c["away_team"])] = c
    return out, hdr


# ---- CLV -----------------------------------------------------------------
def pick_side(recommendation: str) -> str | None:
    rec = str(recommendation).upper()
    if rec.startswith("HOME"):
        return "HOME"
    if rec.startswith("AWAY"):
        return "AWAY"
    return None  # PASS / blank


def clv_points(pick_line: float, closing_line: float, side: str) -> float:
    """Positive = you beat the close. Lines are nflverse sign (POSITIVE = home
    favored), same convention as the tracker and clv_backtest. A HOME bettor beats
    the close when the close is MORE home-favored than the pick (closing > pick);
    an AWAY bettor when the close is LESS home-favored."""
    if side == "HOME":
        return round(closing_line - pick_line, 2)   # 2dp matches clv_backtest (U4A-9)
    if side == "AWAY":
        return round(pick_line - closing_line, 2)   # 2dp matches clv_backtest (U4A-9)
    return float("nan")


# ---- commands ------------------------------------------------------------
def lines_cmd(args) -> None:
    lines, hdr = fetch_lines()
    print(f"{len(lines)} NFL games with posted lines (consensus, home-relative):\n")
    print(f"{'date':11s} {'matchup':16s} {'spread':>7} {'total':>6} {'books':>6}")
    print("-" * 50)
    for c in sorted(lines.values(), key=lambda c: c["date"]):
        tot = f"{c['total']}" if c["total"] is not None else "-"
        print(f"{c['date']:11s} {c['away_team']+' @ '+c['home_team']:16s} "
              f"{c['spread']:+7.1f} {tot:>6} {c['n_books']:>6}")
    print(f"\nquota: {hdr['remaining']} remaining, {hdr['used']} used")


def _write_tracker_atomic(df: pd.DataFrame, orig: pd.DataFrame) -> None:
    """Integrity-checked atomic replace of the forward log (review L-2 / R34).

    The tracker is an append-only forward record. Before replacing it: row count
    and column list must be unchanged, and every NON-TARGET column must equal the
    original frame — a snapshot may only fill pick_line/closing_line/clv."""
    target_cols = {"pick_line", "closing_line", "clv"}
    if len(df) != len(orig):
        sys.exit(f"REFUSING tracker write: row count changed {len(orig)} -> {len(df)}")
    if list(df.columns) != list(orig.columns):
        sys.exit("REFUSING tracker write: column list changed")
    for c in df.columns:
        if c in target_cols:
            continue
        if not df[c].fillna("__nan__").equals(orig[c].fillna("__nan__")):
            sys.exit(f"REFUSING tracker write: non-target column '{c}' was mutated")
    tmp = TRACKER.with_suffix(TRACKER.suffix + ".tmp")
    df.to_csv(tmp, index=False)
    os.replace(tmp, TRACKER)


def snapshot_cmd(args) -> None:
    if not TRACKER.exists():
        sys.exit(f"tracker not found: {TRACKER}")
    # R33 (review L-16): a write command must be scoped. Refuse BEFORE any API
    # fetch or file write.
    if not getattr(args, "season", None) or not getattr(args, "week", None):
        sys.exit("snapshot requires --season and --week: an unscoped snapshot walks "
                 "the whole tracker and can overwrite historical rows whose matchup "
                 "repeats on the current board.")
    df = pd.read_csv(TRACKER)
    orig = df.copy(deep=True)
    sub = df
    if args.season:
        sub = sub[sub["season"] == args.season]
    if args.week:
        sub = sub[sub["week"] == args.week]
    if sub.empty:
        print("No tracker rows match the season/week filter "
              "(2026 predictions not generated yet?). Nothing to snapshot.")
        return

    lines, hdr = fetch_lines()
    col = "pick_line" if args.which == "pick" else "closing_line"
    updated = graded = skipped = unmatched = 0
    for i, row in sub.iterrows():
        key = (row["home_team"], row["away_team"])
        if key not in lines:
            unmatched += 1
            continue
        # pick_line is the CLV baseline (line WHEN you picked) — first write wins so a
        # re-run doesn't stomp it; closing_line is always refreshed to the latest.
        if (col == "pick_line" and pd.notna(df.at[i, "pick_line"])
                and not getattr(args, "force", False)):   # R32 (review L-15)
            skipped += 1
        else:
            df.at[i, col] = lines[key]["spread"]
            updated += 1
        pl, cl = df.at[i, "pick_line"], df.at[i, "closing_line"]
        side = pick_side(row.get("recommendation", ""))
        if pd.notna(pl) and pd.notna(cl) and side:
            df.at[i, "clv"] = clv_points(float(pl), float(cl), side)
            graded += 1

    _write_tracker_atomic(df, orig)   # R34 (review L-2)
    print(f"wrote {col} for {updated} game(s); computed clv for {graded}; "
          f"{skipped} kept existing pick_line; {unmatched} unmatched (no line / team-name "
          f"mismatch).")
    if graded:
        done = df[df["clv"].notna()]
        beat = (done["clv"] > 0).mean() * 100
        print(f"running CLV: {len(done)} graded, beat the close {beat:.0f}%, "
              f"avg {done['clv'].mean():+.2f} pts")
    print(f"quota: {hdr['remaining']} remaining, {hdr['used']} used")


def main() -> None:
    p = argparse.ArgumentParser(description="NFL odds + CLV tracking (The Odds API)")
    sub = p.add_subparsers(dest="cmd", required=True)

    ln = sub.add_parser("lines", help="show the current consensus board")
    ln.set_defaults(func=lines_cmd)

    sn = sub.add_parser("snapshot", help="write pick_line/closing_line + clv into the tracker")
    sn.add_argument("--which", choices=["pick", "closing"], required=True)
    sn.add_argument("--season", type=int, required=True)   # R33 (review L-16)
    sn.add_argument("--week", type=int, required=True)     # R33 (review L-16)
    sn.add_argument("--force", action="store_true",
                    help="overwrite an existing pick_line (default: first write wins)")
    sn.set_defaults(func=snapshot_cmd)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
