"""2026 Draft Board tab — public revamp (2026-07-12): plain language by
default, technical detail in the advanced view.

License discipline: the plain strings TRANSLATE the licensed claims — never
strengthen, never weaken. The verbatim licensed strings ship in-schema and in
the advanced view. Plain translations pend Joseph's ratification.

Color coding: ALLOWED (Joseph-ratified 2026-07-13), uniform with the Weekly
Fantasy table — a red→green heat on the Gap and on the descriptive magnitude
columns (Top-12 chance, NFL Efficiency %ile), plus a bold, enlarged Gap headline.
Color conveys magnitude/direction only; it adds no claim the WORDING doesn't
already make, and the text still states validation IN AGGREGATE (never a rating
of an individual player). Still forbidden in the WORDING: buy/sell/fade/target/
steal/reach language, named tiers, accuracy or hit-rate claims, sub-group claims.
The talent column stays descriptive only and is never combined with another column.
Data: phase4_band_2026.csv + talent_index_2026.csv (frozen artifacts, read-only).
"""
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard_chrome import TABLE_HEIGHT   # shared ~20-row height for long tables

_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")

_HERE = Path(__file__).resolve().parent
SEAS = _HERE / "fantasy" / "seasonal_projections"
# LIVE ADP overlay written by refresh_board_adp.py (regenerable; market data only).
# The frozen band + season-dataset ADP are the fallback when it is absent.
LIVE_OVERLAY = SEAS / "board_adp_live_2026.csv"
# Talent/Rookie Score artifacts (fantasy/talent/, provenance-stamped). The dash
# rule's single source of truth is the ARTIFACT SPLIT itself — both files were
# built through schemas.is_nfl (zero NFL regular-season stat lines -> Rookie;
# any -> Talent), so cell population here derives ONLY from artifact membership.
# H7 LAYOUT FENCE: these columns are context-only and are NEVER combined with —
# or placed to imply combination with — the Gap, bands, Top-N, or bust columns.
TALENT_DIR = _HERE / "fantasy" / "talent"
TALENT_CSV = TALENT_DIR / "talent_score_2026.csv"
ROOKIE_CSV = TALENT_DIR / "rookie_score_2026.csv"
SCALE_DISCLOSURE = (
    "Talent Score ranks NFL players against NFL players; Rookie Score ranks "
    "2026 prospects against past drafted prospects. They are different "
    "instruments on different scales — a 90 in one column is not a 90 in the "
    "other, and neither feeds any other column on this board.")

# plain badge per population (short, default view)
BADGE = {
    "stable_role": "✓ Verified for this player group",
    "volatile_rb_wr": "✓ Verified for this player group",
    "volatile_qb_te": "Not yet verified for this group",
}
# plain TRANSLATIONS of the licensed strings (pending ratification; the
# verbatim strings remain in-schema and in the advanced view beside these)
PLAIN_LABEL = {
    "stable_role": (
        "Verified: for established players (same team as last year, played "
        "most of last season), I tested this projections-vs-price comparison "
        "on five past seasons and it held up as a group pattern — including a "
        "check that it wasn't just projections being newer than draft prices. "
        "It was tested on a large best-ball drafting platform, a slightly "
        "different format than classic leagues. It is a pattern across many "
        "players, not a rating of this player, and the size of any one gap "
        "has not been tested."),
    "volatile_rb_wr": (
        "Verified: for running backs and receivers in changing situations "
        "(rookies, players on new teams, and players with little recent "
        "playing time), the comparison held up as a group pattern across "
        "five past seasons when checked against draft prices from just "
        "before the season, taken at close to the same time as the "
        "projections. "
        "Same caveats: tested on a best-ball platform, a group pattern only — "
        "not a rating of this player and not a claim about any specific kind "
        "of player."),
    "volatile_qb_te": (
        "Not yet verified: for quarterbacks and tight ends in changing "
        "situations, this comparison has not been tested — there are too few "
        "players like this in past seasons to test it reliably. Treat the "
        "Projection vs. Price number here as untested information."),
}
ADV_DEFS = [
    ("in aggregate", "a pattern confirmed across groups of many players, "
     "not a claim about any individual"),
    ("freshness-controlled", "I checked that the signal isn't explained by "
     "projections simply being more up-to-date than draft prices"),
    ("dated best-ball market", "draft prices reconstructed week by week from "
     "Underdog best-ball drafts, so projections and prices could be compared "
     "from the same point in time"),
    ("format delta", "best-ball drafting differs a little from classic "
     "leagues (18 rounds, no in-season management), so results may not carry "
     "over exactly"),
    ("percentile band (P10–P90)", "a range drawn so that a player should "
     "finish below P10 about 10% of the time, below P50 half the time, and "
     "so on"),
    ("leave-one-season-out", "each past season was scored using ranges built "
     "only from the other seasons — no season graded itself"),
]


