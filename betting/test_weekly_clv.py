"""Tests for weekly_clv.py + odds_client.snapshot_cmd (review L-15/L-16/L-2, R32-R35).

Hermetic: oc.TRACKER is ALWAYS monkeypatched to a temp file (the real tracker is an
append-only forward log — never touched); fetch_lines is stubbed. Style follows
test_historical_clv.py. Run from betting/ (sibling imports).
"""
import types

import pandas as pd
import pytest

import odds_client as oc
import weekly_clv as wc


def _mini_tracker(tmp_path):
    """Synthetic 3-row tracker: two rows in (2026, wk1), one historical (2025, wk17)
    with the SAME matchup as a current game — the L-16 overwrite hazard row."""
    df = pd.DataFrame({
        "season": [2026, 2026, 2025],
        "week": [1, 1, 17],
        "gameday": ["2026-09-13", "2026-09-13", "2025-12-28"],
        "home_team": ["ATL", "KC", "ATL"],
        "away_team": ["LA", "BUF", "LA"],
        "recommendation": ["HOME (ATL)", "AWAY (BUF)", "HOME (ATL)"],
        "spread_line": [3.0, -1.5, 2.5],
        "pick_line": [float("nan")] * 3,
        "closing_line": [float("nan")] * 3,
        "clv": [float("nan")] * 3,
        "untouched_int": [7, 8, 9],
        "untouched_str": ["a", "b", "c"],
    })
    p = tmp_path / "predictions_tracker.csv"
    df.to_csv(p, index=False)
    return p


def _stub_lines(spread_by_key):
    def fake(_args=None):
        return ({k: {"spread": v, "total": 44.0, "n_books": 5, "date": "2026-09-13",
                     "home_team": k[0], "away_team": k[1]}
                 for k, v in spread_by_key.items()},
                {"remaining": "499", "used": "1"})
    return fake


# ---- L-15 (R32): two consecutive pick snapshots must not crash ----------------
def test_second_pick_snapshot_skips_not_crashes(monkeypatch, tmp_path):
    p = _mini_tracker(tmp_path)
    monkeypatch.setattr(oc, "TRACKER", p)
    monkeypatch.setattr(oc, "fetch_lines", lambda: _stub_lines(
        {("ATL", "LA"): 2.5, ("KC", "BUF"): -1.0})())
    ns = lambda: types.SimpleNamespace(which="pick", season=2026, week=1)
    oc.snapshot_cmd(ns())                       # Tuesday: writes pick_line
    first = pd.read_csv(p)
    assert first.loc[0, "pick_line"] == 2.5
    oc.snapshot_cmd(ns())                       # Thursday: MUST skip, not AttributeError
    second = pd.read_csv(p)
    assert second.loc[0, "pick_line"] == 2.5    # first write wins


def test_force_flag_still_overwrites(monkeypatch, tmp_path):
    p = _mini_tracker(tmp_path)
    monkeypatch.setattr(oc, "TRACKER", p)
    monkeypatch.setattr(oc, "fetch_lines", lambda: _stub_lines({("ATL", "LA"): 2.5})())
    oc.snapshot_cmd(types.SimpleNamespace(which="pick", season=2026, week=1))
    monkeypatch.setattr(oc, "fetch_lines", lambda: _stub_lines({("ATL", "LA"): 3.5})())
    oc.snapshot_cmd(types.SimpleNamespace(which="pick", season=2026, week=1, force=True))
    assert pd.read_csv(p).loc[0, "pick_line"] == 3.5


# ---- L-16 (R33): unscoped snapshot must refuse BEFORE fetch or write ----------
def test_bare_snapshot_refuses_no_fetch_no_write(monkeypatch, tmp_path):
    p = _mini_tracker(tmp_path)
    before = p.read_bytes()
    monkeypatch.setattr(oc, "TRACKER", p)

    def boom():
        raise AssertionError("fetch_lines must NOT be called on an unscoped snapshot")
    monkeypatch.setattr(oc, "fetch_lines", boom)
    with pytest.raises(SystemExit):
        oc.snapshot_cmd(types.SimpleNamespace(which="closing", season=None, week=None))
    assert p.read_bytes() == before             # no write happened


