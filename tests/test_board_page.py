"""REBOUND 2026-08-03 by the qb_changed DEPLOY REFRESH (inference only; the seven position
model pkls are byte-identical). Provenance:
fantasy/projections/results/QB_CHANGED_DEPLOY_REFRESH_2026-08-03.json

Proof for the rebuilt Draft Board tab (2026-07-22): the licensed Phase-4 band was
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

_HERE = Path(__file__).resolve().parents[1]
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
    """The 2026 production overlay is exactly 45 named players.

    Joseph's 2026-07-27 directive replaced the earlier conditional/status gates: every
    player previously held back for an unresolved competition, recovery timetable or
    room-allocation question now carries a nonzero probability-weighted board value.
    """
    import draft_board_2026 as board

    expected = {
        "Josh Downs": (92.5, 109.6),
        "Xavier Worthy": (84.0, 131.0),
        "Ladd McConkey": (153.1, 174.7),
        # 2026-08-03 news: PCL surgery, out for the full season, placed on injured
        # reserve. This row previously carried a 119.4 healthy-role scenario.
        "Ricky Pearsall": (66.3, 0.0),
        "Bijan Robinson": (208.2, 248.2),
        "Chase Brown": (198.8, 219.6),
        "De'Von Achane": (204.1, 211.6),
        "Jahmyr Gibbs": (234.6, 255.2),
        "Javonte Williams": (157.3, 180.9),
        "Jonathan Taylor": (177.8, 195.8),
        "Kenneth Walker III": (159.1, 178.2),
        "Brenton Strange": (67.8, 95.0),
        "George Kittle": (127.5, 105.0),
        "Gunnar Helm": (47.5, 70.0),
        "Isaiah Likely": (50.6, 95.0),
        "Theo Johnson": (90.8, 75.0),
        "Brock Purdy": (162.5, 285.0),
        "Jaxson Dart": (233.5, 270.0),
        "Jayden Daniels": (145.8, 285.0),
        "Joe Burrow": (257.1, 300.0),
        "Lamar Jackson": (217.3, 315.0),
        "Malik Willis": (20.4, 220.0),
        "Trevor Lawrence": (230.5, 285.0),
        "Tyler Shough": (114.3, 215.0),
        # Previously held for an unresolved status; now carried at a weighted value.
        "Rome Odunze": (85.0, 125.0),
        "Michael Wilson": (115.5, 129.4),
        "Zach Charbonnet": (99.6, 63.2),
        "Sam LaPorta": (97.9, 134.2),
        "T.J. Hockenson": (59.4, 104.6),
        "Oronde Gadsden II": (78.9, 109.0),
        "Mark Andrews": (97.4, 117.1),
        "Kyler Murray": (125.9, 186.0),
        "J.J. McCarthy": (115.9, 116.2),
        "Patrick Mahomes": (272.9, 286.0),
        "Daniel Jones": (232.4, 239.3),
        # Rookie WRs added 2026-07-27 at Joseph's direction.
        "Jordyn Tyson": (78.7, 149.5),
        "Chris Brazzell": (23.6, 55.6),
        "Chris Bell": (38.4, 24.3),
        "Carnell Tate": (102.9, 138.4),
        "De'Zhaun Stribling": (102.6, 99.3),
        "Kenyon Sadiq": (56.6, 77.3),
        "Jeremiyah Love": (153.1, 199.0),
        "Jadarian Price": (145.1, 172.7),
        "Demond Claiborne": (5.4, 21.3),
        # 2026-08-03 news: re-signed with San Francisco on a one-year deal into a
        # receiver room reduced by Pearsall's season-ending injury. This row also
        # carries the TEAM correction (the artifact has him blank as a free agent).
        "Deebo Samuel Sr.": (93.4, 120.0),
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
    assert len(overlay) == len(expected) == 45
    assert not overlay["player_id"].duplicated().any()
    assert overlay["adjusted_projection"].notna().all()
    # No market/consensus field may enter the overlay artifact.
    assert not {"sleeper", "adp", "diff", "rank", "consensus"}.intersection(overlay.columns)
    assert set(overlay["player"]) == set(expected)
    assert formerly_conditional <= set(overlay["player"])
    assert not_approved.isdisjoint(set(overlay["player"]))
    assert overlay["position"].value_counts().to_dict() == \
        {"QB": 12, "WR": 12, "RB": 11, "TE": 10}

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
    assert len(disclosure) == 45
    for col in ("Position", "Player", "Team", "Raw model", "Board value", "Basis", "As of"):
        assert col in disclosure.columns

    at = _run()
    assert not [e for e in at.expander
                if "analyst projection overlay" in str(getattr(e, "label", "")).lower()],         "the overlay expander was removed and must not reappear"
    captions = " ".join(str(c.value) for c in at.caption)
    assert "direction nor the magnitude" in captions
    assert "named-player scenario" in captions
    assert "raw model output is preserved" in captions


def test_overlay_team_correction_is_identity_only_and_validated():
    """A dated overlay row may correct a player's TEAM, and nothing else moves.

    Deebo Samuel re-signed with San Francisco on 2026-07-31, after the projection artifacts
    were built. Those artifacts still carry him blank, which the board renders as "not
    signed" — so the correction rides on his disclosed overlay row. It must arrive on the
    board WITHOUT the raw model artifact being hand-edited, and it must feed no number.
    """
    import draft_board_2026 as board

    # The correction is real only if the underlying artifact is still blank.
    raw = pd.read_csv(board.PROJ_RESULTS / "wr_projection_2026.csv",
                      usecols=["player_id", "player", "team", "projection"])
    deebo_raw = raw[raw["player_id"].eq("00-0035719")]
    assert len(deebo_raw) == 1
    assert pd.isna(deebo_raw.iloc[0]["team"]), \
        "the WR artifact must stay untouched — the team correction belongs to the overlay"
    assert float(deebo_raw.iloc[0]["projection"]) == 93.4

    board_rows = board._load_board_2026().set_index("player_id")
    assert board_rows.loc["00-0035719", "team"] == "SF"
    assert float(board_rows.loc["00-0035719", "model_proj_raw"]) == 93.4

    # Identity only: no other player's team is touched by the overlay, and every overlay row
    # without a team code leaves the artifact's own team in place.
    overlay = pd.read_csv(board.ANALYST_PROJECTION_ADJUSTMENTS)
    corrected = overlay.loc[overlay["team"].notna(), "player_id"].tolist()
    assert corrected == ["00-0035719"], "only the disclosed signing carries a team correction"
    untouched = overlay.loc[overlay["team"].isna() & overlay["player_id"].eq("00-0039916")]
    assert len(untouched) == 1
    assert board_rows.loc["00-0039916", "team"] == "SF"  # from the artifact, not the overlay

    # A malformed code must fail loudly rather than render a nonsense team.
    import tempfile
    original = board.ANALYST_PROJECTION_ADJUSTMENTS
    bad = overlay.copy()
    bad.loc[bad["player_id"].eq("00-0035719"), "team"] = "San Francisco"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad_overlay.csv"
            bad.to_csv(path, index=False)
            board.ANALYST_PROJECTION_ADJUSTMENTS = path
            try:
                board._load_projections()
            except ValueError as exc:
                assert "team correction" in str(exc)
            else:
                raise AssertionError("a malformed team code must raise")
    finally:
        board.ANALYST_PROJECTION_ADJUSTMENTS = original

    # And the guard is not vacuously passing: the real file loads clean afterwards.
    assert board._load_projections().loc["00-0035719", "team"] == "SF"


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
    # Assert against the module constant, not a literal, so the tint lives in one place. It must
    # stay a GREEN surface (Joseph's call 2026-07-27: the old #1b5e3a read as grey on the
    # deployed dark skin) and stay dark enough that the red/green value encoding rendered on top
    # of it remains legible.
    assert active_style["background-color"] == board._SORT_TINT
    tint = board._SORT_TINT.lstrip("#")
    r, g, b = (int(tint[i:i + 2], 16) for i in (0, 2, 4))
    assert g > r and g > b, f"the active-sort tint must read green, got #{tint}"
    assert max(r, g, b) < 190, f"the sort tint must stay a surface, not a value color: #{tint}"
    # Grey-regression floor. Joseph rejected #1b5e3a and #16703a for reading grey on the deployed
    # dark skin: both were green by hex but too dark to read as green. A tint that trips either
    # bound below is that regression returning, so fail here rather than on the live site.
    assert g >= 120, f"the sort tint is too dark to read as green — it will look grey: #{tint}"
    assert g - max(r, b) >= 60, (
        f"the sort tint's green is not dominant enough over red/blue — it will look grey: #{tint}")
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


def test_sort_tint_actually_reaches_the_rendered_grid():
    """The Styler-context assertion above is pandas-side only — it passes even if streamlit
    never transports the style. Streamlit 1.59 marshals Styler CSS INTO `arrow_data` (there is
    no top-level `styler` proto field any more), so assert the tint survives all the way into
    what the front end is actually handed."""
    import draft_board_2026 as board

    at = _run()
    proto = None
    for el in at.dataframe:
        value = el.value
        frame = value.data if hasattr(value, "data") else value
        try:
            if {"adp_half_ppr", "model_gap"} <= set(frame.columns):
                proto = el.proto
                break
        except Exception:
            pass
    assert proto is not None, "board dataframe not found"

    payload = str(proto)
    tint = board._SORT_TINT.lstrip("#")
    assert tint in payload, (
        f"the active-sort tint #{tint} never reached the grid payload — the Styler is being "
        "computed but not transported, so the board would render with no cell colour at all")
    assert "background-color" in payload, "no background-color survived into the grid payload"


def test_no_forbidden_language_in_rendered_copy():
    at = _run()
    text = " ".join(str(m.value) for m in at.markdown)
    hits = _FORBIDDEN.findall(text)
    assert not hits, f"forbidden language in rendered board copy: {hits}"


def test_csv_download_present():
    at = _run()
    dl = at.get("download_button")
    assert any("Download board (CSV)" in b.label for b in dl), "full-board CSV download missing"
    # The outside-market explorer ships its own, distinctly labelled download.
    assert any("Download players outside the draft market (CSV)" in b.label for b in dl), \
        "outside-market CSV download missing"
    labels = [b.label for b in dl]
    assert len(set(labels)) == len(labels), f"two downloads share a label: {labels}"


# ---------------------------------------------------------------------------------------
# Players outside the current Sleeper draft market (added 2026-07-28)
# ---------------------------------------------------------------------------------------
# The board above is the DRAFT-PRICE universe (245 players with a 2026 Sleeper ADP) and stays
# exactly that. Everyone else the model projects lives in a collapsed, price-free explorer.
def _outside_df(at):
    for el in at.dataframe:
        v = el.value
        d = v.data if hasattr(v, "data") else v
        try:
            if {"model_proj_pos_rank_full", "nfl_talent"} <= set(d.columns):
                return d
        except Exception:
            pass
    return None


def _outside_entry():
    """The explorer alone, so its copy can be scanned without the board's captions."""
    import draft_board_2026 as board
    board._render_outside_market(len(board._load_board_2026()))


