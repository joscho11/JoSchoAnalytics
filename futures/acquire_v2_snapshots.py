"""Capture the point-in-time snapshots the v2 feature families need. Acquisition only.

WHY THIS IS A SCRIPT AND WHY IT RUNS TODAY
------------------------------------------
Three of the four inputs below are revised IN PLACE upstream. A roster pulled in December is a
December roster no matter which season you ask for, so "what did team X look like before Week 1"
cannot be reconstructed after the fact. The 2026 roster in particular decays every week as cuts and
signings land. Capturing it dated, with a hash, is the only way a 2026 roster feature can later be
called point-in-time without lying.

Nothing here fits, evaluates or predicts. It writes four artifacts and a provenance record.

WHAT IT CORRECTS
----------------
`futures/PRESEASON_FEATURE_NOTES.md` verdicted the All-Pro, roster-continuity and preseason-injury
families UNAVAILABLE on the grounds that this repo owns no dated preseason roster. That was wrong:
`nflreadpy.load_rosters_weekly` carries week-level rosters for 2002-2025 with a 100% populated
`gsis_id`, and each team-season opening week is a genuine pre-kickoff snapshot. The audit
never probed it. See the
`corrections` block in the provenance JSON.

Run:  python futures/acquire_v2_snapshots.py
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import nflreadpy as nfl
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "futures" / "data"
ART = REPO / "futures" / "artifacts"

PREDICT_SEASON = 2026
HISTORY = list(range(2002, 2026))          # rosters_weekly coverage, verified 2002-2025
# Snap counts do NOT reach back to 2002. The loader refuses anything before 2012, so any
# roster-continuity feature built from snaps is undefined for the early seasons. The loader accepts
# 2012 but returns ZERO rows for it, so real coverage starts 2013 and a prior-season continuity
# feature first resolves in 2014, not 2013. Measured, not assumed.
# Recorded rather than hidden: the panel's median imputer will fill those seasons, and a feature
# imputed across twelve of twenty-five seasons is weak evidence, not strong.
SNAPS_HISTORY = list(range(2012, 2026))
SNAPS_MIN_SEASON = 2012
CAPTURE_DATE = date.today().isoformat()

# Nickname -> nflverse franchise code, matching the panel's convention (LA = Rams, LAC = Chargers).
TEAM = {
    "bills": "BUF", "dolphins": "MIA", "pats": "NE", "jets": "NYJ",
    "ravens": "BAL", "bengals": "CIN", "browns": "CLE", "steelers": "PIT",
    "texans": "HOU", "colts": "IND", "jags": "JAX", "titans": "TEN",
    "broncos": "DEN", "chiefs": "KC", "raiders": "LV", "chargers": "LAC",
    "cowboys": "DAL", "giants": "NYG", "eagles": "PHI", "commanders": "WAS",
    "bears": "CHI", "lions": "DET", "packers": "GB", "vikings": "MIN",
    "falcons": "ATL", "panthers": "CAR", "saints": "NO", "bucs": "TB",
    "cards": "ARI", "rams": "LA", "49ers": "SF", "seahawks": "SEA",
}

# Joseph's manual capture, 2026-08-05. FanDuel: the alternate line nearest even money on the over,
# over price only. DraftKings: the app's default line, both sides.
# Validated before storage: 32/32 teams per book; DK per-team hold 3.79%-4.84% (median 4.71%),
# no out-of-range hold; DK posted lines sum to exactly 272; DK devigged implied wins 273.04.
FANDUEL = {
    "bills": (10.5, -125, None), "dolphins": (3.5, -135, None), "pats": (10.5, 115, None),
    "jets": (5.5, 100, None), "ravens": (11.5, 120, None), "bengals": (10.5, 105, None),
    "browns": (5.5, -115, None), "steelers": (8.5, 120, None), "texans": (10.5, 125, None),
    "colts": (8.5, 120, None), "jags": (8.5, -130, None), "titans": (6.5, 115, None),
    "broncos": (9.5, -120, None), "chiefs": (10.5, 120, None), "raiders": (6.5, 125, None),
    "chargers": (9.5, -130, None), "cowboys": (9.5, 105, None), "giants": (7.5, 100, None),
    "eagles": (10.5, 115, None), "commanders": (7.5, -110, None), "bears": (9.5, 115, None),
    "lions": (10.5, -120, None), "packers": (9.5, -110, None), "vikings": (8.5, -110, None),
    "falcons": (7.5, 120, None), "panthers": (7.5, 120, None), "saints": (7.5, -120, None),
    "bucs": (8.5, 120, None), "cards": (4.5, 125, None), "rams": (12.5, 125, None),
    "49ers": (9.5, -130, None), "seahawks": (10.5, -110, None),
}
DRAFTKINGS = {
    "cards": (3.5, -136, 115), "falcons": (6.5, -140, 120), "ravens": (11.5, 115, -140),
    "bills": (10.5, -120, 100), "panthers": (7.5, 115, -136), "bears": (9.5, 100, -120),
    "bengals": (10.5, 115, -140), "browns": (5.5, -130, 110), "cowboys": (9.5, 115, -140),
    "broncos": (9.5, -115, -105), "lions": (10.5, -115, -105), "packers": (9.5, -130, 110),
    "texans": (9.5, -146, 124), "colts": (7.5, -140, 115), "jags": (8.5, -140, 116),
    "chiefs": (10.5, 115, -140), "raiders": (5.5, -146, 120), "chargers": (9.5, -140, 115),
    "rams": (11.5, -125, 105), "dolphins": (4.5, 122, -146), "vikings": (8.5, -110, -110),
    "pats": (10.5, 115, -140), "saints": (7.5, -120, 100), "giants": (7.5, -110, -110),
    "jets": (5.5, -120, 100), "eagles": (10.5, 115, -140), "steelers": (8.5, 110, -130),
    "49ers": (9.5, -146, 120), "seahawks": (10.5, -115, -105), "bucs": (8.5, 115, -136),
    "titans": (6.5, -105, -115), "commanders": (7.5, -125, 105),
}
BOOKS = {"FanDuel": FANDUEL, "DraftKings": DRAFTKINGS}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def to_pandas(obj):
    return obj.to_pandas() if hasattr(obj, "to_pandas") else obj


def build_lines() -> pd.DataFrame:
    rows = []
    for book, table in BOOKS.items():
        for nick, (line, over, under) in table.items():
            rows.append({
                "season": PREDICT_SEASON,
                "team": TEAM[nick],
                "win_total_line": float(line),
                "price_over": int(over),
                "price_under": None if under is None else int(under),
                "book": book,
                "market_source": f"{book} sportsbook app (manual capture)",
                "as_of_date": CAPTURE_DATE,
                "source": "manual capture by Joseph Schoenbaum from the book's own app",
                "source_url": None,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "raw_team_name": nick,
                "point_in_time_status": "preseason, captured before Week 1",
            })
    df = pd.DataFrame(rows)
    assert len(df) == 64 and df.groupby("book")["team"].nunique().eq(32).all()
    assert df["team"].nunique() == 32
    # DraftKings is the only book with both sides, so it is the only gate-C-eligible source here.
    dk = df[df["book"] == "DraftKings"]
    assert dk["price_under"].notna().all()
    assert abs(dk["win_total_line"].sum() - 272.0) < 1e-9, "DK lines no longer sum to 272"
    return df


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    ART.mkdir(parents=True, exist_ok=True)
    written = {}

    # 1. The deploy-side roster. This is the file that decays; everything else is reconstructible.
    r26 = to_pandas(nfl.load_rosters([PREDICT_SEASON]))
    p = DATA / f"roster_snapshot_{PREDICT_SEASON}.parquet"
    r26.to_parquet(p, index=False)
    written[p.name] = {"rows": len(r26), "teams": int(r26["team"].nunique()),
                       "gsis_coverage": round(float(r26["gsis_id"].notna().mean()), 4),
                       "sha256": sha256_file(p)}

    # 2. The historical spine: each team-season's OPENING roster.
    #
    # Not literally `week == 1`. Miami and Tampa Bay have no week-1 row in 2017 because Hurricane
    # Irma postponed their opener to week 11, so a hard week-1 filter silently drops two team-seasons
    # and leaves 30 teams in that year. Taking each team-season's earliest present week is the same
    # snapshot for all 798 other team-seasons and is still the opener for those two.
    rw = to_pandas(nfl.load_rosters_weekly(HISTORY))
    first_wk = rw.groupby(["season", "team"])["week"].transform("min")
    w1 = rw[rw["week"] == first_wk].copy()
    per_season = w1.groupby("season")["team"].nunique()
    assert per_season.eq(32).all(), f"seasons without 32 teams: {per_season[per_season != 32].to_dict()}"
    late = w1[w1["week"] > 1][["season", "team", "week"]].drop_duplicates()
    p = DATA / "roster_snapshot_opening_2002_2025.parquet"
    w1.to_parquet(p, index=False)
    written[p.name] = {"rows": len(w1), "seasons": [int(w1.season.min()), int(w1.season.max())],
                       "teams_per_season": 32,
                       "rule": "earliest week present per team-season (week 1 for 798 of 800)",
                       "not_week_1": late.to_dict("records"),
                       "gsis_coverage": round(float(w1["gsis_id"].notna().mean()), 4),
                       "sha256": sha256_file(p)}

    # 3. Prior-season snap counts, for roster continuity (share of last year's snaps retained).
    snaps = to_pandas(nfl.load_snap_counts(SNAPS_HISTORY))
    p = DATA / f"snap_counts_{SNAPS_MIN_SEASON}_2025.parquet"
    snaps.to_parquet(p, index=False)
    written[p.name] = {"rows": len(snaps),
                       "seasons": [int(snaps.season.min()), int(snaps.season.max())],
                       "coverage_limit": (f"loader refuses seasons before {SNAPS_MIN_SEASON}; any "
                                          f"snap-based continuity feature is undefined for "
                                          f"2002-{SNAPS_MIN_SEASON} and first resolves in "
                                          f"{int(snaps.season.min()) + 1} (the loader accepts 2012 "
                                          f"but returns no rows for it)"),
                       "sha256": sha256_file(p)}

    # 4. The first named-book lines this project has ever held.
    lines = build_lines()
    p = DATA / f"win_totals_{PREDICT_SEASON}_named_books.csv"
    lines.to_csv(p, index=False)
    written[p.name] = {"rows": len(lines), "books": sorted(BOOKS),
                       "both_sides_priced": ["DraftKings"], "sha256": sha256_file(p)}

    prov = {
        "script": "futures/acquire_v2_snapshots.py",
        "purpose": "point-in-time capture for the v2 feature families; acquisition only",
        "capture_date": CAPTURE_DATE,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "artifacts": written,
        "corrections": {
            "supersedes": "futures/PRESEASON_FEATURE_NOTES.md blockers B and C",
            "finding": ("the audit verdicted the All-Pro, roster-continuity and preseason-injury "
                        "families UNAVAILABLE for want of a dated preseason roster. "
                        "load_rosters_weekly carries week-level rosters for 2002-2025 with gsis_id "
                        "fully populated, and week 1 is a pre-kickoff snapshot. The audit never "
                        "probed it, so those verdicts were too strict."),
            "still_unavailable": ("a true preseason IR/PUP/NFI transaction feed. The week-1 roster "
                                  "status field (RES/INA/DEV) is the honest proxy and must be "
                                  "described as reserve-list status, never as an injury report."),
        },
        "lines_note": ("FanDuel rows carry the over price only, so they cannot be devigged and are "
                       "a cross-check source, not a gate-C-eligible benchmark. DraftKings carries "
                       "both sides."),
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "pandas": pd.__version__, "nflreadpy": getattr(nfl, "__version__", "unknown")},
    }
    out = ART / "v2_snapshot_provenance.json"
    out.write_text(json.dumps(prov, indent=2), encoding="utf-8")

    for name, meta in written.items():
        print(f"  {name}")
        for k, v in meta.items():
            print(f"      {k}: {v}")
    print(f"\nprovenance -> {out.relative_to(REPO).as_posix()}")


if __name__ == "__main__":
    sys.exit(main())
