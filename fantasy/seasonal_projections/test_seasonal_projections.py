"""Hermetic tests for the seasonal-projections pipeline.

These exercise the pure transformation logic (no network / nflreadpy calls) on
small synthetic frames, so they run anywhere in well under a second. The
network-dependent loaders (load_player_stats, load_snap_counts, rosters,
schedules) are integration steps and are not unit-tested here.

Run:  python fantasy/seasonal_projections/test_seasonal_projections.py
   or pytest fantasy/seasonal_projections/test_seasonal_projections.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _utils import norm_name, ADP_SENTINEL, SKILL_POSITIONS
import build_season_dataset as bsd
import build_2026_board as b26


# ── _utils.norm_name ─────────────────────────────────────────────────────────
def test_norm_name_suffixes_and_accents():
    assert norm_name("Frank Gore Jr.") == "frank gore"
    assert norm_name("Odell Beckham Jr.") == "odell beckham"
    assert norm_name("Robert Griffin III") == "robert griffin"
    assert norm_name("Amon-Ra St. Brown") == "amonra st brown"      # punctuation stripped
    assert norm_name("D'Andre Swift") == "dandre swift"
    assert norm_name("") == ""
    assert norm_name(None) == ""
    # father/son collapse is a known, accepted behavior
    assert norm_name("Frank Gore") == norm_name("Frank Gore Jr.")


def test_constants_sane():
    assert ADP_SENTINEL == 900.0
    assert set(SKILL_POSITIONS) == {"QB", "RB", "WR", "TE"}


# ── reconstruct_missed: fill 0-game seasons in gaps between active seasons ────
def test_reconstruct_missed_fills_only_internal_gaps():
    agg = pd.DataFrame({
        "player_id": ["A", "A", "A", "B", "B"],
        "season":    [2018, 2020, 2021, 2019, 2020],   # A skipped 2019; B consecutive
        "player":    ["Ann"] * 3 + ["Bob"] * 2,
        "position":  ["RB"] * 3 + ["WR"] * 2,
        "team":      ["KC"] * 3 + ["LV"] * 2,
        "norm_name": ["ann"] * 3 + ["bob"] * 2,
        "games":     [16, 15, 14, 17, 16],
        "half_ppr":  [200, 180, 170, 220, 210],
        "targets": [10, 10, 10, 90, 88], "receptions": [8, 8, 8, 70, 68],
        "rec_yards": [60, 60, 60, 900, 880], "rec_air_yards": [80, 80, 80, 1100, 1000],
        "carries": [200, 190, 180, 0, 0], "rush_yards": [900, 880, 800, 0, 0],
        "pass_att": [0, 0, 0, 0, 0], "total_td": [8, 7, 6, 6, 5], "touches": [208, 198, 188, 70, 68],
        "target_share": [.1, .1, .1, .25, .24], "air_yards_share": [.1, .1, .1, .3, .29],
        "rec_epa": [5, 5, 5, 40, 38], "rush_epa": [10, 9, 8, 0, 0],
    })
    out = bsd.reconstruct_missed(agg)
    # Exactly one reconstructed row, for player A season 2019.
    recon = out[out["reconstructed"] == 1]
    assert len(recon) == 1, f"expected 1 reconstructed row, got {len(recon)}"
    r = recon.iloc[0]
    assert r["player_id"] == "A" and r["season"] == 2019
    assert r["games"] == 0 and r["half_ppr"] == 0
    assert r["position"] == "RB"          # carried from player's modal position
    # B has no internal gap -> no reconstruction for B
    assert (out[out["player_id"] == "B"]["reconstructed"] == 0).all()


# ── add_rates: per-game + efficiency, with 0-game rows safely NaN ────────────
def test_add_rates_zero_game_is_nan_not_error():
    full = pd.DataFrame({
        "games": [10, 0], "half_ppr": [120.0, 0.0],
        "targets": [50, 0], "carries": [100, 0], "receptions": [40, 0],
        "touches": [140, 0], "rec_air_yards": [300, 0], "rec_yards": [400, 0],
        "rush_yards": [450, 0], "total_td": [7, 0],
    })
    out = bsd.add_rates(full)
    assert abs(out.loc[0, "ppg"] - 12.0) < 1e-9
    assert np.isnan(out.loc[1, "ppg"])             # 0 games -> NaN, no divide error
    assert abs(out.loc[0, "td_rate"] - 7 / 140) < 1e-9
    assert np.isnan(out.loc[1, "td_rate"])         # 0 touches -> NaN
    assert abs(out.loc[0, "targets_pg"] - 5.0) < 1e-9


# ── build_feature_rows: prior join (gap-aware), flags, targets, soft floor ──
def test_add_snaps_excludes_postseason(monkeypatch):
    full = pd.DataFrame({
        "player_id": ["00-ann"], "norm_name": ["ann"], "season": [2025], "games": [2.0],
        "reconstructed": [0],
    })
    snaps = pd.DataFrame({
        "player": ["Ann", "Ann", "Ann"],
        "pfr_player_id": ["AnnX00", "AnnX00", "AnnX00"],
        "season": [2025, 2025, 2025],
        "week": [1, 2, 19],
        "game_type": ["REG", "REG", "POST"],
        "offense_snaps": [40.0, 50.0, 60.0],
        "offense_pct": [0.5, 0.7, 0.9],
    })
    # snaps now join on a stable id (pfr -> gsis via players), not the normalized name
    players = pd.DataFrame({"pfr_id": ["AnnX00"], "gsis_id": ["00-ann"]})
    monkeypatch.setattr(bsd, "snap",
                        lambda key, *a, **k: players if key == "players" else snaps)
    out = bsd.add_snaps(full)
    assert out.loc[0, "games"] == 2.0
    assert abs(out.loc[0, "snap_share_pg"] - 0.6) < 1e-9


def test_snaps_do_not_collide_on_shared_names(monkeypatch):
    """Two different players sharing a name must NOT inherit each other's snap row."""
    full = pd.DataFrame({
        "player_id": ["00-a", "00-b"], "norm_name": ["mike williams", "mike williams"],
        "season": [2025, 2025], "games": [4.0, 9.0], "reconstructed": [0, 0],
    })
    snaps = pd.DataFrame({
        "player": ["Mike Williams"] * 3,
        "pfr_player_id": ["WillA00", "WillA00", "WillB00"],
        "season": [2025] * 3, "week": [1, 2, 1], "game_type": ["REG"] * 3,
        "offense_snaps": [40.0, 40.0, 10.0], "offense_pct": [0.8, 0.8, 0.2],
    })
    players = pd.DataFrame({"pfr_id": ["WillA00", "WillB00"], "gsis_id": ["00-a", "00-b"]})
    monkeypatch.setattr(bsd, "snap",
                        lambda key, *a, **k: players if key == "players" else snaps)
    out = bsd.add_snaps(full).set_index("player_id")
    assert out.loc["00-a", "games"] == 2.0 and abs(out.loc["00-a", "snap_share_pg"] - 0.8) < 1e-9
    assert out.loc["00-b", "games"] == 1.0 and abs(out.loc["00-b", "snap_share_pg"] - 0.2) < 1e-9