@st.cache_data
def _load_board_2026():
    band = pd.read_csv(SEAS / "phase4_band_2026.csv")
    talent = pd.read_csv(SEAS / "talent_index_2026.csv")
    ds = pd.read_csv(SEAS / "season_dataset_2014_2026.csv",
                     usecols=["player_id", "season", "adp_half_ppr"])
    adp = ds[ds.season == 2026][["player_id", "adp_half_ppr"]]
    t = talent[["player_id", "metric_name", "raw_value",
                "pct_among_2025_qualifiers", "pct_among_2026_drafted_class",
                "is_rookie_context", "draft_round", "draft_pick",
                "coverage_flag", "disclosure"]]
    df = band.merge(t, on="player_id", how="left").merge(adp, on="player_id", how="left")
    # LIVE ADP overlay: prefer the freshly-refreshed price columns where present, else
    # keep the frozen band's adp_pos_rank/value_gap and the season-dataset adp_half_ppr
    # (so a fresh clone and the hermetic AppTest still render). proj_pos_rank stays
    # frozen either way, since value_gap moves in lockstep with adp_pos_rank.
    if LIVE_OVERLAY.exists():
        ov = pd.read_csv(LIVE_OVERLAY).set_index("player_id")
        for col in ("adp_half_ppr", "adp_pos_rank", "value_gap"):
            if col in ov.columns:
                fresh = df["player_id"].map(ov[col])
                df[col] = fresh.where(fresh.notna(), df[col])
    df["badge"] = df["population"].map(BADGE)
    df["plain_label"] = df["population"].map(PLAIN_LABEL)
    df["talent_pct"] = df["pct_among_2025_qualifiers"].fillna(
        df["pct_among_2026_drafted_class"])
    df["rookie_note"] = df.apply(
        lambda r: "Rookie — college stats shown, not directly comparable to "
                  f"veteran numbers (drafted round {int(r.draft_round)}, "
                  f"pick {int(r.draft_pick)})"
        if r.is_rookie_context is True or r.is_rookie_context == True else "", axis=1)
    df["data_note"] = df["band_confidence"].map(
        lambda c: "Limited data — extra-wide uncertainty" if c == "LOW" else "")
    for src, dst in (("p_top12", "top12_pct"), ("p_top24", "top24_pct"),
                     ("p_bust", "bust_pct")):
        df[dst] = df[src] * 100.0

    # the two ranks behind the gap (value_gap = adp_pos_rank - proj_pos_rank)
    df["proj_pos_rank"] = (df["adp_pos_rank"] - df["value_gap"]).astype("Int64")
    # display: a missing gap renders as "–", never a blank cell
    df["gap_disp"] = [f"{v:.0f}" if pd.notna(v) else "–" for v in df["value_gap"]]
    # exception-only mark: † on the Pos cell for the untested volatile QB/TE group
    df["position_disp"] = df["position"].where(
        df["population"] != "volatile_qb_te", df["position"] + " †")
    # ⚠ on the name for limited-data rows
    limited = (df["band_confidence"] == "LOW") | df["is_unprojected"].fillna(False)
    df["player_disp"] = df["player"].where(~limited, df["player"] + " ⚠")
    # 2025 NFL efficiency percentile: qualified veterans only; rookies and
    # below-qualifier veterans get text markers (context column, never blended)
    df["eff_disp"] = [
        "Rookie" if rc is True or rc == True
        else (f"{v:.0f}" if pd.notna(v) else "–")
        for rc, v in zip(df["is_rookie_context"],
                         df["pct_among_2025_qualifiers"])]
    # Expected as "VALUE (Nth)" — percentile within position among this board's
    # rows, shown in the header ("Expected (Percentile)") so the cell stays
    # compact (display transform; no new data). Expected ONLY: the band spread is
    # flat per position, so Floor/Ceiling percentiles would be identical copies.
    pct = df.groupby("position")["p50"].rank(pct=True) * 100
    df["p50_pct"] = pct
    # Season fantasy points can't be negative. The band is a flat P50 ± position-constant
    # spread, so low-projection players (near-zero P50) get a mechanically negative lower
    # tail — e.g. a -76 "Floor". Clip the band at 0 for display: coverage-safe, since no
    # real season total is < 0, so the validated P10-P90 coverage is unchanged. The
    # percentile above ranks on the RAW P50, so ordering among low-projection players is
    # preserved.
    for _c in ("p10", "p25", "p50", "p75", "p90"):
        df[_c] = df[_c].clip(lower=0)
    df["p50_disp"] = [
        f"{v:.0f} ({_ordinal(int(round(p)))})"
        if pd.notna(v) and pd.notna(p) else ""
        for v, p in zip(df["p50"], pct)]
    # rank equivalents (display-only units table; see build_rank_equiv_reference.py)
    equiv = _load_rank_equiv()
    for src, dst in (("p10", "floor_equiv"), ("p50", "expected_equiv"),
                     ("p90", "ceiling_equiv")):
        df[dst] = [_equiv_label(equiv, p, v)
                   for p, v in zip(df["position"], df[src])]

    # ---- Talent Score + Rookie Score (two-cell display, R12/R23) ----------------
    # Cells populate from artifact membership ONLY (the dash rule's single source
    # of truth — see TALENT_DIR comment). Null-last sorting via the numeric keys.
    df["talent_score_num"] = pd.NA
    df["rookie_score_num"] = pd.NA
    df["talent_disp"] = "–"
    df["rookie_disp"] = "–"
    df["talent_w"] = pd.NA
    df["college_share"] = pd.NA
    if TALENT_CSV.exists():
        t = pd.read_csv(TALENT_CSV).set_index("gsis_id")
        m = df["player_id"].isin(t.index)
        idx = df.loc[m, "player_id"]
        df.loc[m, "talent_score_num"] = t.loc[idx, "score"].values
        df.loc[m, "talent_w"] = t.loc[idx, "w"].values
        df.loc[m, "college_share"] = t.loc[idx, "college_share"].values
        df.loc[m, "talent_disp"] = [
            f"{s:.0f} [{lo:.0f}–{hi:.0f}]{f if isinstance(f, str) else ''}"
            for s, lo, hi, f in zip(t.loc[idx, "score"], t.loc[idx, "ci_lo"],
                                    t.loc[idx, "ci_hi"], t.loc[idx, "flag"].fillna(""))]
    if TALENT_CSV.exists():
        for c in [c for c in t.columns if c.startswith(("z_", "w_"))]:
            df.loc[m, "tal_" + c] = t.loc[idx, c].values   # advanced-view facet detail
    if ROOKIE_CSV.exists():
        r = pd.read_csv(ROOKIE_CSV).set_index("gsis_id")
        m = df["player_id"].isin(r.index)
        idx = df.loc[m, "player_id"]
        df.loc[m, "rookie_score_num"] = r.loc[idx, "rookie_score"].values
        df.loc[m, "rookie_disp"] = [f"{s:.0f}" for s in r.loc[idx, "rookie_score"]]
    # R23 neither-cell tooltips live in the cell text's column help; QB rookies
    # get the scope note (Rookie Score covers RB/WR/TE only).
    neither = (df["talent_disp"] == "–") & (df["rookie_disp"] == "–")
    qb_rookie = neither & (df["position"] == "QB") & (
        df["eff_disp"] == "Rookie" if "eff_disp" in df.columns else False)
    df["cell_note"] = ""
    df.loc[neither, "cell_note"] = "insufficient qualifying data"
    df.loc[qb_rookie, "cell_note"] = "Rookie Score covers RB/WR/TE"
    for c in ("talent_score_num", "rookie_score_num", "talent_w", "college_share"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _ordinal(n):
    """1 -> '1st', 72 -> '72nd', 11 -> '11th'."""
    if 10 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


@st.cache_data
def _refresh_date():
    """The ADP snapshot date from the live overlay (ISO string), or None if absent."""
    if not LIVE_OVERLAY.exists():
        return None
    try:
        s = pd.read_csv(LIVE_OVERLAY, usecols=["refreshed_at"])["refreshed_at"]
        return str(s.iloc[0]) if len(s) else None
    except (KeyError, ValueError, pd.errors.EmptyDataError):
        return None


def _adp_caption():
    """Auto-stamped, first-person ADP caption. Flags a snapshot older than 7 days."""
    iso = _refresh_date()
    if not iso:
        return ("I refresh these draft prices from Sleeper ADP; prices move as real "
                "drafts happen.")
    try:
        stamp = date.fromisoformat(str(iso)[:10])
        pretty = f"{_MONTHS[stamp.month - 1]} {stamp.day}, {stamp.year}"
        stale = (date.today() - stamp).days > 7
    except (ValueError, TypeError):
        pretty, stale = str(iso), False
    note = (" These prices are more than a week old, so they may be behind the market."
            if stale else " Prices move as real drafts happen.")
    return f"I refresh these draft prices from Sleeper ADP — latest pull {pretty}.{note}"


@st.cache_data
def _load_rank_equiv():
    """position -> DataFrame(finish_rank, mean_pts), from the units table."""
    ref = pd.read_csv(SEAS / "rank_equiv_reference.csv")
    return {pos: g[["finish_rank", "mean_pts"]].reset_index(drop=True)
            for pos, g in ref.groupby("position")}


def _equiv_label(equiv, position, pts):
    """points -> '≈ WR24' via nearest mean_pts; '+' when below the table floor."""
    g = equiv.get(position)
    if g is None or pd.isna(pts):
        return ""
    idx = (g["mean_pts"] - pts).abs().idxmin()
    rank = int(g.loc[idx, "finish_rank"])
    suffix = "+" if pts < g["mean_pts"].min() else ""
    return f"≈ {position}{rank}{suffix}"


EXAMPLE_PLAYER_ID = "00-0041029"   # Jordyn Tyson (rookie WR, sizable gap)


def _worked_example(df):
    """Narrate one live row's default columns, mechanics only. Skips if absent."""
    row = df[df["player_id"] == EXAMPLE_PLAYER_ID]
    if row.empty:
        return
    r = row.iloc[0]
    if pd.isna(r.adp_pos_rank) or pd.isna(r.value_gap) or pd.isna(r.p50) \
            or not r.expected_equiv:
        return
    gap = int(r.value_gap)
    direction = "better than" if gap > 0 else ("worse than" if gap < 0 else "even with")
    eff_sent = (
        " His 2025 NFL Efficiency cell reads \"Rookie\" because he has no "
        "NFL season yet; the advanced view shows his college production "
        "context instead — and either way that column is context only, "
        "never part of the Gap."
        if r.eff_disp == "Rookie" else
        f" His 2025 NFL Efficiency %ile is {r.eff_disp} — context only, "
        "never part of the Gap."
        if r.eff_disp != "–" else
        " His 2025 NFL Efficiency cell reads \"–\" because he didn't play "
        "enough in 2025 to qualify — that column is context only, never "
        "part of the Gap.")
    st.markdown(
        f"**For example:** take {r.player} ({r.position}, {r.team}). His "
        f"draft price is ADP {r.adp_half_ppr:.0f}, which makes him the "
        f"number-{int(r.adp_pos_rank)} {r.position} by price — his "
        f"Position rank. Projections rank him number "
        f"{int(r.proj_pos_rank)} at the position — his Proj position rank "
        f"— so his Gap is {gap}: projections see him {abs(gap)} spots "
        f"{direction} his price. His range is Floor {r.p10:.0f}, Expected "
        f"{r.p50:.0f}, Ceiling {r.p90:.0f} season points; the percentile "
        f"next to Expected shows where he stands among {r.position}s on "
        f"this board — his Expected sits at the "
        f"{_ordinal(int(round(r.p50_pct)))} percentile, higher than about "
        f"{int(round(r.p50_pct))} in 100 {r.position}s here. His Top-12 "
        f"chance is {r.top12_pct:.0f}%: of many players with his expected "
        f"points, about {r.top12_pct:.0f} in 100 finished top-12 at the "
        f"position.{eff_sent} What you do with that is your call.")


# Sortable display column -> the underlying NUMERIC field it sorts on (never the
# display string). Every sentinel — Gainwell's blank Gap/Proj rank, and the
# "Rookie"/"–" efficiency rows — is NaN in its numeric key, so na_position="last"
# sinks it to the BOTTOM in BOTH directions. Insertion order sets the selector order;
# "Gap" is first so it is the default. Display strings are never touched by sorting.
SORT_KEYS = {
    "Gap": "value_gap",                              # numeric gap, not "-11"/"–"
    "Draft Price (ADP)": "adp_half_ppr",
    "Position rank": "adp_pos_rank",
    "Proj position rank": "proj_pos_rank",
    "Expected": "p50",                               # numeric p50 only, ignore the percentile suffix
    "Floor": "p10",
    "Ceiling": "p90",
    "Top-12 chance": "top12_pct",
    "NFL Efficiency %ile (pos)": "pct_among_2025_qualifiers",  # NaN for Rookie/– rows
    "Talent Score (2026)": "talent_score_num",       # NaN (dash) rows sink null-last
    "Rookie Score (2026)": "rookie_score_num",       # NaN (dash) rows sink null-last
}


def _sort_board(view, sort_label, ascending):
    """Sort the board by the numeric field behind a display column. Sentinels (NaN
    sort keys) always sink to the bottom, in both ascending and descending order
    (na_position='last' is direction-independent). Stable so ties keep board order.
    Display strings are unchanged — this is a display-layer sort only."""
    key = SORT_KEYS.get(sort_label, "value_gap")
    return view.sort_values(key, ascending=ascending, na_position="last", kind="stable")


# Single source of truth for each display column's label + tooltip, shared by the
# st.dataframe column_config (legacy default view) AND the st.table page's visible
# "what each column means" guide (use_table=True) — so the tooltip strings are the
# SAME Python string in both places (byte-identical by construction, design 4m).
_TXT, _NUM = "text", "number"
COLUMN_META = [
    ("player_disp", _TXT, "Player",
     "⚠ beside a name = limited data — extra-wide uncertainty; details in the advanced view", {}),
    ("position_disp", _TXT, "Pos",
     "† = the Gap comparison is untested for QBs and TEs in changing situations — details in advanced view",
     {"width": "small"}),
    ("team", _TXT, "Team", "Blank = not signed with a team yet", {"width": "small"}),
    ("adp_half_ppr", _NUM, "Draft Price (ADP)",
     "Average draft position — the spot where drafters are actually taking this player",
     {"format": "%.1f"}),
    ("adp_pos_rank", _NUM, "Position rank",
     "His rank at his position by draft price (1 = first off the board at the position)",
     {"format": "%d", "width": "small"}),
    ("proj_pos_rank", _NUM, "Proj position rank",
     "His rank at his position by season projection", {"format": "%d", "width": "small"}),
    ("gap_disp", _TXT, "Gap",
     "Position rank minus Proj position rank. Positive = projections see him finishing "
     "better than his price; negative = worse. A group pattern, not a rating of this "
     "player. '–' = no gap available for this row.", {"width": "small"}),
    ("p10", _NUM, "Floor",
     "A tough season: about 1 in 10 players finish below this number (season points). "
     "Its ≈ finish equivalent is in the advanced view.", {"format": "%.0f"}),
    ("p50_disp", _TXT, "Expected (Percentile)",
     "The middle of the range — half of players finish above this, half below. The "
     "number in parentheses is the percentile: where his Expected stands among players "
     "at his position on this board (Floor and Ceiling rank players in the same order, "
     "so one percentile covers all three).", {}),
    ("p90", _NUM, "Ceiling",
     "A great season: about 1 in 10 players finish above this number. Its ≈ finish "
     "equivalent is in the advanced view.", {"format": "%.0f"}),
    ("top12_pct", _NUM, "Top-12 chance", "Chance to finish top-12 at his position",
     {"format": "%.0f%%"}),
    ("eff_disp", _TXT, "NFL Efficiency %ile (pos)",
     "0–100, within his position only: where his 2025 NFL efficiency ranked among "
     "players at his position who played enough to qualify — 88 means more efficient "
     "than 88% of them. Context only — NOT part of the value signal; testing showed it "
     "does not predict draft value. 'Rookie' = no NFL data yet; college production "
     "context is in the advanced view. '–' = not enough 2025 playing time to qualify.", {}),
    ("talent_disp", _TXT, "Talent Score (2026)",
     "My model-based estimate of what a player does per opportunity, net of situation "
     "where that's identifiable — shown as score [range]. The range is the honest "
     "uncertainty; † = lower-confidence, ‡ = lowest-confidence. Players with no NFL "
     "data show '–' (see Rookie Score). Context only — never part of the Gap or any "
     "other column. It ranks NFL players against NFL players.", {}),
    ("rookie_disp", _TXT, "Rookie Score (2026)",
     "A college-production read for 2026 rookies (RB/WR/TE), scaled against past "
     "drafted prospects — NOT the same scale as the Talent Score. '–' for anyone "
     "with NFL data (see Talent Score), for rookie QBs (no college QB instrument "
     "ships), and for rookies whose college data couldn't be matched. Context only — "
     "never part of the Gap or any other column.", {"width": "small"}),
]
_DISPLAY_COLS = [m[0] for m in COLUMN_META]
_EXPORT_NAMES = {m[0]: m[2] for m in COLUMN_META}       # colkey -> on-screen label
_STYLE_FMT = {m[0]: ("{:.1f}" if m[4].get("format") == "%.1f"
                     else "{:.0f}%" if m[4].get("format") == "%.0f%%"
                     else "{:.0f}") for m in COLUMN_META if m[1] == _NUM}


def _column_config():
    """Build the st.dataframe column_config from COLUMN_META (identical output to the
    former inline config — verified by the app.py board AppTest)."""
    cfg = {}
    for key, kind, label, help_, extra in COLUMN_META:
        col = st.column_config.NumberColumn if kind == _NUM else st.column_config.TextColumn
        cfg[key] = col(label, help=help_, **extra)
    return cfg


def _rg_color(ratio):
    """Weekly-Fantasy-uniform red→green tint. ratio in [0,1]: 0 = red (rgb 255,82,82),
    ~0.5 = amber, 1 = green (rgb 0,200,82). Same formula as the Weekly Fantasy table's
    rank_color / total_color, so the two tables read identically."""
    ratio = max(0.0, min(1.0, ratio))
    r = int(round(255 * (1 - ratio)))
    g = int(round(82 + 118 * ratio))
    return f"rgb({r},{g},82)"


def _style_board(view, gap_cap):
    """pandas Styler callback (axis=None), uniform with the Weekly Fantasy table
    (Joseph-ratified color coding, 2026-07-13):
      • Gap — the headline value signal: bold + enlarged, red→green DIVERGING around
        zero (gap_cap is the symmetric ±full-saturation bound), so negative = red,
        zero ≈ amber, positive = green. Blank '–' rows stay bold, uncolored.
      • Top-12 chance and NFL Efficiency %ile — red→green SEQUENTIAL over 0–100.
    Underlying numeric series come from `view` positionally — the displayed frame is
    `view[cols]`, same row order — so the tint tracks the true number, not the
    formatted string (Gap's and efficiency's numeric keys are NaN for '–'/Rookie, so
    those cells stay untinted)."""
    gap = view["value_gap"].to_numpy()
    top12 = view["top12_pct"].to_numpy()
    eff = view["pct_among_2025_qualifiers"].to_numpy()
    cap = gap_cap if (gap_cap and gap_cap > 0) else 1.0

    def _style(df):
        styles = pd.DataFrame("", index=df.index, columns=df.columns)
        if "gap_disp" in df.columns:
            loc = df.columns.get_loc("gap_disp")
            for i, v in enumerate(gap):
                if pd.isna(v):
                    styles.iloc[i, loc] = "font-weight: 700"
                else:
                    ratio = (max(-cap, min(cap, v)) + cap) / (2 * cap)
                    styles.iloc[i, loc] = (f"color: {_rg_color(ratio)}; "
                                           "font-weight: 700; font-size: 15px")
        for col, src in (("top12_pct", top12), ("eff_disp", eff)):
            if col in df.columns:
                loc = df.columns.get_loc(col)
                for i, v in enumerate(src):
                    if not pd.isna(v):
                        styles.iloc[i, loc] = (f"color: {_rg_color(v / 100.0)}; "
                                               "font-weight: 600")
        return styles
    return _style


# Board scroll-box height is the shared site-wide TABLE_HEIGHT (~20 rows visible; all
# 180 scroll inside) — imported from dashboard_chrome so every long table matches.


def render():
    df = _load_board_2026()

    with st.expander("How to read this board", expanded=False):
        st.markdown(
            "This board compares season projections with where players are "
            "actually being drafted — their draft price. **Position rank** "
            "is his rank at his position by draft price; **Proj position "
            "rank** is his rank at his position by season projection. "
            "**Gap** is the difference: positive means projections see him "
            "finishing better than his price, negative means worse. A † on "
            "the Pos cell marks the one group where that comparison is "
            "untested (QBs and TEs in changing situations); every other "
            "row's group has a tested track record. **Floor, Expected, and "
            "Ceiling** show a realistic range for his season in points — "
            "most players land inside their range, and I checked that on "
            "five past seasons; the percentile in parentheses after "
            "Expected shows where he stands among players at his position "
            "on this board. **Top-12 chance** turns the range into a simple "
            "percentage, like a weather forecast. **NFL Efficiency %ile "
            "(pos)** is context only — it ranks his 2025 efficiency within "
            "his position, is not part of the Gap, and is never mixed into "
            "any other column; 'Rookie' means no NFL "
            "data yet, and '–' means not enough 2025 playing time to "
            "qualify. A ⚠ beside a name means I have limited data on "
            "that player and his range is extra-wide. Everything here "
            "describes patterns across many players — it cannot guarantee "
            "what any single player will do.")
        _worked_example(df)
        # The column tooltips also shown as a visible guide (mobile has no hover),
        # inside this collapsed expander so nothing about it renders open on load.
        # Strings from COLUMN_META — byte-identical to the column_config tooltips.
        st.markdown("**What each column means:**")
        for _key, _kind, _label, _help, _extra in COLUMN_META:
            st.markdown(f"- **{_label}** — {_help}")
        st.caption("Sort with these controls — they order the whole board numerically, "
                   "with no-data rows (Rookie / – / blank) always at the bottom.")

    # Filter + sort toolbar: one grouped row (Position · search · sort · order) so the
    # controls read as a single bar instead of sprawling down the page. Explicit numeric
    # sort — st.dataframe's header-click sorts the display strings lexicographically (see
    # audit/board_sort_diagnosis_2026-07-13.md); this routes every sortable column through
    # one numeric path with sentinels pinned to the bottom. Default: Gap, descending.
    with st.container(border=True):
        fc1, fc2, fc3, fc4 = st.columns([1.4, 1.3, 1.3, 1.15])
        with fc1:
            pos = st.multiselect("Position", ["QB", "RB", "WR", "TE"],
                                 default=["QB", "RB", "WR", "TE"], key="db26_pos")
        with fc2:
            name = st.text_input("Player search", "", key="db26_search")
        with fc3:
            sort_label = st.selectbox("Sort by", list(SORT_KEYS), index=0, key="db26_sortby")
        with fc4:
            order = st.radio("Order", ["Descending", "Ascending"], index=0,
                             horizontal=True, key="db26_sortdir")
        st.caption("Note: clicking a column header sorts too, but Gap, Expected and "
                   "Efficiency won't sort correctly that way — a Streamlit limitation. "
                   "Use the controls above.")

    view = df[df.position.isin(pos)]
    if name.strip():
        view = view[view.player.str.contains(name.strip(), case=False, na=False)]
    view = _sort_board(view, sort_label, ascending=(order == "Ascending"))

    cols = _DISPLAY_COLS
    st.caption(_adp_caption())
    st.caption(SCALE_DISCLOSURE)   # two-cell scale warning (R12), beside the columns
    # Fixed-height scroll box holds all 180 rows (TABLE_HEIGHT ≈ 20 rows visible), so no
    # row cap is needed. The key encodes the current sort AND the filter state (position,
    # search, row count), so the grid REMOUNTS on any change to the visible rows — this
    # discards st.dataframe's sticky client-side header-sort (which otherwise survives a
    # filter change and overrides the control) so the Sort-by control always wins. See
    # audit/board_sort_diagnosis_2026-07-13.md.
    # Symmetric ±bound for the diverging Gap tint, taken from the FULL board so the
    # shading stays stable when the position filter changes the visible rows.
    _cap = df["value_gap"].abs().max()
    gap_cap = float(_cap) if pd.notna(_cap) else 20.0
    st.dataframe(
        view[cols].style.apply(_style_board(view, gap_cap), axis=None),
        width="stretch", height=TABLE_HEIGHT, hide_index=True,
        key=("db26_grid_"
             f"{SORT_KEYS[sort_label]}_{order}_"
             f"{'-'.join(sorted(pos))}_{name.strip().lower()}_{len(view)}"),
        column_config=_column_config())

    # CSV export — always the FULL sorted view (uncapped by the Top-40 display),
    # with the on-screen column names (design 4m: full-board export unchanged).
    st.download_button(
        "Download board (CSV)",
        data=view[cols].rename(columns=_EXPORT_NAMES)
                       .to_csv(index=False).encode("utf-8"),
        file_name="draft_value_2026.csv", mime="text/csv",
        key="db26_dl")

    show_adv = st.checkbox("Show advanced view (full percentiles, raw "
                           "metrics, verbatim research labels)",
                           key="db26_adv")
    if show_adv:
        st.markdown("**Advanced view** — the technical layer behind the "
                    "plain columns above.")
        adv_cols = ["player", "position", "adp_pos_rank", "proj_pos_rank",
                    "value_gap",
                    "p10", "p25", "p50", "p75", "p90",
                    "floor_equiv", "expected_equiv", "ceiling_equiv",
                    "p_top12", "p_top24", "p_bust", "band_confidence",
                    "badge", "data_note", "rookie_note", "talent_pct",
                    "population", "metric_name", "raw_value",
                    "pct_among_2025_qualifiers", "pct_among_2026_drafted_class",
                    "talent_w", "college_share", "cell_note"]
        st.dataframe(
            view[adv_cols], width="stretch", height=TABLE_HEIGHT, hide_index=True,
            column_config={
                "floor_equiv": st.column_config.TextColumn(
                    "≈ finish (Floor)",
                    help="Typical-season rank equivalent of the Floor "
                         "(P10) points number"),
                "expected_equiv": st.column_config.TextColumn(
                    "≈ finish (Expected)"),
                "ceiling_equiv": st.column_config.TextColumn(
                    "≈ finish (Ceiling)",
                    help="Typical-season rank equivalent of the Ceiling "
                         "(P90) points number"),
                "badge": st.column_config.TextColumn(
                    "Signal check",
                    help="Whether the projections-vs-price comparison has "
                         "a tested track record for players in this group "
                         "— a pattern confirmed across many similar "
                         "players in five past seasons, not a rating of "
                         "this player"),
                "data_note": st.column_config.TextColumn(
                    "Data note",
                    help="Flags players my ranges know least about"),
                "rookie_note": st.column_config.TextColumn("Rookie context"),
                "talent_pct": st.column_config.NumberColumn(
                    "2025 Efficiency", format="%.0f",
                    help="Context only — this number is NOT part of the "
                         "value signal and has been shown not to predict "
                         "draft value. Veterans: efficiency percentile "
                         "among 2025 qualifiers at his position. Rookies: "
                         "college production percentile among drafted 2026 "
                         "rookies instead — a different measure, not "
                         "directly comparable."),
            })
        st.markdown("**Research labels — verbatim licensed wording, with the "
                    "plain reading beside it** (plain versions pending "
                    "ratification):")
        st.dataframe(view[["player", "signal_status", "plain_label",
                           "disclosure"]].rename(columns={
                               "signal_status": "licensed label (verbatim)",
                               "plain_label": "plain reading",
                               "disclosure": "talent disclosure (verbatim)"}),
                     width="stretch", height=TABLE_HEIGHT, hide_index=True)
        st.markdown("**Term definitions:**")
        for term, definition in ADV_DEFS:
            st.markdown(f"- **{term}** — {definition}")
        facet_cols = [c for c in view.columns if c.startswith("tal_")]
        if facet_cols:
            st.markdown("**Talent Score facet detail** — per-facet standardized "
                        "read (z) and its reliability (w) behind each score; "
                        "columns apply per position, blank elsewhere. "
                        f"{SCALE_DISCLOSURE}")
            st.dataframe(view[view["talent_disp"] != "–"][["player", "position",
                         "talent_disp", "talent_w", "college_share"] + facet_cols],
                         width="stretch", height=TABLE_HEIGHT, hide_index=True)

    st.markdown("---")
    st.caption(
        "**About these numbers.** The point estimates are the market's — "
        "powered by Sleeper's projections vs the draft market. The ranges, "
        "chances, and bust risk are my contribution: when I drew these "
        "ranges for past seasons, about 8 in 10 players finished inside "
        "their 80% range — almost exactly what the math promises (checked "
        "on 900 player-seasons, 2021–2025). The projections-vs-price signal "
        "has a tested track record as a group pattern for the player groups "
        "marked ✓ — including a check that it wasn't just projections being "
        "newer than draft prices — and it was tested against prices from a "
        "large best-ball drafting platform, a slightly different format than "
        "classic leagues. It is not yet tested for QBs and TEs in changing "
        "situations. The 2025 Efficiency column (advanced view) is context "
        "only; testing "
        "showed it does not predict draft value, and it is never mixed into "
        "any other number here. All of this describes patterns across many "
        "players — none of it is a guarantee, or a recommendation, about "
        "any single player.")
