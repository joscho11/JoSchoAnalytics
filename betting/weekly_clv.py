"""Automation-ready CLV driver — picks pick/closing by weekday and snapshots.

Standalone on purpose: NOT yet wired into the GitHub Actions weekly workflow or
the Streamlit app. When you're ready to go live, add one step to each weekly job:

    # Tue/Thu prediction job, after picks are written:
    python betting/weekly_clv.py            # weekday auto-selects 'pick'
    # Sunday pre-kickoff job:
    python betting/weekly_clv.py --which closing

It reads the upcoming slate straight from predictions_tracker.csv (rows whose
gameday is within the next week), so it needs no hardcoded week number and
no-ops cleanly in the offseason.

    python betting/weekly_clv.py                       # auto (pick Tue-Thu, else closing)
    python betting/weekly_clv.py --which pick --date 2026-09-08   # force / dry-date
"""
from __future__ import annotations

import argparse
import types
from datetime import date, datetime, timedelta

import pandas as pd

import odds_client as oc


def current_target(df: pd.DataFrame, today: date):
    """(season, week) of the nearest upcoming tracked slate, or None (offseason)."""
    df = df.copy()
    df["gd"] = pd.to_datetime(df["gameday"], errors="coerce").dt.date
    upcoming = df[(df["gd"] >= today - timedelta(days=1))
                  & (df["gd"] <= today + timedelta(days=8))].dropna(subset=["gd"])
    if upcoming.empty:
        return None
    row = upcoming.sort_values("gd").iloc[0]
    return int(row["season"]), int(row["week"])


def main() -> None:
    p = argparse.ArgumentParser(description="Weekly CLV snapshot driver")
    p.add_argument("--which", choices=["pick", "closing", "auto"], default="auto")
    p.add_argument("--date", default=str(date.today()),
                   help="run-date override (for testing/backfill)")
    args = p.parse_args()

    today = datetime.strptime(args.date, "%Y-%m-%d").date()
    which = args.which
    if which == "auto":
        # NFL picks finalize Tue-Thu; lines close around Sunday kickoff
        which = "pick" if today.weekday() in (1, 2, 3) else "closing"

    if not oc.TRACKER.exists():
        print(f"tracker not found: {oc.TRACKER}")
        return
    df = pd.read_csv(oc.TRACKER)
    tgt = current_target(df, today)
    if not tgt:
        print(f"No upcoming tracked games near {today} (offseason or no current "
              f"predictions yet). No-op.")
        return
    season, week = tgt
    print(f"[weekly_clv] {today} -> snapshot '{which}' for {season} week {week}")
    oc.snapshot_cmd(types.SimpleNamespace(which=which, season=season, week=week))


if __name__ == "__main__":
    main()
