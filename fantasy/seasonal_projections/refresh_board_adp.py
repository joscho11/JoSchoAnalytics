"""Daily ADP refresh for the shipped 2026 Draft Board — MARKET DATA ONLY.

The model is FROZEN for 2026. This script re-pulls LIVE Sleeper ADP and recomputes
ONLY the three price-derived columns (adp_half_ppr, adp_pos_rank, value_gap) against
the FROZEN projections, then writes one regenerable overlay CSV. It never writes
phase4_band_2026.csv, talent_index_2026.csv, the season dataset, or the ADP cache.

Freeze boundary (see .claude/skills/board-refresh/SKILL.md):
  - FROZEN, read-only: phase4_band_2026.csv gives the 180-player set and each row's
    frozen projection rank = adp_pos_rank - value_gap (ADP-independent).
  - LIVE: Sleeper ADP, pulled fresh via fetch_adp's own functions (no fork).
  - REGENERABLE, written: board_adp_live_2026.csv (the overlay the tab reads).

In-season pause (option i, hard date guard): on/after SEASON_START a SCHEDULED run
is a no-op that writes nothing and logs "in-season: pre-draft board frozen, refresh
paused". A manual run (--force / BOARD_REFRESH_FORCE=1) always runs. Change the date
via BOARD_REFRESH_SEASON_START or the SEASON_START constant below.

Research log (PRIVATE — adp_logs/ is gitignored, never on the public tip): each
successful run writes a dated snapshot board_adp_<YYYY-MM-DD>.csv and appends one
row to refresh_ledger.jsonl. This is a fenced research artifact — never a content
input; the movers detail is player-level directional data and must not leak to any
board/video surface.

Run:   python fantasy/seasonal_projections/refresh_board_adp.py [--force]
"""
import argparse
import json
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from apply_board_labels import ALIAS, nmz  # reuse the exact band-join alias bridge
from fetch_adp import fetch_season, load_players

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BAND = HERE / "phase4_band_2026.csv"                 # FROZEN — read only
DATASET = HERE / "season_dataset_2014_2026.csv"      # FROZEN — read only (fallback price)
OVERLAY = HERE / "board_adp_live_2026.csv"           # REGENERABLE — the only committed output
LOGS_DIR = HERE / "adp_logs"                          # PRIVATE — gitignored
LEDGER = LOGS_DIR / "refresh_ledger.jsonl"

BOARD_SEASON = 2026
MIN_PULL_PLAYERS = 150                                # healthy-pull floor; abort below this
# In-season guard: on/after this date a scheduled run pauses (option i). Override with
# BOARD_REFRESH_SEASON_START=YYYY-MM-DD. Kickoff-week default so the pre-draft board
# freezes once real drafts are done.
SEASON_START = date(2026, 9, 4)


def _season_start() -> date:
    raw = os.environ.get("BOARD_REFRESH_SEASON_START")
    return date.fromisoformat(raw) if raw else SEASON_START


def _forced(cli_force: bool) -> bool:
    return cli_force or os.environ.get("BOARD_REFRESH_FORCE") == "1"


