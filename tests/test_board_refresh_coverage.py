"""Coverage-gate tests for the 2026 board ADP refresh. Fully hermetic: no network, and
every path (`OVERLAY`, `LOGS_DIR`, `LEDGER`) is redirected into tmp_path, so the live
published overlay `board_adp_live_2026.csv` and `adp_logs/` are never read or written.

The defect these lock down: the refresh validated only the SIZE of the pull
(`MIN_PULL_PLAYERS=150`) and the size of the board universe. `matched` was computed and
written to the ledger but gated NOTHING, so a well-formed 245-row pull that matched none
of the board still published a 100%-stale overlay stamped with today's date.

Run:  python -m pytest tests/test_board_refresh_coverage.py -q
"""
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

os.environ["APP_OFFLINE"] = "1"

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "fantasy" / "seasonal_projections"))

import refresh_board_adp as rb  # noqa: E402

# The real universe composition, verified from the frozen season dataset.
REAL_N = {"QB": 33, "RB": 76, "TE": 35, "WR": 101}


# ── floor derivation ──────────────────────────────────────────────────────────
def test_frozen_floors_match_the_documented_derivation():
    """The floors in the module docstring must be exactly what coverage_floor()
    produces for the real universe sizes — no hand-edited numbers."""
    assert rb.coverage_floor(sum(REAL_N.values())) == pytest.approx(rb.FROZEN_FLOORS["overall"])
    for pos, n in REAL_N.items():
        assert rb.coverage_floor(n) == pytest.approx(rb.FROZEN_FLOORS[pos]), pos
    assert rb.FROZEN_FLOORS == {"overall": 0.90, "QB": 0.60, "RB": 0.80, "TE": 0.65, "WR": 0.85}


def test_floor_is_monotone_in_n_and_bounded():
    prev = 0.0
    for n in (5, 10, 33, 35, 76, 101, 245, 500, 2000):
        f = rb.coverage_floor(n)
        assert rb.COVERAGE_ABSOLUTE_MIN <= f < 1.0
        assert f >= prev, "a larger group must not get a weaker floor"
        prev = f
    assert rb.coverage_floor(0) == rb.COVERAGE_ABSOLUTE_MIN


def test_floors_catch_a_total_collapse_and_a_single_position_collapse():
    total = sum(REAL_N.values())
    assert 0.0 < rb.FROZEN_FLOORS["overall"], "a 0% run must breach the overall floor"
    for pos, n in REAL_N.items():
        # that position alone goes to zero, every other position stays perfect
        overall = (total - n) / total
        assert overall < rb.FROZEN_FLOORS["overall"], (
            f"losing all of {pos} ({n}/{total}) must breach the overall floor too")
        assert 0.0 < rb.FROZEN_FLOORS[pos]


def test_floors_leave_headroom_for_the_observed_100_percent_runs():
    """Every observed run — the two ledger rows at 180/180 and the current 245/245 —
    is at 100%, so no floor may sit at or above 1.0."""
    for f in rb.FROZEN_FLOORS.values():
        assert f <= 0.90, "a floor this tight would fire on ordinary churn"


# ── fixtures ──────────────────────────────────────────────────────────────────
def _universe(counts=None):
    counts = counts or REAL_N
    rows = []
    for pos, n in counts.items():
        for i in range(n):
            rows.append({"player_id": f"{pos}{i:03d}", "player": f"{pos} Player {i}",
                         "position": pos, "adp_frozen": float(10 + i)})
    return pd.DataFrame(rows)


