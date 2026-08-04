"""Daily ADP refresh for the shipped 2026 Draft Board — MARKET DATA ONLY.

The projections/model are FROZEN for 2026. This script re-pulls LIVE Sleeper ADP and
refreshes the price columns (adp_half_ppr, adp_pos_rank) for the fixed board universe,
then writes one regenerable overlay CSV. It never writes phase4_band_2026.csv,
talent_index_2026.csv, the season dataset, or the ADP cache.

Board universe (2026-07-22): the tab was rebuilt as a season-projection comparison table
over EVERY player with a 2026 Sleeper ADP (~245), so the refresh now covers that full
universe — taken from the FROZEN season dataset — not just the old 180-player band. The
band file stays on disk, read-only, for the closed research campaign; the refresh no
longer reads it, and the band-derived value_gap column was dropped from the overlay.

Freeze boundary (see .claude/skills/board-refresh/SKILL.md):
  - FROZEN, read-only: season_dataset_2014_2026.csv defines the fixed ~245-player universe
    and the fallback price; the model projections are frozen and joined by the tab, not here.
  - LIVE: Sleeper ADP, pulled fresh via fetch_adp's own functions (no fork).
  - REGENERABLE, written: board_adp_live_2026.csv (the overlay the tab reads:
    player_id, adp_half_ppr, adp_pos_rank, refreshed_at, plus the per-row provenance
    columns position / adp_source / adp_matched described below).

Coverage gate (added 2026-08-03): the run used to validate only the SIZE of the live
pull (MIN_PULL_PLAYERS) and the size of the board universe. `matched` was computed and
logged but gated nothing, so a pull that returned 245 well-formed rows under a changed
schema — matching none of the board — published a 100%-stale overlay stamped with
today's date. The denominator that matters is matched / len(universe), NOT pull size.
See COVERAGE FLOORS below; a low overall OR a low per-position coverage now aborts with
a nonzero exit and leaves the previous overlay untouched on disk.

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
import math
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(HERE))
from apply_board_labels import ALIAS, nmz  # reuse the exact band-join alias bridge
from fetch_adp import fetch_season, load_players
from seasonal_config import SEASON_START, board_refresh_season_start

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DATASET = HERE / "season_dataset_2014_2026.csv"      # FROZEN — defines the ~245 universe + fallback price
OVERLAY = HERE / "board_adp_live_2026.csv"           # REGENERABLE — the only committed output
LOGS_DIR = HERE / "adp_logs"                          # PRIVATE — gitignored
LEDGER = LOGS_DIR / "refresh_ledger.jsonl"

BOARD_SEASON = 2026
MIN_PULL_PLAYERS = 150                                # healthy-pull floor; abort below this
MIN_UNIVERSE = 200                                    # board-universe floor (was a bare assert)

# ─────────────────────────── COVERAGE FLOORS ──────────────────────────────────
# COVERAGE = matched / len(universe). Pull size is NOT the denominator: a 245-row pull
# that matches nothing is a 0%-coverage run, and it used to publish.
#
# EVIDENCE (all of it — there is no observed failure to fit against):
#   * every successful ledger row to date: pull_players=245, matched=180 against the
#     then-180-player board universe = 180/180 = 100% coverage;
#   * the current measured run: 245/245 = 100% overall, and 100% at every position —
#     QB 33/33, RB 76/76, TE 35/35, WR 101/101 (universe composition verified from the
#     frozen season dataset: WR 101 + RB 76 + TE 35 + QB 33 = 245).
#
# So the data contains ZERO misses. You cannot estimate a miss rate from that, and you
# must not invent one. What you CAN do is bound it: for k = n successes out of n, the
# exact one-sided Clopper–Pearson lower bound on the true per-player match probability
# at confidence c is p_lo = (1 - c)^(1/n). At c = 0.99 that is 0.9814 for n = 245.
#
# The floor is then p_lo minus a run-to-run noise allowance of SIGMAS binomial standard
# deviations evaluated AT p_lo (the pessimistic end of the interval), rounded DOWN to
# the nearest GRANULARITY, and never above the collapse-catching ABSOLUTE_MIN:
#
#     floor(n) = max(ABSOLUTE_MIN, floor_to(GRANULARITY, p_lo - SIGMAS*sqrt(p_lo(1-p_lo)/n)))
#
# Because the bound weakens as n shrinks, each position gets its OWN floor from its own
# n — that is the honest consequence of QB having 33 rows and WR 101, not a tuned knob.
# For the current universe this yields:
#
#     overall n=245  p_lo 0.9814  -4sd -> 0.9468  ->  floor 0.90
#     QB      n=33   p_lo 0.8697  -4sd -> 0.6354  ->  floor 0.60
#     RB      n=76   p_lo 0.9412  -4sd -> 0.8333  ->  floor 0.80
#     TE      n=35   p_lo 0.8767  -4sd -> 0.6544  ->  floor 0.65
#     WR      n=101  p_lo 0.9554  -4sd -> 0.8733  ->  floor 0.85
#
# Does it catch a collapse? A schema change that matches nothing scores 0% overall and
# 0% at every position — caught many times over. Even a SINGLE position collapsing to
# zero is caught twice: by its own floor, and by the overall floor (losing QB alone,
# the smallest position, drops overall coverage to 232/245 = 0.865 < 0.90).
#
# Does it false-abort on churn? Every observed run is at 100%, which clears every floor
# by 10-40 points. Even at the pessimistic p_lo the floor sits 4 binomial sigmas below
# the mean, i.e. a ~3e-5 per-position false-abort rate per run. The floors are one-sided
# by design: they exist to catch a break, not to police normal Sleeper turnover.
#
# Recompute (do not hand-edit) if the board universe is resized — coverage_floor() is
# called with the LIVE n, and FROZEN_FLOORS below pins today's values for the tests.
COVERAGE_CONFIDENCE = 0.99      # one-sided Clopper–Pearson confidence for p_lo
COVERAGE_SIGMAS = 4.0           # run-to-run binomial noise allowance below p_lo
COVERAGE_GRANULARITY = 0.05     # round the floor DOWN to this step
COVERAGE_ABSOLUTE_MIN = 0.50    # a floor below this would stop catching a collapse
FROZEN_FLOORS = {"overall": 0.90, "QB": 0.60, "RB": 0.80, "TE": 0.65, "WR": 0.85}


def coverage_floor(n: int) -> float:
    """Minimum acceptable matched/n for a group of size n. See COVERAGE FLOORS above."""
    if n <= 0:
        return COVERAGE_ABSOLUTE_MIN
    p_lo = (1.0 - COVERAGE_CONFIDENCE) ** (1.0 / n)
    allowance = COVERAGE_SIGMAS * math.sqrt(p_lo * (1.0 - p_lo) / n)
    stepped = math.floor((p_lo - allowance) / COVERAGE_GRANULARITY) * COVERAGE_GRANULARITY
    return max(COVERAGE_ABSOLUTE_MIN, round(stepped, 4))


# In-season guard: on/after this date a scheduled run pauses (option i). Override with
def _season_start() -> date:
    return board_refresh_season_start()


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
    """Write via a same-directory temp file + os.replace, so a reader never sees a
    half-written overlay and a failed write cannot truncate the previous one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    os.close(fd)
    try:
        df.to_csv(tmp, index=False)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_board_universe() -> pd.DataFrame:
    """The fixed board universe: every player with a 2026 Sleeper ADP in the frozen season
    dataset (~245). Columns: player_id, player, position, adp_frozen (the frozen fallback price)."""
    ds = pd.read_csv(DATASET, usecols=["player_id", "season", "player", "position", "adp_half_ppr"])
    u = ds[(ds.season == BOARD_SEASON) & ds.adp_half_ppr.notna()].drop_duplicates("player_id")
    return u[["player_id", "player", "position", "adp_half_ppr"]] \
             .rename(columns={"adp_half_ppr": "adp_frozen"}).reset_index(drop=True)