def test_vacated_opportunity_is_team_specific_and_zero_complete():
    prior = pd.DataFrame({
        "player_id": ["stay", "move", "leave", "other"],
        "team": ["KC", "KC", "KC", "ARI"],
        "target_share": [0.30, 0.20, 0.10, 0.40],
        "carries": [60.0, 30.0, 10.0, 100.0],
    })
    roster = pd.DataFrame({
        "player_id": ["stay", "move", "other", "rookie"],
        "team": ["KC", "BUF", "AZ", "KC"],      # "AZ" must normalize onto "ARI"
    })
    vac = b26.compute_vacated_opportunity(prior, roster).set_index("team")
    assert abs(vac.loc["KC", "vacated_target_share"] - 0.30) < 1e-9
    assert abs(vac.loc["KC", "vacated_rush_share"] - 0.40) < 1e-9
    # Arizona is ONE franchise. The old DRAFT_TEAM_MAP sent ARI -> AZ, inventing a code that
    # exists in no season of the dataset and stranding 27 live 2026 players on NaN.
    assert "AZ" not in vac.index, "AZ must normalize onto ARI, not split the franchise"
    assert vac.loc["ARI", "vacated_target_share"] == 0.0
    assert vac.loc["ARI", "vacated_rush_share"] == 0.0


