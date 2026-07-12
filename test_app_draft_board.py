"""Integration test: the Draft Board tab (draft_board_2026.py) renders inside app.py.

Uses Streamlit AppTest to render app.py end to end against the real on-disk CSVs
(phase4_band_2026.csv + talent_index_2026.csv + season_dataset_2014_2026.csv +
rank_equiv_reference.csv), asserts the v4 launch column set (two position ranks +
gap, † on volatile QB/TE Pos cells, "VALUE (Nth %ile)" band cells, rightmost
context-only Efficiency column with Rookie/– markers), the worked-example block,
the ADP-snapshot caption, and the CSV download button, then drives the Position
filter and the advanced-view toggle, asserting a clean render (no uncaught
exception, no rendered st.error) at each step.

Run:  python test_app_draft_board.py    (or: pytest test_app_draft_board.py)
"""
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parent
APP = str(_HERE / "app.py")
BAND_CSV = _HERE / "fantasy" / "seasonal_projections" / "phase4_band_2026.csv"
TAB_LABEL = "📋 Draft Board"
DEFAULT_COLS = ["player_disp", "position_disp", "team", "adp_half_ppr",
                "adp_pos_rank", "proj_pos_rank", "value_gap",
                "p10", "p50_disp", "p90",
                "top12_pct", "eff_disp"]
PCTILE_RE = re.compile(r"^-?\d+ \(\d+(st|nd|rd|th) %ile\)$")
EFF_RE = re.compile(r"^(\d+|Rookie|–)$")


def _board_df(at):
    """The 2026 board's default table among all rendered dataframes."""
    for el in at.dataframe:
        v = el.value
        df = v.data if hasattr(v, "data") else v
        try:
            cols = list(df.columns)
        except Exception:
            continue
        if "player_disp" in cols:
            return df
    return None


def test_draft_value_2026_tab_renders_and_filters():
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]

    assert any(TAB_LABEL in t.label for t in at.tabs), f"{TAB_LABEL!r} tab not found"

    # ── default view: exact v4 launch column set (Efficiency rightmost) ──
    df = _board_df(at)
    assert df is not None, "2026 board table not found"
    assert list(df.columns) == DEFAULT_COLS, \
        f"default columns changed: {list(df.columns)}"

    # † appears on exactly the volatile-QB/TE rows, never elsewhere
    n_untested = int((pd.read_csv(BAND_CSV)["population"] == "volatile_qb_te").sum())
    dagger = df["position_disp"].str.contains("†", na=False)
    assert int(dagger.sum()) == n_untested, \
        f"† rows {int(dagger.sum())} != volatile_qb_te rows {n_untested}"
    assert df.loc[dagger, "position_disp"].str.startswith(("QB", "TE")).all(), \
        "† must only mark QB/TE rows"

    # the two ranks reconstruct the gap (value_gap = position rank − proj rank)
    ok = df.dropna(subset=["adp_pos_rank", "proj_pos_rank", "value_gap"])
    assert ((ok["adp_pos_rank"] - ok["proj_pos_rank"]) == ok["value_gap"]).all(), \
        "Position rank − Proj position rank must equal Gap"

    # Expected renders as "VALUE (Nth %ile)"; Floor/Ceiling stay numeric-sortable
    cells = df["p50_disp"].dropna()
    cells = cells[cells != ""]
    assert len(cells) > 100 and cells.map(
        lambda s: bool(PCTILE_RE.match(s))).all(), \
        "p50_disp cells should look like '113 (47th %ile)'"
    from pandas.api.types import is_numeric_dtype
    assert is_numeric_dtype(df["p10"]) and is_numeric_dtype(df["p90"]), \
        "Floor/Ceiling must stay numeric for grid sorting"

    # Efficiency column: numeric percentile, 'Rookie', or '–' — nothing else
    eff = df["eff_disp"].dropna()
    assert eff.map(lambda s: bool(EFF_RE.match(s))).all(), \
        f"unexpected Efficiency cells: {set(eff) - set(['Rookie', '–'])}"
    assert (eff == "Rookie").sum() > 0, "rookie rows should display 'Rookie'"

    # ── ADP snapshot caption + CSV download button ──
    assert any("Sleeper ADP as of July 10, 2026" in str(c.value)
               for c in at.caption), "ADP snapshot caption missing"
    dl = at.get("download_button")
    assert any("Download board (CSV)" in b.label for b in dl), \
        "CSV download button missing"

    # ── no ADP range slider on this tab ──
    assert not any(getattr(s, "key", None) == "db26_adp" for s in at.slider), \
        "ADP range slider should be removed"

    # ── worked-example block renders inside the how-to-read expander ──
    example = [m for m in at.markdown if "For example:" in str(m.value)]
    assert example, "worked-example block not rendered"
    assert "your call" in str(example[0].value), \
        "example must end on the non-evaluative closing line"

    # ── flip a filter: Position -> RB only ──
    pos = [m for m in at.multiselect if m.key == "db26_pos"]
    assert pos, "Position filter not found"
    pos[0].set_value(["RB"]).run()
    assert not at.exception, at.exception
    df_rb = _board_df(at)
    assert df_rb is not None and (df_rb["position_disp"] == "RB").all(), \
        "position filter should restrict to RB (and RB rows carry no †)"

    # ── advanced view toggle: relocated columns + per-row equivalents ──
    adv = [c for c in at.checkbox if c.key == "db26_adv"]
    assert adv, "advanced-view toggle not found"
    adv[0].set_value(True).run()
    assert not at.exception, at.exception

    adv_df = None
    for el in at.dataframe:
        v = el.value
        d = v.data if hasattr(v, "data") else v
        try:
            cols = set(d.columns)
        except Exception:
            continue
        if "metric_name" in cols:
            adv_df = d
            break
    assert adv_df is not None, "advanced view should expose a per-row metric_name column"
    for c in ("floor_equiv", "expected_equiv", "ceiling_equiv", "badge",
              "data_note", "rookie_note", "talent_pct", "p_top24", "p_bust",
              "pct_among_2026_drafted_class"):
        assert c in adv_df.columns, f"advanced view missing column {c!r}"

    print("OK  Draft Board tab: launch columns (Efficiency rightmost, "
          "percentile on Expected only); † on exactly the volatile QB/TE rows; "
          "ranks reconstruct Gap; Rookie/– markers; ADP caption; CSV "
          "download; worked example renders; Position filter works; advanced "
          "view carries equivalents + relocated columns")


if __name__ == "__main__":
    test_draft_value_2026_tab_renders_and_filters()
