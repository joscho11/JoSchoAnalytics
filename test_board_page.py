"""Proof for the rebuilt Draft Board tab (2026-07-22): the licensed Phase-4 band was
retired and the tab is now a 245-row season-projection comparison table (Sleeper ADP +
Position Rank + two independent projections with their positional-rank gaps + descriptive
talent scores). Renders the board page function directly via AppTest.from_function
(nav-independent). Hermetic (APP_OFFLINE=1).

Asserts: renders via st.dataframe (not st.table); the "What each column means" guide lives
INSIDE the collapsed How-to-read expander; all 245 rows render; the default sort is Sleeper
ADP ascending; the two un-projected rookie QBs are KEPT with a blank Model Proj; the exact
on-screen column labels are present; the CSV download exists; and the rendered copy carries no
forbidden buy/sell/value language.
"""
import os
import re
import sys
from pathlib import Path

import pandas as pd

os.environ["APP_OFFLINE"] = "1"

from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "betting"))
sys.path.insert(0, str(_HERE / "fantasy" / "seasonal_projections"))

_FORBIDDEN = re.compile(
    r"\b(buy|sell|fade|steal|reach|target|tier|must[- ]?draft|overvalued|undervalued|"
    r"hit[- ]?rate|accuracy)\b", re.I)


def _entry():
    """Board page as a standalone AppTest script (nav-independent)."""
    import page_draft_board
    page_draft_board.render()