OVERLAY_CORE_COLS = ["player_id", "adp_half_ppr", "adp_pos_rank", "refreshed_at"]
OVERLAY_META_COLS = ["position", "adp_source", "adp_matched"]


def build_overlay_full(universe: pd.DataFrame, fresh: pd.DataFrame, source_date: str):
    """Refresh every universe player's price from a live pull, keeping the row set FIXED.
    Fresh price where the player matches by (normalized name, position); else the frozen
    fallback — so the overlay is complete and stateless, never partial.

    Returns (overlay, coverage). The overlay carries per-row provenance on top of the
    four core columns: `adp_source` ("fresh" | "frozen") and `adp_matched` (bool) say,
    for every published row, whether today's price came from today's pull or is a
    carried-forward frozen fallback — the thing a stale overlay used to hide behind a
    fresh `refreshed_at` stamp. `coverage` is the input to the gate in check_coverage().
    """
    u = universe.copy()
    u["nn"] = u["player"].map(nmz)
    f = fresh.copy()
    f["nn"] = f["player"].map(nmz)
    fresh_adp = f.drop_duplicates(["nn", "position"])[["nn", "position", "adp_half_ppr"]] \
                 .rename(columns={"adp_half_ppr": "adp_fresh"})
    m = u.merge(fresh_adp, on=["nn", "position"], how="left")
    m["adp_matched"] = m["adp_fresh"].notna()
    m["adp_source"] = m["adp_matched"].map({True: "fresh", False: "frozen"})
    matched = int(m["adp_matched"].sum())
    m["adp_half_ppr"] = m["adp_fresh"].where(m["adp_fresh"].notna(), m["adp_frozen"])
    # deterministic within-position ADP rank over the fixed universe (1 = lowest ADP)
    m = m.sort_values(["adp_half_ppr", "player_id"]).reset_index(drop=True)
    m["adp_pos_rank"] = m.groupby("position").cumcount() + 1
    m["refreshed_at"] = source_date
    overlay = m[OVERLAY_CORE_COLS + OVERLAY_META_COLS] \
                .sort_values("player_id").reset_index(drop=True)

    by_position = {}
    for pos, grp in m.groupby("position"):
        n = int(len(grp))
        k = int(grp["adp_matched"].sum())
        by_position[str(pos)] = {"n": n, "matched": k, "coverage": k / n if n else 0.0,
                                 "floor": coverage_floor(n)}
    n_all = int(len(m))
    coverage = {
        "n": n_all,
        "matched": matched,
        "coverage": matched / n_all if n_all else 0.0,
        "floor": coverage_floor(n_all),
        "by_position": by_position,
    }
    return overlay, coverage


