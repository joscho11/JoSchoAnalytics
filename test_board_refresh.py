"""Hermetic test for the 245-player ADP refresh (no network). Feeds a synthetic universe +
fresh pull into build_overlay and checks full-universe coverage, fresh-where-matched /
frozen-fallback, within-position ADP rank, and the overlay schema (value_gap dropped). Also
checks the real board universe from the frozen season dataset is the expected ~245.
"""
import os
import sys
from pathlib import Path

import pandas as pd

os.environ["APP_OFFLINE"] = "1"

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "fantasy" / "seasonal_projections"))


def test_build_overlay_full_coverage_and_fallback():
    import refresh_board_adp as rb
    universe = pd.DataFrame({
        "player_id": ["a", "b", "c", "d"],
        "player": ["Player A", "Player B", "Player C", "Player D"],
        "position": ["RB", "RB", "WR", "WR"],
        "adp_frozen": [10.0, 20.0, 5.0, 30.0],
    })
    # fresh has A, B, C (moved) but NOT D -> D falls back to its frozen price
    fresh = pd.DataFrame({
        "player": ["Player A", "Player B", "Player C", "Someone Else"],
        "position": ["RB", "RB", "WR", "TE"],
        "adp_half_ppr": [12.0, 8.0, 4.0, 99.0],
    })
    overlay, matched = rb.build_overlay(universe, fresh, "2026-07-22")

    assert list(overlay.columns) == ["player_id", "adp_half_ppr", "adp_pos_rank", "refreshed_at"]
    assert "value_gap" not in overlay.columns, "band-derived value_gap must be gone"
    assert len(overlay) == 4, "every universe player must appear (complete, never partial)"
    assert matched == 3, "A, B, C matched fresh; D falls back to frozen"
    o = overlay.set_index("player_id")
    assert o.loc["a", "adp_half_ppr"] == 12.0 and o.loc["b", "adp_half_ppr"] == 8.0
    assert o.loc["d", "adp_half_ppr"] == 30.0, "unmatched player keeps its frozen price"
    # within-position ADP rank: RB B(8) < A(12) -> B=1, A=2 ; WR C(4) < D(30) -> C=1, D=2
    assert o.loc["b", "adp_pos_rank"] == 1 and o.loc["a", "adp_pos_rank"] == 2
    assert o.loc["c", "adp_pos_rank"] == 1 and o.loc["d", "adp_pos_rank"] == 2


def test_real_board_universe_is_full_adp_set():
    import refresh_board_adp as rb
    u = rb.load_board_universe()
    assert 240 <= len(u) <= 250, f"expected the full ~245 Sleeper-ADP universe, got {len(u)}"
    assert u["player_id"].is_unique
    assert set(u.columns) == {"player_id", "player", "position", "adp_frozen"}


if __name__ == "__main__":
    test_build_overlay_full_coverage_and_fallback()
    test_real_board_universe_is_full_adp_set()
    print("OK  refresh covers the full ~245 board universe; fresh-or-fallback; value_gap dropped")