def test_outside_market_is_disjoint_from_the_board_and_fully_projected():
    import draft_board_2026 as board

    df = board._load_board_2026()
    outside = board._load_outside_market_players()

    assert len(df) == 245, f"the priced board must stay 245 rows, got {len(df)}"
    assert not set(outside["player_id"]) & set(df["player_id"]), \
        "outside-market rows must not overlap the 245-player board"
    assert not outside["player_id"].duplicated().any()
    assert outside["model_proj"].notna().all(), \
        "every outside-market row must carry a model projection"

    # Current artifact set: 897 projected players, 245 priced, 648 outside.
    assert board._projection_pool_size() == 897
    assert len(outside) == 654, f"expected 654 outside-market rows, got {len(outside)}"
    assert outside["position"].value_counts().to_dict() == \
        {"WR": 293, "TE": 160, "RB": 139, "QB": 62}

    # The arithmetic is 891 - 243, not 891 - 245: the two un-projected rookie QBs hold a
    # board row (they have an ADP) but no projection-artifact row, so they are in neither
    # the pool nor this list. Deriving the identity from the pool keeps that visible.
    projected = set(board._load_projections().index)
    priced_and_projected = int(df["player_id"].isin(projected).sum())
    assert priced_and_projected == 243
    assert int(df["model_proj"].isna().sum()) == 245 - priced_and_projected == 2
    assert len(outside) == board._projection_pool_size() - priced_and_projected
    # Robust floor in case a future projection refresh moves the exact cardinality.
    assert len(outside) >= 500