def _run():
    at = AppTest.from_function(_entry, default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def _run_compact():
    """Same page with the detail toggle switched OFF (detail is ON by default)."""
    at = AppTest.from_function(_entry, default_timeout=180).run()
    assert not at.exception, at.exception
    toggles = [t for t in at.toggle if "detail" in str(t.label).lower()]
    assert toggles, f"detail toggle missing: {[str(t.label) for t in at.toggle]}"
    assert toggles[0].value is True, "the detail toggle must ship ON by default"
    at = toggles[0].set_value(False).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def _board_df(at):
    for el in at.dataframe:
        v = el.value
        d = v.data if hasattr(v, "data") else v
        try:
            if {"adp_half_ppr", "model_gap"} <= set(d.columns):
                return d
        except Exception:
            pass
    return None


def test_board_uses_dataframe_not_table():
    at = _run()
    assert len(list(at.table)) == 0, "board must render via st.dataframe, not st.table"
    assert _board_df(at) is not None, "board dataframe not found"


def test_column_guide_inside_collapsed_expander():
    at = _run()
    exps = [e for e in at.expander if "How to read" in str(getattr(e, "label", ""))]
    assert exps, "How-to-read expander missing"
    assert exps[0].proto.expanded is False, "How-to-read expander must be collapsed on load"
    md = " ".join(str(m.value) for m in at.markdown)
    assert "What each column means" in md, "column guide missing"
    # a COLUMN_META tooltip string appears in the guide (relocated byte-identical)
    assert "descriptive difference, not advice" in md, \
        "a COLUMN_META tooltip must appear in the guide"


def test_full_board_245_default_adp_ascending_rookie_qbs_kept():
    """2026-07-27 polish: the full thirteen-column board stays the DEFAULT (Joseph's call), and a
    detail toggle can drop the four raw-projection / talent columns for a compact comparison view.
    Every original assertion still runs against the default, and is re-checked in compact mode."""
    import draft_board_2026 as board

    at = _run()
    t = _board_df(at)
    assert t.shape[0] == 245, f"expected 245 rows in the scroll box, got {t.shape[0]}"
    adp = t["adp_half_ppr"].to_numpy()
    assert (adp[:-1] <= adp[1:]).all(), "default sort must be Sleeper ADP ascending"
    # DEFAULT is the full board: every display column renders, detail included.
    assert set(board._DISPLAY_COLS) <= set(t.columns), \
        f"default view is missing columns: {set(board._DISPLAY_COLS) - set(t.columns)}"
    # the two un-projected rookie QBs are KEPT (not dropped), blank in Model Proj
    n_blank_model = int(pd.isna(t["model_proj"]).sum())
    assert n_blank_model == 2, f"expected exactly 2 blank Model Proj rows, got {n_blank_model}"
    # Sleeper Proj is blank for the same two (their only non-blank cells are ADP-derived)
    assert int(pd.isna(t["sleeper_proj"]).sum()) == 2

    # COMPACT mode drops exactly the four detail columns and nothing else, same 245 rows,
    # same ADP-ascending order.
    c = _board_df(_run_compact())
    assert c.shape[0] == 245, f"compact view lost rows: {c.shape[0]}"
    assert set(board._COMPACT_COLS) <= set(c.columns), "a compact column is missing"
    assert not set(board._DETAIL_ONLY) & set(c.columns), \
        f"detail columns must be dropped when the toggle is off: " \
        f"{set(board._DETAIL_ONLY) & set(c.columns)}"
    assert set(board._COMPACT_COLS) | set(board._DETAIL_ONLY) == set(board._DISPLAY_COLS)
    adp_c = c["adp_half_ppr"].to_numpy()
    assert (adp_c[:-1] <= adp_c[1:]).all(), "compact view must keep the ADP-ascending default"
    # model_proj_raw stays internal in BOTH modes and out of the export
    for frame in (t, c):
        assert "model_proj_raw" not in frame.columns


def test_compact_view_keeps_numeric_sort_and_the_full_csv():
    """Hiding a column must not disable sorting by it, and the download stays complete."""
    import draft_board_2026 as board

    df = board._load_board_2026()
    # Every sortable key is still resolvable, including the four detail-only ones.
    for label, key in board.SORT_KEYS.items():
        assert key in df.columns, f"sort key {key!r} for {label!r} is gone"
        for ascending in (True, False):
            ordered = board._sort_board(df, label, ascending=ascending)
            values = pd.to_numeric(ordered[key], errors="coerce")
            blank = values.isna().to_numpy()
            # NaN sentinels pinned to the BOTTOM in both directions
            assert not blank[:len(blank) - int(blank.sum())].any(), \
                f"{label} ({'asc' if ascending else 'desc'}): sentinels did not sink"

    # The CSV export is driven by _DISPLAY_COLS, not by what is on screen.
    export = df[board._DISPLAY_COLS].rename(columns=board._EXPORT_NAMES)
    for detail_key in board._DETAIL_ONLY:
        assert board._EXPORT_NAMES[detail_key] in export.columns, \
            f"{detail_key} must stay in the download even though it is hidden by default"
    assert "model_proj_raw" not in export.columns


def test_final_analyst_overlays_apply_and_preserve_raw_model_values():
    """The frozen 2026 production overlay is exactly 44 named players.

    Joseph's 2026-07-27 directive replaced the earlier conditional/status gates: every
    player previously held back for an unresolved competition, recovery timetable or
    room-allocation question now carries a nonzero probability-weighted board value.
    """
    import draft_board_2026 as board

    expected = {
        "Josh Downs": (92.2, 109.6),
        "Xavier Worthy": (82.4, 131.0),
        "Ladd McConkey": (153.0, 174.7),
        "Ricky Pearsall": (63.9, 119.4),
        "Bijan Robinson": (230.2, 248.2),
        "Chase Brown": (201.6, 219.6),
        "De'Von Achane": (193.6, 211.6),
        "Jahmyr Gibbs": (237.2, 255.2),
        "Javonte Williams": (162.9, 180.9),
        "Jonathan Taylor": (177.8, 195.8),
        "Kenneth Walker III": (160.2, 178.2),
        "Brenton Strange": (70.0, 95.0),
        "George Kittle": (151.2, 105.0),
        "Gunnar Helm": (46.9, 70.0),
        "Isaiah Likely": (56.4, 95.0),
        "Theo Johnson": (90.4, 75.0),
        "Brock Purdy": (160.8, 285.0),
        "Jaxson Dart": (248.6, 270.0),
        "Jayden Daniels": (102.4, 285.0),
        "Joe Burrow": (249.8, 300.0),
        "Lamar Jackson": (218.5, 315.0),
        "Malik Willis": (23.0, 220.0),
        "Trevor Lawrence": (226.7, 285.0),
        "Tyler Shough": (115.6, 215.0),
        # Previously held for an unresolved status; now carried at a weighted value.
        "Rome Odunze": (94.4, 125.0),
        "Michael Wilson": (101.8, 129.4),
        "Zach Charbonnet": (99.9, 63.2),
        "Sam LaPorta": (104.3, 134.2),
        "T.J. Hockenson": (56.1, 104.6),
        "Oronde Gadsden II": (83.3, 109.0),
        "Mark Andrews": (97.0, 117.1),
        "Kyler Murray": (97.8, 186.0),
        "J.J. McCarthy": (87.3, 116.2),
        "Patrick Mahomes": (293.2, 286.0),
        "Daniel Jones": (232.3, 239.3),
        # Rookie WRs added 2026-07-27 at Joseph's direction.
        "Jordyn Tyson": (83.4, 149.5),
        "Chris Brazzell": (12.8, 55.6),
        "Chris Bell": (34.1, 24.3),
        "Carnell Tate": (117.0, 138.4),
        "De'Zhaun Stribling": (106.1, 99.3),
        "Kenyon Sadiq": (56.2, 77.3),
        "Jeremiyah Love": (173.9, 199.0),
        "Jadarian Price": (145.1, 172.7),
        "Demond Claiborne": (5.1, 21.3),
    }
    # The eleven that were previously excluded are now REQUIRED to be present.
    formerly_conditional = {
        "Rome Odunze", "Michael Wilson", "Zach Charbonnet",
        "Sam LaPorta", "T.J. Hockenson", "Oronde Gadsden II", "Mark Andrews",
        "Kyler Murray", "J.J. McCarthy", "Patrick Mahomes", "Daniel Jones",
    }
    # Names reviewed in the same sessions but deliberately NOT approved for the board.
    not_approved = {
        "Malik Washington", "Jaylen Waddle", "DJ Moore", "Garrett Wilson",
        "Breece Hall", "Christian McCaffrey", "Saquon Barkley", "Derrick Henry",
        "Brock Bowers", "Trey McBride", "Sam Darnold", "Jordan Love",
        "Marvin Harrison Jr.", "Luther Burden III",
    }

    overlay = pd.read_csv(board.ANALYST_PROJECTION_ADJUSTMENTS)
    assert len(overlay) == len(expected) == 44
    assert not overlay["player_id"].duplicated().any()
    assert overlay["adjusted_projection"].notna().all()
    # No market/consensus field may enter the overlay artifact.
    assert not {"sleeper", "adp", "diff", "rank", "consensus"}.intersection(overlay.columns)
    assert set(overlay["player"]) == set(expected)
    assert formerly_conditional <= set(overlay["player"])
    assert not_approved.isdisjoint(set(overlay["player"]))
    assert overlay["position"].value_counts().to_dict() == \
        {"QB": 12, "WR": 11, "RB": 11, "TE": 10}

    # Every overlay raw value must still match the untouched raw projection artifact,
    # and every board value must actually differ from it.
    raw_files = pd.concat(
        [pd.read_csv(board.PROJ_RESULTS / f"{p}_projection_2026.csv",
                     usecols=["player_id", "player", "position", "projection"])
         for p in ("qb", "rb", "wr", "te")],
        ignore_index=True,
    ).drop_duplicates("player_id").set_index("player_id")
    joined = overlay.set_index("player_id").join(raw_files, rsuffix="_raw")
    assert joined["projection"].notna().all(), "overlay contains an orphan player_id"
    assert joined["player"].eq(joined["player_raw"]).all()
    assert joined["position"].eq(joined["position_raw"]).all()
    assert joined["projection"].sub(joined["raw_projection"]).abs().max() < 1e-9
    assert joined["adjusted_projection"].sub(joined["raw_projection"]).abs().min() > 0.05

    projections = board._load_projections().set_index("player")
    for player, (raw_value, board_value) in expected.items():
        row = projections.loc[player]
        assert row["model_projection_raw"] == raw_value
        assert row["projection"] == board_value
        assert pd.notna(row["projection_adjustment"])

    board_rows = board._load_board_2026().set_index("player")
    for player, (raw_value, board_value) in expected.items():
        assert player in board_rows.index, f"{player} missing from the 245-row board"
        row = board_rows.loc[player]
        assert row["model_proj_raw"] == raw_value
        assert row["model_proj"] == board_value

    assert "model_proj" in board._DISPLAY_COLS
    assert board._DISPLAY_COLS.count("model_proj") == 1, "one visible Model Proj only"
    for hidden in ("model_proj_raw", "projection_adjustment",
                   "projection_adjustment_as_of"):
        assert hidden not in board._DISPLAY_COLS


def test_ranks_gaps_and_download_use_the_adjusted_projection():
    """Model Proj Position Rank, Model Gap and the CSV export all derive from the
    adjusted value — never from the preserved raw one."""
    import draft_board_2026 as board

    df = board._load_board_2026()
    adjusted = df[df["model_proj"].notna()]
    expected_rank = adjusted.groupby("position")["model_proj"] \
                            .rank(method="min", ascending=False)
    assert adjusted["model_proj_pos_rank"].astype(float).equals(expected_rank.astype(float))
    assert adjusted["model_gap"].astype(float).equals(
        (adjusted["pos_rank"] - adjusted["model_proj_pos_rank"]).astype(float))

    # A raw-derived rank would be a different ordering (Charbonnet and Mahomes move down,
    # Hockenson and Murray move up), so this is a real discriminating check.
    raw_rank = adjusted.groupby("position")["model_proj_raw"] \
                       .rank(method="min", ascending=False)
    assert not adjusted["model_proj_pos_rank"].astype(float).equals(raw_rank.astype(float))

    export = df[board._DISPLAY_COLS].rename(columns=board._EXPORT_NAMES)
    assert "Model Proj" in export.columns
    assert not {"model_proj_raw", "Raw model"}.intersection(export.columns)
    charbonnet = export.loc[df["player"] == "Zach Charbonnet", "Model Proj"]
    assert float(charbonnet.iloc[0]) == 63.2


def test_overlay_audit_helper_and_caption_disclosure():
    """The on-page expander was removed at Joseph's request 2026-07-27. The programmatic
    audit helper stays (it is the overlay's accessor), and the single-line caption must
    still state the overlay exists and that Sleeper did not drive it."""
    import draft_board_2026 as board

    disclosure = board._load_adjustment_disclosure()
    assert len(disclosure) == 44
    for col in ("Position", "Player", "Raw model", "Board value", "Basis", "As of"):
        assert col in disclosure.columns

    at = _run()
    assert not [e for e in at.expander
                if "analyst projection overlay" in str(getattr(e, "label", "")).lower()],         "the overlay expander was removed and must not reappear"
    captions = " ".join(str(c.value) for c in at.caption)
    assert "direction nor the magnitude" in captions
    assert "named-player scenario" in captions
    assert "raw model output is preserved" in captions


def test_overlay_participates_in_the_board_cache_fingerprint():
    import draft_board_2026 as board
    paths = [p for p, _mtime, _size in board._board_source_fingerprint()]
    assert str(board.ANALYST_PROJECTION_ADJUSTMENTS) in paths


def test_exact_column_labels_present():
    import draft_board_2026 as board
    labels = [m[2] for m in board.COLUMN_META]
    for want in ("Sleeper ADP", "Position Rank", "Sleeper Proj Position Rank", "Sleeper Gap",
                 "Model Proj Position Rank", "Model Gap", "Sleeper Proj", "Model Proj",
                 "NFL Talent Score", "College Talent Score"):
        assert want in labels, f"missing exact column label: {want!r}"


def test_semantic_gap_colors_and_active_sort_tint():
    """The rebuilt table keeps the established Weekly Fantasy visual language.

    Gap direction is semantic (negative red, positive green); ranks use the same
    red-to-green ramp; the server-authoritative Sort by control marks its active
    column independently with a soft green surface tint.
    """
    import draft_board_2026 as board

    df = board._load_board_2026()
    view = board._sort_board(df, "Model Gap", ascending=False)
    styler = view[board._DISPLAY_COLS].style.apply(
        board._style_board(view, df, "model_gap"), axis=None)
    ctx = styler._compute().ctx

    model_gap_col = view[board._DISPLAY_COLS].columns.get_loc("model_gap")
    sleeper_gap_col = view[board._DISPLAY_COLS].columns.get_loc("sleeper_gap")
    model_proj_col = view[board._DISPLAY_COLS].columns.get_loc("model_proj")

    active_style = dict(ctx[(0, model_gap_col)])
    assert active_style["background-color"] == "#1b5e3a"
    assert active_style["font-weight"] == "700"
    assert active_style["font-size"] == "15px"

    # Find a non-null negative model gap and a non-null positive Sleeper gap to
    # prove the two independently-computed disagreement columns keep direction.
    neg_i = next(i for i, v in enumerate(view["model_gap"]) if v < 0)
    pos_i = next(i for i, v in enumerate(view["sleeper_gap"]) if v > 0)
    def _rgb(value):
        return tuple(int(x) for x in value.removeprefix("rgb(").removesuffix(")").split(","))

    neg_rgb = _rgb(dict(ctx[(neg_i, model_gap_col)])["color"])
    pos_rgb = _rgb(dict(ctx[(pos_i, sleeper_gap_col)])["color"])
    assert neg_rgb[0] > neg_rgb[1], "negative gaps must lean red"
    assert pos_rgb[1] > pos_rgb[0], "positive gaps must lean green"
    assert (pos_i, model_proj_col) not in ctx or "color" not in dict(ctx[(pos_i, model_proj_col)])


def test_no_forbidden_language_in_rendered_copy():
    at = _run()
    text = " ".join(str(m.value) for m in at.markdown)
    hits = _FORBIDDEN.findall(text)
    assert not hits, f"forbidden language in rendered board copy: {hits}"


def test_csv_download_present():
    at = _run()
    dl = at.get("download_button")
    assert any("Download board (CSV)" in b.label for b in dl), "full-board CSV download missing"


def test_board_cache_key_tracks_projection_artifact_changes(monkeypatch, tmp_path):
    import draft_board_2026 as board

    projection = tmp_path / "wr_projection_2026.csv"
    projection.write_text("projection\n69.0\n", encoding="utf-8")
    monkeypatch.setattr(
        board,
        "_board_source_fingerprint",
        lambda: (("wr", projection.stat().st_mtime_ns, projection.stat().st_size),),
    )
    seen = []
    monkeypatch.setattr(
        board,
        "_load_board_2026_cached",
        lambda fingerprint: seen.append(fingerprint),
    )

    board._load_board_2026()
    projection.write_text("projection\n127.9\n", encoding="utf-8")
    board._load_board_2026()

    assert len(seen) == 2
    assert seen[0] != seen[1]


if __name__ == "__main__":
    test_board_uses_dataframe_not_table()
    test_column_guide_inside_collapsed_expander()
    test_full_board_245_default_adp_ascending_rookie_qbs_kept()
    test_compact_view_keeps_numeric_sort_and_the_full_csv()
    test_final_analyst_overlays_apply_and_preserve_raw_model_values()
    test_ranks_gaps_and_download_use_the_adjusted_projection()
    test_overlay_audit_helper_and_caption_disclosure()
    test_overlay_participates_in_the_board_cache_fingerprint()
    test_exact_column_labels_present()
    test_semantic_gap_colors_and_active_sort_tint()
    test_no_forbidden_language_in_rendered_copy()
    test_csv_download_present()
    print("OK  rebuilt board: st.dataframe; guide collapsed; 245 rows; ADP-asc default; "
          "2 rookie QBs kept blank; 35 analyst overlays applied to ranks/gaps/download; "
          "exact labels; no forbidden language; CSV present")