def build_overlay(universe: pd.DataFrame, fresh: pd.DataFrame, source_date: str):
    """Back-compatible view of build_overlay_full: the four core columns + the matched
    count, i.e. exactly what this function returned before the coverage gate existed."""
    overlay, coverage = build_overlay_full(universe, fresh, source_date)
    return overlay[OVERLAY_CORE_COLS].copy(), coverage["matched"]


def check_coverage(coverage: dict) -> list[str]:
    """Return a list of human-readable floor breaches; empty means the run may publish.

    Overall AND every position must clear its own floor — a position can collapse while
    the overall number still looks survivable, so the per-position check is not
    redundant with the overall one.
    """
    failures = []
    if coverage["coverage"] < coverage["floor"]:
        failures.append(
            f"overall {coverage['matched']}/{coverage['n']} = "
            f"{coverage['coverage']:.1%} < floor {coverage['floor']:.0%}"
        )
    for pos, s in sorted(coverage["by_position"].items()):
        if s["coverage"] < s["floor"]:
            failures.append(
                f"{pos} {s['matched']}/{s['n']} = {s['coverage']:.1%} < floor {s['floor']:.0%}"
            )
    return failures


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

    # --- fixed board universe (frozen, read only) + fresh-ADP overlay over ALL of it ---
    universe = load_board_universe()
    if len(universe) < MIN_UNIVERSE:
        reason = (f"aborted: board universe is {len(universe)} rows, expected ~245 "
                  f"(2026 Sleeper-ADP players)")
        print(reason)
        _append_ledger({"run_ts": run_ts, "source_date": source_date, "status": reason,
                        "pull_players": int(len(fresh)), "matched": None,
                        "coverage": None, "coverage_by_position": None,
                        "mean_abs_rank_change": None, "movers": []})
        return 1

    overlay, coverage = build_overlay_full(universe, fresh, source_date)
    matched = coverage["matched"]
    cov_by_pos = {p: round(s["coverage"], 4) for p, s in coverage["by_position"].items()}

    # --- COVERAGE GATE: validate BEFORE any write ---------------------------------
    # A pull can be the right SIZE and still match nothing (schema change, renamed
    # fields, a different id namespace). That published a 100%-stale overlay stamped
    # with today's date. Nothing is written unless overall AND every position clear
    # their floor; on failure the PREVIOUS overlay is left exactly as it is on disk.
    failures = check_coverage(coverage)
    if failures:
        reason = "aborted: coverage below floor (" + "; ".join(failures) + ")"
        print(reason)
        print(f"  nothing written; {OVERLAY.name} left untouched")
        _append_ledger({"run_ts": run_ts, "source_date": source_date, "status": reason,
                        "pull_players": int(len(fresh)), "matched": matched,
                        "coverage": round(coverage["coverage"], 4),
                        "coverage_by_position": cov_by_pos,
                        "mean_abs_rank_change": None, "movers": []})
        return 1

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
            names = universe.set_index("player_id")[["player", "position"]]
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
                    "coverage": round(coverage["coverage"], 4),
                    "coverage_by_position": cov_by_pos,
                    "mean_abs_rank_change": mean_abs, "movers": movers})

    pos_str = ", ".join(f"{p} {s['matched']}/{s['n']}"
                        for p, s in sorted(coverage["by_position"].items()))
    print(f"refresh OK: {matched}/{len(universe)} matched to fresh ADP "
          f"({coverage['coverage']:.1%}, floor {coverage['floor']:.0%}); {pos_str}; "
          f"source {source_date}; mean|Δrank| {mean_abs}; "
          f"wrote {OVERLAY.name} + snapshot + ledger row")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