def test_dontayvion_wicks_anchor_row():
    """One fully-verified anchor row, exact in every rendered field.

    Rank note: WR105. The explorer starts from `_load_projections()`, so the disclosed
    analyst overlay is applied before ranking — exactly as it is for the board's own Model
    Proj Position Rank. This rank was WR106 until 2026-08-03, when Ricky Pearsall's row was
    cut to 0.0 for season-ending surgery: his overlay now crosses DOWN past Wicks' 46.5,
    cancelling Chris Brazzell's long-standing crossing UP (raw 12.8 -> board 55.6).

    Because the two crossings cancel, the adjusted rank currently EQUALS the raw-column rank
    (105), so this anchor no longer discriminates adjusted-vs-raw ranking by itself — that
    property is proven globally by
    test_ranks_gaps_and_download_use_the_adjusted_projection. What is pinned here is the
    exact pair of crossings, so any future overlay edit that disturbs either one fails loudly
    instead of silently shifting the anchor.
    """
    import draft_board_2026 as board

    outside = board._load_outside_market_players()
    rows = outside[outside["player_id"].eq("00-0038393")]
    assert len(rows) == 1, "Dontayvion Wicks must appear exactly once"
    wicks = rows.iloc[0]
    assert wicks["player"] == "Dontayvion Wicks"
    assert wicks["position"] == "WR"
    assert wicks["team"] == "PHI"
    assert float(wicks["model_proj"]) == 47.6
    assert int(wicks["model_proj_pos_rank_full"]) == 101
    assert float(wicks["nfl_talent"]) == 67.9
    assert float(wicks["college_talent"]) == 61.4

    # Pin BOTH crossings and the fact that they cancel, so a future overlay edit fails
    # loudly here rather than silently shifting the anchor.
    projections = board._load_projections()
    wr = projections[projections["position"].eq("WR")]
    raw_rank = wr["model_projection_raw"].rank(method="min", ascending=False)
    assert int(raw_rank.loc["00-0038393"]) == 101
    up = wr[(wr["model_projection_raw"] <= 47.6) & (wr["projection"] > 47.6)]
    down = wr[(wr["model_projection_raw"] > 47.6) & (wr["projection"] <= 47.6)]
    assert up["player"].tolist() == ["Chris Brazzell"]
    assert down["player"].tolist() == ["Ricky Pearsall"]
    assert len(up) == len(down), "the two crossings must cancel for the anchor to be 105"