def _synthetic_full():
    """Two players across seasons with all columns build_feature_rows expects.
    Player A: 2018 active, 2019 MISSED (reconstructed 0-game), 2020 active.
    Player R: 2020 rookie only.
    """
    cols_base = bsd.ROLL_BASE
    rows = []
    def mk(pid, season, games, ppg, is_rookie, reconstructed, position="RB"):
        d = {c: 1.0 for c in cols_base}      # fill all roll-base cols with a value
        d.update({
            "player_id": pid, "season": season, "player": pid, "norm_name": pid.lower(),
            "position": position, "team": "KC", "games": games, "ppg": ppg,
            "is_rookie": is_rookie, "reconstructed": reconstructed,
            "team_pass_rate": 0.6, "team_plays_est": 1000,
            "coach_changed": False, "qb_changed": False,
            "age": 25.0, "years_exp": season - 2018, "draft_round": 1, "draft_pick": 10,
            "snap_share_pg": 0.8,
        })
        d["half_ppr"] = ppg * games
        return d
    rows.append(mk("A", 2018, 16, 12.0, is_rookie=1, reconstructed=0))
    rows.append(mk("A", 2019, 0,  np.nan, is_rookie=0, reconstructed=1))   # full miss
    rows.append(mk("A", 2020, 15, 14.0, is_rookie=0, reconstructed=0))
    rows.append(mk("R", 2020, 17, 9.0,  is_rookie=1, reconstructed=0))     # rookie
    return pd.DataFrame(rows)


def test_build_feature_rows_targets_and_flags():
    full = _synthetic_full()
    out = bsd.build_feature_rows(full)
    a2020 = out[(out.player_id == "A") & (out.season == 2020)].iloc[0]
    r2020 = out[(out.player_id == "R") & (out.season == 2020)].iloc[0]

    # missed_prior_season: A missed 2019 (prior_games == 0) -> flagged
    assert a2020["missed_prior_season"] == 1
    assert a2020["prior_games"] == 0          # the reconstructed 0-game row is the prior
    # rookie R has no prior row -> not flagged missed_prior, prior_games is NaN
    assert r2020["missed_prior_season"] == 0
    assert pd.isna(r2020["prior_games"])

    # targets: full seasons keep PPG; sample_weight == games
    assert abs(a2020["target_ppg"] - 14.0) < 1e-9
    assert a2020["sample_weight"] == 15
    assert a2020["target_games"] == 15


def test_build_feature_rows_soft_floor_and_zero_game():
    full = _synthetic_full()
    # add a 2-game season (below floor) and a 0-game season as target rows
    extra = pd.DataFrame([
        {**full.iloc[0].to_dict(), "player_id": "C", "norm_name": "c", "season": 2020,
         "games": 2, "ppg": 30.0, "is_rookie": 0, "reconstructed": 0},
        {**full.iloc[0].to_dict(), "player_id": "D", "norm_name": "d", "season": 2020,
         "games": 0, "ppg": np.nan, "is_rookie": 0, "reconstructed": 1},
    ])
    full2 = pd.concat([full, extra], ignore_index=True)
    out = bsd.build_feature_rows(full2)
    c = out[(out.player_id == "C") & (out.season == 2020)].iloc[0]
    d = out[(out.player_id == "D") & (out.season == 2020)].iloc[0]
    # below MIN_GAMES_TARGET -> Model A label dropped (NaN) but kept for Model B
    assert pd.isna(c["target_ppg"]) and c["target_games"] == 2
    # 0-game reconstructed -> Model A NaN, Model B sees 0
    assert pd.isna(d["target_ppg"]) and d["target_games"] == 0


# ── Output-integrity check on the real CSV (skipped if not yet built) ────────
def test_output_csv_integrity_if_present():
    csv = Path(__file__).resolve().parent / "season_dataset_2014_2025.csv"
    if not csv.exists():
        print("  (skip) season_dataset CSV not built yet")
        return
    df = pd.read_csv(csv)
    # The join pipeline must never duplicate the primary key.
    assert df.duplicated(subset=["player_id", "season"]).sum() == 0, "duplicate (player_id, season) rows"
    # Targets present and consistent with the documented rules.
    assert df["target_games"].notna().all(), "target_games should always be present"
    assert (df.loc[df["target_ppg"].notna(), "target_games"] >= bsd.MIN_GAMES_TARGET).all(), \
        "every row with a PPG label must have >= MIN_GAMES_TARGET games"
    assert (df.loc[df["reconstructed"] == 1, "target_games"] == 0).all(), \
        "reconstructed rows must be 0-game"
    # Flags are clean 0/1 ints.
    for c in ["is_rookie", "missed_prior_season", "coach_changed", "qb_changed"]:
        assert set(df[c].dropna().unique()) <= {0, 1}, f"{c} not binary"
    print(f"  ok  output CSV integrity ({len(df):,} rows)")


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} tests passed")


if __name__ == "__main__":
    _run()
