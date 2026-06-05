"""Hermetic tests for the draft-board ranking logic (no network, no model loads).

These lock the shipped behavior of `build_draft_board.py`:
  - the blend weight constant (changing it should be a deliberate, re-validated act)
  - VOR (value over replacement) math
  - the ADP/model blend ranking, NaN handling, and value/reach gap
  - the output CSV carries exactly the columns app.py's Draft Board tab reads

Run:  python fantasy/seasonal_projections/test_draft_board.py
   or pytest fantasy/seasonal_projections/test_draft_board.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_draft_board as bb
import rookie_features as rf
import board_view as bv


# ── board_view: display ranks must be internally consistent (the QB34 bug) ────
def test_display_ranks_overall_positional_consistent():
    # mixed positions; vor sets the order. positional rank MUST agree with overall.
    pool = pd.DataFrame({
        "player": list("ABCDEF"),
        "position": ["QB", "QB", "RB", "RB", "WR", "QB"],
        "vor": [100.0, 90.0, 80.0, 70.0, 60.0, 50.0],
        "adp_overall_rank": [1.0, 5.0, 2.0, 6.0, 3.0, 8.0],
    })
    d = bv.add_display_ranks(pool)
    # overall ranks are dense 1..n over the whole pool
    assert sorted(d["model_ovr"]) == [1, 2, 3, 4, 5, 6]
    # positional rank == the within-position rank of the overall rank -> no contradiction
    derived = d.groupby("position")["model_ovr"].rank(method="min")
    assert (d["model_posrk"] == derived).all()
    # a position's worst rank can't exceed how many of that position are in the pool
    counts = d["position"].value_counts()
    assert (d["model_posrk"] <= d["position"].map(counts)).all()
    # value = adp positional rank - model positional rank
    assert (d["value_disp"] == d["adp_posrk"] - d["model_posrk"]).all()


def test_blend_proj_tracks_sleeper_and_falls_back():
    # blended projection = 0.2*our + 0.5*sleeper renormalized; with Sleeper missing -> our model.
    pool = pd.DataFrame({
        "position": ["QB", "QB"], "vor": [10.0, 9.0], "adp_overall_rank": [2.0, 1.0],
        "projected_total":      [284.0, 274.0],   # our model: A > B
        "sleeper_pts_half_ppr": [310.0, 361.0],   # Sleeper: B >> A  (the Hurts/Allen shape)
    })
    d = bv.add_display_ranks(pool)
    a, b = d.loc[0, "blend_proj"], d.loc[1, "blend_proj"]
    # Sleeper dominates (0.714 weight) -> B's blended projection should exceed A's, matching ADP/Sleeper
    assert b > a, "blend_proj should follow Sleeper's heavier weight (B > A)"
    assert abs(a - (0.2 * 284 + 0.5 * 310) / 0.7) < 1e-6   # exact renormalized weighting
    # Sleeper missing -> falls back to our model's points
    pool2 = pd.DataFrame({"position": ["RB"], "vor": [5.0], "adp_overall_rank": [1.0],
                          "projected_total": [200.0], "sleeper_pts_half_ppr": [np.nan]})
    assert bv.add_display_ranks(pool2).loc[0, "blend_proj"] == 200.0


def test_pred_is_rank_of_proj_so_they_never_contradict():
    # Pred must be exactly the rank of Proj Pts (blend_proj), within position and overall,
    # so a higher projection is ALWAYS a better rank (the Lamar/Hurts complaint).
    pool = pd.DataFrame({
        "player": list("ABCDE"),
        "position": ["QB", "QB", "QB", "RB", "RB"],
        "vor": [10.0, 9.0, 8.0, 7.0, 6.0],
        "adp_overall_rank": [3.0, 1.0, 2.0, 5.0, 4.0],     # ADP disagrees with the projection
        "projected_total":      [284.0, 274.0, 290.0, 200.0, 210.0],
        "sleeper_pts_half_ppr": [310.0, 361.0, 300.0, 180.0, 220.0],
    })
    d = bv.add_display_ranks(pool)
    # overall: Pred is exactly the rank of blend_proj
    assert (d["pred_ovr"] == d["blend_proj"].rank(ascending=False, method="min")).all()
    # positional: within each position, higher blend_proj => lower (better) pred_posrk, no inversions
    for pos, g in d.groupby("position"):
        gg = g.sort_values("pred_posrk")
        proj = gg["blend_proj"].tolist()
        assert proj == sorted(proj, reverse=True), f"{pos}: Proj Pts not monotonic with Pred"


def test_display_ranks_actuals_and_blanks_sort_bottom():
    pool = pd.DataFrame({
        "player": ["A", "B", "C"], "position": ["RB", "RB", "RB"],
        "vor": [80.0, 70.0, 60.0], "adp_overall_rank": [2.0, 6.0, 9.0],
        "actual_total": [200.0, np.nan, 150.0],   # B didn't play
    })
    d = bv.add_display_ranks(pool)
    assert d.loc[0, "actual_ovr"] == 1 and d.loc[2, "actual_ovr"] == 2
    assert pd.isna(d.loc[1, "actual_ovr"]) and pd.isna(d.loc[1, "actual_posrk"])  # blank -> sorts last


def test_board_csv_display_ranks_consistent_real():
    csv = Path(__file__).resolve().parent / "draft_board_2025.csv"
    if not csv.exists():
        print("  (skip) draft_board_2025.csv not built yet")
        return
    df = pd.read_csv(csv)
    for c in ("blend_rank", "vor", "adp_overall_rank", "target_ppg", "target_games"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["actual_total"] = df["target_ppg"] * df["target_games"]
    pool = df[df["blend_rank"].notna()].copy()
    d = bv.add_display_ranks(pool)
    counts = d["position"].value_counts()
    # the exact bug the user caught: no player ranked worse than the count of their position
    assert (d["model_posrk"] <= d["position"].map(counts)).all(), "positional rank exceeds pool position count"
    assert (d["model_posrk"] == d.groupby("position")["model_ovr"].rank(method="min")).all(), \
        "positional rank inconsistent with overall rank"
    print(f"  ok  real board display-ranks consistent ({len(d)} drafted, "
          f"{int(counts.get('QB', 0))} QBs -> max QB rank {int(d.loc[d.position=='QB','model_posrk'].max())})")


# ── rookie_features.parse_ht (hermetic; the combine join itself needs network) ─
def test_parse_ht():
    assert rf.parse_ht("6-4") == 76
    assert rf.parse_ht("5-10") == 70
    assert np.isnan(rf.parse_ht("NA"))
    assert np.isnan(rf.parse_ht(None))
    assert np.isnan(rf.parse_ht("6"))          # no dash -> NaN, not a crash


def test_rookie_feats_include_combine():
    assert "forty" in rf.ROOKIE_FEATS and "wt" in rf.ROOKIE_FEATS
    assert rf.CAT == ["position"]


# ── shipped-weight lock ──────────────────────────────────────────────────────
def test_blend_weights_are_locked():
    # our 0.2 / ADP 0.3 / Sleeper 0.5 confirmed via fine sweep + leave-one-season-out
    # (three_way_blend_test.py). If these change, re-run that experiment and update
    # the expected values deliberately. Weights must sum to 1.
    w = bb.BLEND_WEIGHTS
    assert w == {"our": 0.20, "adp": 0.30, "sleeper": 0.50}, \
        f"BLEND_WEIGHTS changed to {w} -- re-validate via three_way_blend_test.py"
    assert abs(sum(w.values()) - 1.0) < 1e-9, "blend weights must sum to 1"


# ── VOR: total minus the Nth-ranked total at the position ────────────────────
def test_vor_replacement_math():
    saved = bb.REPL
    try:
        bb.REPL = {"RB": 3}
        d = pd.DataFrame({"position": ["RB"] * 5,
                          "projected_total": [100.0, 90.0, 80.0, 70.0, 60.0]})
        vor = bb._vor(d, "projected_total")
        # 3rd-ranked total is 80 -> vor = total - 80
        assert list(vor) == [20.0, 10.0, 0.0, -10.0, -20.0]
    finally:
        bb.REPL = saved


def test_vor_fallback_when_fewer_than_n_players():
    saved = bb.REPL
    try:
        bb.REPL = {"RB": 10}          # only 2 players, n=10 -> use the last (lowest) total
        d = pd.DataFrame({"position": ["RB", "RB"], "projected_total": [100.0, 40.0]})
        vor = bb._vor(d, "projected_total")
        assert list(vor) == [60.0, 0.0]   # replacement = 40 (last available)
    finally:
        bb.REPL = saved


# ── blend ranking + value gap + NaN handling ─────────────────────────────────
def _toy_board():
    # 4 drafted RBs + 1 undrafted (no ADP). our rank by vor, market by adp_overall_rank,
    # plus Sleeper's season projection (higher = better).
    return pd.DataFrame({
        "position":             ["RB", "RB", "RB", "RB", "RB"],
        "vor":                  [100.0, 90.0, 80.0, 70.0, 50.0],   # A B C D E ; our_r A1 B2 C3 D4
        "adp_overall_rank":     [1.0, 4.0, 2.0, 3.0, np.nan],      # adp_r A1 C2 D3 B4
        "adp_pos_rank":         [1.0, 4.0, 2.0, 3.0, np.nan],
        "sleeper_pts_half_ppr": [300.0, 250.0, 200.0, 150.0, np.nan],  # slp_r A1 B2 C3 D4
    }, index=["A", "B", "C", "D", "E"])


def test_make_board_blend_ranking():
    out = bb.make_board(_toy_board())
    # blend = 0.2*our + 0.3*adp + 0.5*sleeper:
    #   A=0.2(1)+0.3(1)+0.5(1)=1.0  B=0.2(2)+0.3(4)+0.5(2)=2.6
    #   C=0.2(3)+0.3(2)+0.5(3)=2.7  D=0.2(4)+0.3(3)+0.5(4)=3.7
    # -> A1, B2, C3, D4 (Sleeper + our model pull B up despite its bad ADP)
    assert out.loc["A", "blend_rank"] == 1
    assert out.loc["B", "blend_rank"] == 2
    assert out.loc["C", "blend_rank"] == 3
    assert out.loc["D", "blend_rank"] == 4
    # the undrafted player gets NaN blend (excluded from the recommended order)
    assert pd.isna(out.loc["E", "blend_rank"])
    assert pd.isna(out.loc["E", "blend_score"])


def test_make_board_blend_falls_back_without_sleeper():
    # if the Sleeper column is absent, the sleeper term defers to ADP (no crash)
    toy = _toy_board().drop(columns=["sleeper_pts_half_ppr"])
    out = bb.make_board(toy)
    assert out.blend_rank.notna().sum() == 4 and pd.isna(out.loc["E", "blend_rank"])


def test_make_board_value_gap_sign():
    out = bb.make_board(_toy_board())
    # value_gap = adp_pos_rank - our_pos_rank ; positive = we like more than market
    assert out.loc["B", "value_gap"] == 2     # ADP RB4, our RB2 -> +2 value
    assert out.loc["C", "value_gap"] == -1    # ADP RB2, our RB3 -> -1 reach
    assert pd.isna(out.loc["E", "value_gap"])  # no ADP -> no gap


def test_make_board_blend_pos_rank_consistent():
    out = bb.make_board(_toy_board())
    # single position, so blend_pos_rank must equal blend_rank for the drafted four
    drafted = out[out.blend_rank.notna()]
    assert (drafted.blend_pos_rank == drafted.blend_rank).all()


# ── output CSV carries the columns app.py's Draft Board tab depends on ───────
def test_board_csv_has_columns_app_reads():
    csv = Path(__file__).resolve().parent / "draft_board_2025.csv"
    if not csv.exists():
        print("  (skip) draft_board_2025.csv not built yet")
        return
    df = pd.read_csv(csv)
    needed = ["player", "position", "team", "ppg_pred", "games_pred", "projected_total", "vor",
              "our_pos_rank", "blend_rank", "blend_pos_rank",
              "adp_pos_rank", "adp_overall_rank", "value_gap", "sleeper_pts_half_ppr",
              "target_ppg", "target_games"]   # incl. cols the dashboard results view reads
    missing = [c for c in needed if c not in df.columns]
    assert not missing, f"draft board CSV missing columns app.py reads: {missing}"
    # blended rows must have a positional rank too (app builds 'Pos' from it)
    ranked = df[df.blend_rank.notna()]
    assert ranked.blend_pos_rank.notna().all(), "blend_rank present but blend_pos_rank missing"
    print(f"  ok  board CSV columns ({len(df):,} rows, {int(ranked.shape[0])} ranked)")


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} tests passed")


if __name__ == "__main__":
    _run()
