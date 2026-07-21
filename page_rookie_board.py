"""Rookie Board page — the rookie hit-probability product (ships regardless; research REJECTED).

Additive page: reads the pre-built board CSVs in fantasy/rookie/board_data/ (no model runs here,
no network). The hit-probability research was fired 2026-07-20 and REJECTED (college/athletic add no
measured edge beyond draft capital: full AUC 0.843 vs draft-only 0.838, 2019-2023 hold-out). The
disclosure below rides on every surface. College grade/efficiency values are per PFF.
"""
from pathlib import Path
import pandas as pd
import streamlit as st

_HERE = Path(__file__).resolve().parent
_BOARD = _HERE / "fantasy" / "rookie" / "board_data"
_CLASSES = [2026, 2025, 2024]

DISCLOSURE = (
    "Backtested, not live-validated (2019-2023 hold-out classes). At this sample, college production "
    "and athletic testing added no measured edge beyond draft capital — the hit probability largely "
    "tracks draft position (full-model AUC 0.843 vs draft-capital-only 0.838, one-shot backtest). "
    "First live test: end of the 2026 season. QB and TE per-position numbers are underpowered."
)

HIT_DEF = (
    "Hit % = share of historical players with this profile who had at least one startable season "
    "(RB2+/WR2+/etc. — top-24 in season-total half-PPR) in their first three years. A best-of-three "
    "outcome, not a per-year rate."
)
THREE_MODEL = (
    "Three views of the same hit definition — 'Draft-Capital' uses only where a player was picked; "
    "'College' uses only his college production + athletic testing; 'Full' combines both. They land "
    "close together because the college signal, while real, is already reflected in draft position "
    "(see guide)."
)
PCT_HELP = (
    "Percentile rank within this player's position across every drafted QB/RB/WR/TE from the "
    "2015–2026 draft classes — e.g. 80 means higher than 80% of same-position drafted rookies since "
    "2015. Higher = better."
)

_COLS = {
    "name": "Player", "position": "Pos", "team": "Team", "draft_round": "Rd", "draft_pick": "Pick",
    "hit_prob_draft": "Draft-Capital Hit-%", "hit_prob_college": "College Hit-%",
    "hit_prob_full": "Full Hit-%", "proj_ppg": "Rookie Proj (PPG)", "talent_score": "College Talent",
    "pff_grade": "College Grade", "pct_pff_grade": "Grade (Percentile)",
    "pct_speed_score": "Athleticism (Percentile)", "pct_cfb_final_dom": "Production (Percentile)",
}


@st.cache_data(ttl=3600)
def _load(cls: int) -> pd.DataFrame:
    f = _BOARD / f"rookie_board_{cls}.csv"
    return pd.read_csv(f) if f.exists() else pd.DataFrame()


def render():
    st.title("🧬 Rookie Board")
    st.caption("A per-position hit-probability score for drafted rookies — plus the rookie-year "
               "projection, a college talent score, and college/athletic percentiles.")
    st.warning("**Backtested, not live-validated.** " + DISCLOSURE)

    avail = [c for c in _CLASSES if not _load(c).empty]
    if not avail:
        st.info("Rookie board data not built yet — run `python fantasy/rookie/build_rookie_board.py`.")
        return

    c1, c2 = st.columns([1, 1])
    cls = c1.selectbox("Draft class", avail, index=0)
    df = _load(cls)
    pos = c2.selectbox("Position", ["All", "QB", "RB", "WR", "TE"], index=0)
    if pos != "All":
        df = df[df["position"] == pos]

    df = df.sort_values("hit_prob_full", ascending=False)
    show = df[[c for c in _COLS if c in df.columns]].rename(columns=_COLS)

    st.caption("**Three hit-% columns.** " + THREE_MODEL)
    st.dataframe(
        show, hide_index=True, width="stretch", height=min(720, 60 + 35 * len(show)),
        column_config={
            "Draft-Capital Hit-%": st.column_config.NumberColumn(
                format="%.0f", help="Hit % from draft position ONLY (the market). " + THREE_MODEL),
            "College Hit-%": st.column_config.NumberColumn(
                format="%.0f", help="Hit % from college production + athletic testing ONLY — no draft "
                                    "capital. " + THREE_MODEL),
            "Full Hit-%": st.column_config.NumberColumn(
                format="%.0f", help="Hit % from all features (draft + college + athletic). " + HIT_DEF
                                    + " " + DISCLOSURE),
            "Rookie Proj (PPG)": st.column_config.NumberColumn(
                format="%.1f", help="Per-game half-PPR rate from draft capital, athletic testing, and "
                                    "landing-spot team context. It does NOT model depth-chart role or "
                                    "playing time — a rookie who backs up a healthy starter still shows a "
                                    "per-game number as if he plays. Read it as an if-on-the-field rate, "
                                    "not a games-played forecast."),
            "College Talent": st.column_config.NumberColumn(
                format="%.2f", help="Descriptive college talent score, read-only from the talent library "
                                    "— RB/WR/TE only (no QB), 2026 class only, and only a subset of it. "
                                    "Blank everywhere else by design — never backfilled."),
            "College Grade": st.column_config.NumberColumn(
                format="%.1f", help="Final college season offensive grade, per PFF."),
            "Grade (Percentile)": st.column_config.NumberColumn(format="%.0f", help=PCT_HELP),
            "Athleticism (Percentile)": st.column_config.NumberColumn(format="%.0f", help=PCT_HELP),
            "Production (Percentile)": st.column_config.NumberColumn(format="%.0f", help=PCT_HELP),
        },
    )
    st.caption(
        f"Class of {cls} · {len(show)} rookies · {HIT_DEF} Rookie Proj is a per-game rate that assumes "
        "the player is on the field — it does not model depth-chart role, so a projected backup still "
        "shows a number. College Talent covers RB/WR/TE only (no QB) and the 2026 class only. "
        "Percentiles are within-position across the 2015–2026 drafted-skill panel. College "
        "grade/efficiency values per PFF. Hit probability and projection are backtested, not live-validated."
    )