def _fresh_from(universe, keep_mask=None, shift=1.0):
    """A live pull that matches the given subset of the universe (plus filler rows so
    the pull always clears MIN_PULL_PLAYERS)."""
    u = universe if keep_mask is None else universe[keep_mask]
    df = pd.DataFrame({"player": u["player"], "position": u["position"],
                       "adp_half_ppr": u["adp_frozen"] + shift})
    filler = pd.DataFrame({"player": [f"Filler {i}" for i in range(200)],
                           "position": ["WR"] * 200,
                           "adp_half_ppr": [200.0 + i for i in range(200)]})
    return pd.concat([df, filler], ignore_index=True)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Redirect every write target into tmp_path and stub the network + date guard."""
    overlay = tmp_path / "board_adp_live_2026.csv"
    logs = tmp_path / "adp_logs"
    monkeypatch.setattr(rb, "OVERLAY", overlay)
    monkeypatch.setattr(rb, "LOGS_DIR", logs)
    monkeypatch.setattr(rb, "LEDGER", logs / "refresh_ledger.jsonl")
    monkeypatch.setattr(rb, "_season_start", lambda: date(2099, 1, 1))
    monkeypatch.setattr(rb, "load_players", lambda: {})
    monkeypatch.setattr(sys, "argv", ["refresh_board_adp.py"])
    # A pre-existing published overlay, so "leave the previous one untouched" is testable.
    prior = pd.DataFrame({"player_id": ["QB000"], "adp_half_ppr": [9.9],
                          "adp_pos_rank": [1], "refreshed_at": ["2026-07-13"],
                          "position": ["QB"], "adp_source": ["fresh"],
                          "adp_matched": [True]})
    prior.to_csv(overlay, index=False)
    return {"overlay": overlay, "logs": logs, "prior_sha": _sha(overlay),
            "prior_bytes": overlay.read_bytes()}


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _ledger_rows(logs: Path):
    f = logs / "refresh_ledger.jsonl"
    if not f.exists():
        return []
    return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]


def _run(monkeypatch, universe, fresh):
    monkeypatch.setattr(rb, "load_board_universe", lambda: universe)
    monkeypatch.setattr(rb, "fetch_season", lambda season, players: fresh)
    return rb.main()


# ── the three required gate tests ─────────────────────────────────────────────
def test_low_overall_coverage_aborts_and_leaves_the_prior_overlay_byte_identical(
        sandbox, monkeypatch):
    u = _universe()
    # a pull of the right SIZE that matches nothing at all — the schema-change case
    fresh = pd.DataFrame({"player": [f"Ghost {i}" for i in range(245)],
                          "position": ["WR"] * 245,
                          "adp_half_ppr": [float(i + 1) for i in range(245)]})
    assert len(fresh) >= rb.MIN_PULL_PLAYERS, "premise: the OLD size check passes"

    rc = _run(monkeypatch, u, fresh)

    assert rc == 1, "a collapsed-coverage run must exit nonzero"
    assert sandbox["overlay"].read_bytes() == sandbox["prior_bytes"]
    assert _sha(sandbox["overlay"]) == sandbox["prior_sha"]
    assert not list(sandbox["logs"].glob("board_adp_*.csv")), "no dated snapshot on abort"
    rows = _ledger_rows(sandbox["logs"])
    assert rows and rows[-1]["status"].startswith("aborted: coverage below floor")
    assert rows[-1]["coverage"] == 0.0
    assert rows[-1]["pull_players"] == 245, "the pull was big enough; coverage is what failed"


def test_low_single_position_coverage_aborts_even_when_overall_passes(sandbox, monkeypatch):
    u = _universe()
    # Drop 20 of 33 QBs: QB 13/33 = 39.4% < 0.60, while overall 225/245 = 91.8% >= 0.90.
    qb_rows = u.index[u["position"] == "QB"][:20]
    keep = ~u.index.isin(qb_rows)
    fresh = _fresh_from(u, keep)

    overall = keep.sum() / len(u)
    assert overall >= rb.FROZEN_FLOORS["overall"], (
        f"premise: overall {overall:.1%} must still clear the overall floor")

    rc = _run(monkeypatch, u, fresh)

    assert rc == 1, "a single collapsed position must abort even with a healthy overall"
    assert sandbox["overlay"].read_bytes() == sandbox["prior_bytes"]
    rows = _ledger_rows(sandbox["logs"])
    assert rows[-1]["status"].startswith("aborted: coverage below floor")
    assert "QB" in rows[-1]["status"]
    assert rows[-1]["coverage_by_position"]["QB"] < rb.FROZEN_FLOORS["QB"]
    assert rows[-1]["coverage_by_position"]["WR"] == 1.0


def test_healthy_run_writes_the_overlay_snapshot_and_ledger(sandbox, monkeypatch):
    u = _universe()
    fresh = _fresh_from(u)

    rc = _run(monkeypatch, u, fresh)

    assert rc == 0
    out = pd.read_csv(sandbox["overlay"])
    assert len(out) == len(u) == 245
    assert list(out.columns) == rb.OVERLAY_CORE_COLS + rb.OVERLAY_META_COLS
    assert out["adp_source"].eq("fresh").all()
    assert out["adp_matched"].all()
    assert sandbox["overlay"].read_bytes() != sandbox["prior_bytes"], "it must have published"
    snaps = list(sandbox["logs"].glob("board_adp_*.csv"))
    assert len(snaps) == 1, "one dated private snapshot per run day"
    rows = _ledger_rows(sandbox["logs"])
    assert rows[-1]["status"] == "success"
    assert rows[-1]["coverage"] == 1.0
    assert rows[-1]["coverage_by_position"] == {p: 1.0 for p in REAL_N}


# ── per-row provenance + partial churn ────────────────────────────────────────
def test_partial_but_healthy_churn_still_publishes_and_labels_each_row(sandbox, monkeypatch):
    u = _universe()
    # Miss 5 WRs (WR 96/101 = 95.0% >= 0.85) and 4 RBs (RB 72/76 = 94.7% >= 0.80).
    miss = list(u.index[u["position"] == "WR"][:5]) + list(u.index[u["position"] == "RB"][:4])
    keep = ~u.index.isin(miss)
    fresh = _fresh_from(u, keep)

    rc = _run(monkeypatch, u, fresh)

    assert rc == 0, "ordinary churn must NOT false-abort"
    out = pd.read_csv(sandbox["overlay"])
    assert int(out["adp_matched"].sum()) == len(u) - len(miss)
    assert out["adp_source"].value_counts().to_dict() == {"fresh": len(u) - len(miss),
                                                          "frozen": len(miss)}
    frozen_rows = out[out["adp_source"] == "frozen"]
    assert not frozen_rows.empty
    assert frozen_rows["adp_matched"].eq(False).all()


def test_metadata_marks_carried_forward_rows_so_a_stale_overlay_is_visible():
    u = _universe({"QB": 4})
    fresh = pd.DataFrame({"player": ["QB Player 0"], "position": ["QB"],
                          "adp_half_ppr": [1.0]})
    overlay, cov = rb.build_overlay_full(u, fresh, "2026-08-03")
    assert set(overlay["adp_source"]) == {"fresh", "frozen"}
    assert overlay.loc[overlay["player_id"] == "QB000", "adp_source"].iloc[0] == "fresh"
    assert int(overlay["adp_matched"].sum()) == 1
    # refreshed_at is fresh on EVERY row -- that is exactly why adp_source is needed.
    assert overlay["refreshed_at"].eq("2026-08-03").all()
    assert cov["matched"] == 1 and cov["n"] == 4


def test_build_overlay_keeps_its_original_two_value_signature_and_schema():
    """The pre-existing suite unpacks (overlay, matched) and asserts the 4-column
    schema; the metadata must not leak into that view."""
    u = _universe({"RB": 3})
    fresh = _fresh_from(u)
    overlay, matched = rb.build_overlay(u, fresh, "2026-08-03")
    assert list(overlay.columns) == rb.OVERLAY_CORE_COLS
    assert matched == 3


# ── check_coverage in isolation ───────────────────────────────────────────────
def test_check_coverage_reports_every_breach():
    cov = {
        "n": 245, "matched": 100, "coverage": 100 / 245, "floor": 0.90,
        "by_position": {
            "QB": {"n": 33, "matched": 3, "coverage": 3 / 33, "floor": 0.60},
            "RB": {"n": 76, "matched": 76, "coverage": 1.0, "floor": 0.80},
        },
    }
    failures = rb.check_coverage(cov)
    assert len(failures) == 2
    assert any(f.startswith("overall") for f in failures)
    assert any(f.startswith("QB") for f in failures)
    assert not any(f.startswith("RB") for f in failures)


def test_check_coverage_passes_a_clean_run():
    cov = {"n": 245, "matched": 245, "coverage": 1.0, "floor": 0.90,
           "by_position": {p: {"n": n, "matched": n, "coverage": 1.0,
                               "floor": rb.FROZEN_FLOORS[p]} for p, n in REAL_N.items()}}
    assert rb.check_coverage(cov) == []


# ── the production overlay must never be a test target ────────────────────────
def test_tests_never_point_at_the_published_overlay(sandbox):
    assert str(sandbox["overlay"]) != str(
        _ROOT / "fantasy" / "seasonal_projections" / "board_adp_live_2026.csv")
    assert "adp_logs" not in str(sandbox["logs"].parent)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