def test_outside_market_rank_is_taken_against_the_full_projection_pool():
    """The rank must be positional across all 897 projected players, never within the 648."""
    import draft_board_2026 as board

    projections = board._load_projections().reset_index()
    projections["model_proj"] = pd.to_numeric(projections["projection"], errors="coerce")
    expected = projections.groupby("position")["model_proj"] \
                          .rank(method="min", ascending=False)
    expected.index = projections["player_id"]

    outside = board._load_outside_market_players().set_index("player_id")
    got = outside["model_proj_pos_rank_full"].astype(float)
    assert got.equals(expected.loc[got.index].astype(float))

    # A subset-local rank would start at 1 in every position; the full-pool rank does not,
    # because the highest-projected players at each position are all on the priced board.
    assert got.groupby(outside["position"]).min().min() > 1
    assert int(got.max()) <= board._projection_pool_size()


def test_outside_market_explorer_renders_collapsed_with_its_own_table():
    import draft_board_2026 as board

    at = _run()
    labels = [str(getattr(e, "label", "")) for e in at.expander]
    matches = [e for e in at.expander
               if "outside" in str(getattr(e, "label", "")).lower()]
    assert matches, f"outside-market expander missing: {labels}"
    assert matches[0].proto.expanded is False, \
        "the outside-market explorer must ship collapsed"
    label = str(matches[0].label)
    outside = board._load_outside_market_players()
    assert str(len(outside)) in label, f"the count must be derived into the label: {label!r}"
    assert str(len(board._load_board_2026())) in label

    table = _outside_df(at)
    assert table is not None, "outside-market dataframe not rendered"
    assert table.shape[0] == len(outside)
    assert list(table.columns) == [board._ROW_NO] + board._OUTSIDE_DISPLAY_COLS
    # Default sort: Model Proj descending.
    proj = table["model_proj"].to_numpy()
    assert (proj[:-1] >= proj[1:]).all(), "default sort must be Model Proj descending"
    assert table[board._ROW_NO].tolist() == list(range(1, len(table) + 1))

    # The priced board is untouched and still the only place price columns appear.
    board_table = _board_df(at)
    assert board_table.shape[0] == 245
    assert not {"adp_half_ppr", "sleeper_proj", "pos_rank", "sleeper_gap",
                "model_gap"} & set(table.columns), \
        "the outside-market explorer must show no price or gap columns"


def test_outside_market_copy_passes_the_forbidden_language_scan():
    """Scans the explorer in isolation — its own labels, captions and column tooltips —
    so the result is not diluted by the board copy rendered above it."""
    import draft_board_2026 as board

    at = AppTest.from_function(_outside_entry, default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]

    text = " ".join(
        [str(m.value) for m in at.markdown]
        + [str(c.value) for c in at.caption]
        + [str(getattr(e, "label", "")) for e in at.expander]
        + [str(b.label) for b in at.get("download_button")]
        + [m[2] for m in board._OUTSIDE_COLUMN_META]
        + [m[3] for m in board._OUTSIDE_COLUMN_META]
        + list(board.OUTSIDE_SORT_KEYS)
    )
    hits = _FORBIDDEN.findall(text)
    assert not hits, f"forbidden language in the outside-market copy: {hits}"
    # The required disclosures, stated in the explorer itself.
    assert "no current Sleeper half-PPR ADP" in text
    assert "same underlying artifacts" in text
    assert "qualification or coverage rules" in text
    assert "Different reference pools" in text


