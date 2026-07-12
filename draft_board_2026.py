"""2026 Draft Board tab — public revamp (2026-07-12): plain language by
default, technical detail in the advanced view.

License discipline: the plain strings TRANSLATE the licensed claims — never
strengthen, never weaken. The verbatim licensed strings ship in-schema and in
the advanced view. Plain translations pend Joseph's ratification. Forbidden
everywhere: buy/sell/fade/target/steal/reach language, tier names or colors,
accuracy or hit-rate claims, player-level calls, sub-group claims. The talent
column is descriptive only and is never combined with any other column.
Data: phase4_band_2026.csv + talent_index_2026.csv (frozen artifacts, read-only).
"""
from pathlib import Path

import pandas as pd
import streamlit as st

_HERE = Path(__file__).resolve().parent
SEAS = _HERE / "fantasy" / "seasonal_projections"

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
        "most of last season), we tested this projections-vs-price comparison "
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
    ("freshness-controlled", "we checked that the signal isn't explained by "
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
    # Expected as "VALUE (Nth %ile)" — percentile within position among this
    # board's rows (display transform; no new data). Expected ONLY: the band
    # spread is flat per position, so Floor/Ceiling percentiles would be
    # identical copies of this one.
    pct = df.groupby("position")["p50"].rank(pct=True) * 100
    df["p50_pct"] = pct
    df["p50_disp"] = [
        f"{v:.0f} ({_ordinal(int(round(p)))} %ile)"
        if pd.notna(v) and pd.notna(p) else ""
        for v, p in zip(df["p50"], pct)]
    # rank equivalents (display-only units table; see build_rank_equiv_reference.py)
    equiv = _load_rank_equiv()
    for src, dst in (("p10", "floor_equiv"), ("p50", "expected_equiv"),
                     ("p90", "ceiling_equiv")):
        df[dst] = [_equiv_label(equiv, p, v)
                   for p, v in zip(df["position"], df[src])]
    return df


def _ordinal(n):
    """1 -> '1st', 72 -> '72nd', 11 -> '11th'."""
    if 10 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


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


def render():
    df = _load_board_2026()

    st.title("📋 2026 Draft Board")

    with st.expander("How to read this board", expanded=True):
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
            "most players land inside their range, and we checked that on "
            "five past seasons; the percentile in parentheses after "
            "Expected shows where he stands among players at his position "
            "on this board. **Top-12 chance** turns the range into a simple "
            "percentage, like a weather forecast. **NFL Efficiency %ile "
            "(pos)** is context only — it ranks his 2025 efficiency within "
            "his position, is not part of the Gap, and is never mixed into "
            "any other column; 'Rookie' means no NFL "
            "data yet, and '–' means not enough 2025 playing time to "
            "qualify. A ⚠ beside a name means we have limited data on "
            "that player and his range is extra-wide. Everything here "
            "describes patterns across many players — it cannot guarantee "
            "what any single player will do.")
        _worked_example(df)

    fc1, fc2 = st.columns([1.2, 1.4])
    with fc1:
        pos = st.multiselect("Position", ["QB", "RB", "WR", "TE"],
                             default=["QB", "RB", "WR", "TE"], key="db26_pos")
    with fc2:
        name = st.text_input("Player search", "", key="db26_search")

    view = df[df.position.isin(pos)]
    if name.strip():
        view = view[view.player.str.contains(name.strip(), case=False, na=False)]
    view = view.sort_values("adp_half_ppr")     # market order — neutral default

    cols = ["player_disp", "position_disp", "team", "adp_half_ppr",
            "adp_pos_rank", "proj_pos_rank", "value_gap",
            "p10", "p50_disp", "p90",
            "top12_pct", "eff_disp"]
    st.caption("Draft prices are Sleeper ADP as of July 10, 2026; "
               "prices move as real drafts happen.")
    st.dataframe(
        view[cols], width="stretch", height=520, hide_index=True,
        column_config={
            "player_disp": st.column_config.TextColumn(
                "Player",
                help="⚠ beside a name = limited data — extra-wide "
                     "uncertainty; details in the advanced view"),
            "position_disp": st.column_config.TextColumn(
                "Pos", width="small",
                help="† = the Gap comparison is untested for QBs and TEs "
                     "in changing situations — details in advanced view"),
            "team": st.column_config.TextColumn("Team", width="small",
                                                help="Blank = not signed with a team yet"),
            "adp_half_ppr": st.column_config.NumberColumn(
                "Draft Price (ADP)", format="%.1f",
                help="Average draft position — the spot where drafters are "
                     "actually taking this player"),
            "adp_pos_rank": st.column_config.NumberColumn(
                "Position rank", format="%d", width="small",
                help="His rank at his position by draft price (1 = first "
                     "off the board at the position)"),
            "proj_pos_rank": st.column_config.NumberColumn(
                "Proj position rank", format="%d", width="small",
                help="His rank at his position by season projection"),
            "value_gap": st.column_config.NumberColumn(
                "Gap", format="%.0f", width="small",
                help="Position rank minus Proj position rank. Positive = "
                     "projections see him finishing better than his price; "
                     "negative = worse. A group pattern, not a rating of "
                     "this player."),
            "p10": st.column_config.NumberColumn(
                "Floor", format="%.0f",
                help="A tough season: about 1 in 10 players finish below "
                     "this number (season points). Its ≈ finish equivalent "
                     "is in the advanced view."),
            "p50_disp": st.column_config.TextColumn(
                "Expected",
                help="The middle of the range — half of players finish "
                     "above this, half below. The percentile in "
                     "parentheses is where his Expected stands among "
                     "players at his position on this board (Floor and "
                     "Ceiling rank players in the same order, so one "
                     "percentile covers all three)."),
            "p90": st.column_config.NumberColumn(
                "Ceiling", format="%.0f",
                help="A great season: about 1 in 10 players finish above "
                     "this number. Its ≈ finish equivalent is in the "
                     "advanced view."),
            "top12_pct": st.column_config.NumberColumn(
                "Top-12 chance", format="%.0f%%",
                help="Chance to finish top-12 at his position"),
            "eff_disp": st.column_config.TextColumn(
                "NFL Efficiency %ile (pos)",
                help="0–100, within his position only: where his 2025 NFL "
                     "efficiency ranked among players at his position who "
                     "played enough to qualify — 88 means more efficient "
                     "than 88% of them. Context "
                     "only — NOT part of the value signal; testing showed "
                     "it does not predict draft value. 'Rookie' = no NFL "
                     "data yet; college production context is in the "
                     "advanced view. '–' = not enough 2025 playing time "
                     "to qualify."),
        })

    st.download_button(
        "Download board (CSV)",
        data=view[cols].to_csv(index=False).encode("utf-8"),
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
                    "pct_among_2025_qualifiers", "pct_among_2026_drafted_class"]
        st.dataframe(
            view[adv_cols], width="stretch", hide_index=True,
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
                    help="Flags players our ranges know least about"),
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
                     width="stretch", hide_index=True)
        st.markdown("**Term definitions:**")
        for term, definition in ADV_DEFS:
            st.markdown(f"- **{term}** — {definition}")

    st.markdown("---")
    st.caption(
        "**About these numbers.** The point estimates are the market's — "
        "powered by Sleeper's projections vs the draft market. The ranges, "
        "chances, and bust risk are our contribution: when we drew these "
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