def test_scoped_snapshot_touches_only_scope(monkeypatch, tmp_path):
    p = _mini_tracker(tmp_path)
    monkeypatch.setattr(oc, "TRACKER", p)
    monkeypatch.setattr(oc, "fetch_lines", lambda: _stub_lines(
        {("ATL", "LA"): 2.5, ("KC", "BUF"): -1.0})())
    oc.snapshot_cmd(types.SimpleNamespace(which="closing", season=2026, week=1))
    out = pd.read_csv(p)
    assert out.loc[0, "closing_line"] == 2.5
    # the 2025 wk17 row shares the (ATL, LA) matchup — it must be UNTOUCHED
    assert pd.isna(out.loc[2, "closing_line"])
    assert list(out["untouched_int"]) == [7, 8, 9]
    assert list(out["untouched_str"]) == ["a", "b", "c"]


# ---- L-2 (R34): atomic, integrity-checked write --------------------------------
def test_nontarget_columns_survive_roundtrip(monkeypatch, tmp_path):
    p = _mini_tracker(tmp_path)
    orig = pd.read_csv(p)
    monkeypatch.setattr(oc, "TRACKER", p)
    monkeypatch.setattr(oc, "fetch_lines", lambda: _stub_lines({("KC", "BUF"): -1.0})())
    oc.snapshot_cmd(types.SimpleNamespace(which="pick", season=2026, week=1))
    out = pd.read_csv(p)
    assert list(out.columns) == list(orig.columns)
    assert len(out) == len(orig)
    for c in ["season", "week", "gameday", "home_team", "away_team",
              "recommendation", "spread_line", "untouched_int", "untouched_str"]:
        assert out[c].tolist() == orig[c].tolist(), f"non-target column {c} mutated"
    assert not (p.parent / (p.name + ".tmp")).exists()   # no tmp litter


def test_integrity_assert_blocks_bad_frame(monkeypatch, tmp_path):
    p = _mini_tracker(tmp_path)
    monkeypatch.setattr(oc, "TRACKER", p)
    orig = pd.read_csv(p)
    bad = orig.iloc[:-1].copy()                 # row count changed
    with pytest.raises((SystemExit, ValueError)):
        oc._write_tracker_atomic(bad, orig)
    assert len(pd.read_csv(p)) == len(orig)     # file untouched


# ---- weekly_clv driver behaviors (R35) -----------------------------------------
def test_weekday_auto_mapping(monkeypatch, tmp_path):
    p = _mini_tracker(tmp_path)
    monkeypatch.setattr(oc, "TRACKER", p)
    seen = []
    monkeypatch.setattr(oc, "snapshot_cmd", lambda ns: seen.append(ns))
    for run_date, expect in [("2026-09-08", "pick"),      # Tuesday
                             ("2026-09-10", "pick"),      # Thursday
                             ("2026-09-13", "closing")]:  # Sunday
        monkeypatch.setattr("sys.argv", ["weekly_clv.py", "--date", run_date])
        wc.main()
    assert [s.which for s in seen] == ["pick", "pick", "closing"]
    assert all((s.season, s.week) == (2026, 1) for s in seen)


def test_offseason_noop(monkeypatch, tmp_path):
    p = _mini_tracker(tmp_path)
    monkeypatch.setattr(oc, "TRACKER", p)
    called = []
    monkeypatch.setattr(oc, "snapshot_cmd", lambda ns: called.append(ns))
    monkeypatch.setattr("sys.argv", ["weekly_clv.py", "--date", "2026-03-01"])
    wc.main()
    assert not called                            # no slate in window -> no-op


def test_missing_tracker_noop(monkeypatch, tmp_path):
    monkeypatch.setattr(oc, "TRACKER", tmp_path / "nope.csv")
    called = []
    monkeypatch.setattr(oc, "snapshot_cmd", lambda ns: called.append(ns))
    monkeypatch.setattr("sys.argv", ["weekly_clv.py"])
    wc.main()
    assert not called


def test_current_target_handles_nat(tmp_path):
    df = pd.DataFrame({"season": [2026], "week": [1],
                       "gameday": ["not-a-date"]})
    assert wc.current_target(df, pd.Timestamp("2026-09-08").date()) is None