def test_outside_market_shares_the_board_cache_fingerprint(monkeypatch, tmp_path):
    """One fingerprint drives both views, so a changed projection or talent artifact can
    never leave the explorer stale while the board refreshes."""
    import draft_board_2026 as board

    paths = [p for p, _mtime, _size in board._board_source_fingerprint()]
    for required in (board.PROJ_RESULTS / "wr_projection_2026.csv",
                     board.ANALYST_PROJECTION_ADJUSTMENTS,
                     board.NFL_WR_CSV, board.COLLEGE_WR_CSV,
                     board.NFL_QB_CSV, board.COLLEGE_QB_CSV,
                     board.NFL_RB_CSV, board.COLLEGE_RB_CSV,
                     board.NFL_TE_CSV, board.COLLEGE_TE_CSV):
        assert str(required) in paths, f"{required.name} is outside the cache fingerprint"

    artifact = tmp_path / "nfl_wr_score_2026.csv"
    artifact.write_text("gsis_id,score\n00-0038393,67.9\n", encoding="utf-8")
    monkeypatch.setattr(
        board, "_board_source_fingerprint",
        lambda: (("wr_talent", artifact.stat().st_mtime_ns, artifact.stat().st_size),))
    seen = []
    monkeypatch.setattr(
        board, "_load_outside_market_players_cached", lambda fingerprint: seen.append(fingerprint))

    board._load_outside_market_players()
    # A different SIZE as well as a rewrite: two same-length writes inside one filesystem
    # mtime tick would leave the fingerprint identical and make this pass vacuously.
    artifact.write_text("gsis_id,score\n00-0038393,71.25\n00-0000001,50.0\n", encoding="utf-8")
    board._load_outside_market_players()

    assert len(seen) == 2 and seen[0] != seen[1]


def test_outside_market_college_join_is_id_guarded_never_by_name():
    """The college artifacts carry the NFL id in `gsis_id` for veterans and in
    `nfl_player_id` for brand-new deploy rows. The join coalesces the two, keeps position in
    the key, drops ambiguous duplicates, and never falls back to a name match."""
    import draft_board_2026 as board

    source = board._college_talent_by_join_id
    for position, path in board._COLLEGE_TALENT_BY_POSITION.items():
        scores = source(path)
        assert not scores.index.duplicated().any(), \
            f"{position}: ambiguous college ids were not dropped"
        assert scores.notna().all()

    # Wicks' college row carries the NFL id in gsis_id with nfl_player_id blank — the seam
    # an nfl_player_id-only join would miss entirely.
    college_wr = pd.read_csv(board.COLLEGE_WR_CSV,
                             usecols=["gsis_id", "nfl_player_id", "player", "score"],
                             dtype={"gsis_id": str, "nfl_player_id": str})
    row = college_wr[college_wr["gsis_id"].eq("00-0038393")]
    assert len(row) == 1 and pd.isna(row.iloc[0]["nfl_player_id"])
    assert float(source(board.COLLEGE_WR_CSV).loc["00-0038393"]) == 61.4

    # And no name column is read anywhere in the join path.
    import inspect
    join_source = inspect.getsource(source)
    assert "norm_name" not in join_source and '"player"' not in join_source


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
    test_sort_tint_actually_reaches_the_rendered_grid()
    test_no_forbidden_language_in_rendered_copy()
    test_csv_download_present()
    test_outside_market_is_disjoint_from_the_board_and_fully_projected()
    test_dontayvion_wicks_anchor_row()
    test_outside_market_rank_is_taken_against_the_full_projection_pool()
    test_outside_market_explorer_renders_collapsed_with_its_own_table()
    test_outside_market_copy_passes_the_forbidden_language_scan()
    test_outside_market_college_join_is_id_guarded_never_by_name()
    print("OK  rebuilt board: st.dataframe; guide collapsed; 245 rows; ADP-asc default; "
          "2 rookie QBs kept blank; 35 analyst overlays applied to ranks/gaps/download; "
          "exact labels; no forbidden language; CSV present; outside-market explorer "
          "collapsed with 648 disjoint fully-projected rows, full-pool ranks and its own CSV")