def _append_ledger(row: dict) -> None:
    LOGS_DIR.mkdir(exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _prior_snapshot(today_name: str) -> pd.DataFrame | None:
    if not LOGS_DIR.exists():
        return None
    snaps = sorted(p for p in LOGS_DIR.glob("board_adp_*.csv") if p.name != today_name)
    if not snaps:
        return None
    return pd.read_csv(snaps[-1])


def _atomic_write(df: pd.DataFrame, path: Path) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    os.close(fd)
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="run even in-season (set by workflow_dispatch)")
    args = ap.parse_args()

    run_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    source_date = datetime.now(timezone.utc).date().isoformat()

    # --- in-season pause (hard date guard) ---
    if date.today() >= _season_start() and not _forced(args.force):
        msg = "in-season: pre-draft board frozen, refresh paused"
        print(msg)
        _append_ledger({"run_ts": run_ts, "source_date": source_date,
                        "status": f"paused ({msg})", "pull_players": None,
                        "matched": None, "mean_abs_rank_change": None, "movers": []})
        return 0

    # --- pull live ADP (reuse fetch_adp; no disk write) ---
    try:
        players = load_players()
        fresh = fetch_season(BOARD_SEASON, players)
    except Exception as e:                                   # network / endpoint failure
        reason = f"aborted: pull failed ({type(e).__name__}: {e})"
        print(reason)
        _append_ledger({"run_ts": run_ts, "source_date": source_date, "status": reason,
                        "pull_players": 0, "matched": None,
                        "mean_abs_rank_change": None, "movers": []})
        return 1

    # --- validate the pull (never publish off a malformed/short pull) ---
    if fresh is None or fresh.empty or "adp_half_ppr" not in fresh.columns \
            or len(fresh) < MIN_PULL_PLAYERS:
        n = 0 if fresh is None else len(fresh)
        reason = f"aborted: unhealthy pull ({n} players < {MIN_PULL_PLAYERS} floor)"
        print(reason)
        _append_ledger({"run_ts": run_ts, "source_date": source_date, "status": reason,
                        "pull_players": n, "matched": None,
                        "mean_abs_rank_change": None, "movers": []})
        return 1

    # --- frozen inputs (read only) ---
    band = pd.read_csv(BAND, usecols=["player", "player_id", "position",
                                      "adp_pos_rank", "value_gap"])
    assert len(band) == 180, f"frozen band is {len(band)} rows, expected 180"
    band["proj_pos_rank"] = band["adp_pos_rank"] - band["value_gap"]   # ADP-independent
    band["nn"] = band["player"].map(nmz)

    frozen_price = pd.read_csv(DATASET, usecols=["player_id", "season", "adp_half_ppr"])
    frozen_price = frozen_price[frozen_price.season == BOARD_SEASON][
        ["player_id", "adp_half_ppr"]].rename(columns={"adp_half_ppr": "adp_frozen"})

    # --- bridge fresh ADP to the frozen 180 (same alias bridge the band was built with) ---
    fresh = fresh.copy()
    fresh["nn"] = fresh["player"].map(nmz)
    fresh_adp = fresh.drop_duplicates(["nn", "position"])[["nn", "position", "adp_half_ppr"]] \
                     .rename(columns={"adp_half_ppr": "adp_fresh"})

    m = band.merge(fresh_adp, on=["nn", "position"], how="left") \
            .merge(frozen_price, on="player_id", how="left")
    matched = int(m["adp_fresh"].notna().sum())
    # per-player fallback to the frozen price when a frozen-board player is absent from a
    # healthy pull — keeps the overlay complete and stateless, never partial.
    m["adp_half_ppr"] = m["adp_fresh"].where(m["adp_fresh"].notna(), m["adp_frozen"])

    # --- deterministic recompute over the fixed 180 pool ---
    m = m.sort_values(["adp_half_ppr", "player_id"]).reset_index(drop=True)
    m["adp_pos_rank"] = m.groupby("position").cumcount() + 1          # 1 = lowest ADP
    m["value_gap"] = m["adp_pos_rank"] - m["proj_pos_rank"]
    m["refreshed_at"] = source_date

    overlay = m[["player_id", "adp_half_ppr", "adp_pos_rank", "value_gap", "refreshed_at"]] \
                .sort_values("player_id").reset_index(drop=True)

    # --- movement vs the prior dated snapshot (private research metrics) ---
    today_name = f"board_adp_{source_date}.csv"
    prior = _prior_snapshot(today_name)
    mean_abs = None
    movers = []
    if prior is not None and "adp_pos_rank" in prior.columns:
        j = overlay.merge(prior[["player_id", "adp_pos_rank"]], on="player_id",
                          how="inner", suffixes=("", "_prev"))
        j["delta"] = j["adp_pos_rank"] - j["adp_pos_rank_prev"]
        if len(j):
            mean_abs = round(float(j["delta"].abs().mean()), 3)
            names = band.set_index("player_id")[["player", "position"]]
            top = j.reindex(j["delta"].abs().sort_values(ascending=False).index).head(5)
            for _, r in top.iterrows():
                pid = r["player_id"]
                movers.append({"player_id": pid,
                               "player": str(names.loc[pid, "player"]) if pid in names.index else "",
                               "position": str(names.loc[pid, "position"]) if pid in names.index else "",
                               "rank_delta": int(r["delta"])})

    # --- write the overlay (atomic) + the dated private snapshot ---
    _atomic_write(overlay, OVERLAY)
    LOGS_DIR.mkdir(exist_ok=True)
    _atomic_write(overlay, LOGS_DIR / today_name)   # one file per run day
    _append_ledger({"run_ts": run_ts, "source_date": source_date, "status": "success",
                    "pull_players": int(len(fresh)), "matched": matched,
                    "mean_abs_rank_change": mean_abs, "movers": movers})

    print(f"refresh OK: {matched}/180 matched to fresh ADP; source {source_date}; "
          f"mean|Δrank| {mean_abs}; wrote {OVERLAY.name} + snapshot + ledger row")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
