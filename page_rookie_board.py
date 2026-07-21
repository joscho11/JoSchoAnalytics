"""Rookie Board page — the rookie hit-probability product (ships regardless; research REJECTED).

Additive page: reads the pre-built board CSVs in fantasy/rookie/board_data/ (no model runs here,
no network). The hit-probability research was fired 2026-07-20 and REJECTED (college/athletic add no
measured edge beyond draft capital: full AUC 0.843 vs draft-only 0.838, 2019-2023 hold-out). The
disclosure below rides on every surface. College grade/efficiency values are per PFF.

The rookie-year PROJECTION column is sourced from the new RB season-total model
(fantasy/projections/, results/rb_rookie_board_projection.csv) — RB only for now (WR/TE/QB are later,
separate builds). The old starved per-game `rookie_ppg` surface is retired from display; its pkl is
untouched in-repo. The projection is shown beside Sleeper's projection with a difference column; it
makes no claim to beat Sleeper.
"""
import sys
from pathlib import Path
import pandas as pd
import streamlit as st

_HERE = Path(__file__).resolve().parent
_BOARD = _HERE / "fantasy" / "rookie" / "board_data"
_PROJ = _HERE / "fantasy" / "projections" / "results" / "rb_rookie_board_projection.csv"
_CLASSES = [2026, 2025, 2024]

sys.path.insert(0, str(_HERE / "fantasy" / "seasonal_projections"))
try:
    from _utils import norm_name
except Exception:                                             # pragma: no cover - defensive
    def norm_name(s):
        return str(s).lower().strip()

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
PROJ_HELP = (
    "Projected SEASON-TOTAL half-PPR points for the rookie year, from the RB season-total model "
    "(veteran+rookie models under fantasy/projections/). It models opportunity (vacated backfield "
    "share, drafting-team context, ADP-implied role) and college/athletic/draft profile — so a "
    "back drafted into a crowded room projects lower than his draft slot alone would suggest. "
    "For the 2026 class this is the deploy projection; for 2024/2025 it is the walk-forward "
    "out-of-sample projection. Backtested 2021–2025 (pooled Spearman +0.69 vs actual season totals), "
    "NOT live-validated. RB only for now — WR/TE/QB projections are separate later builds."
)
SLEEPER_HELP = (
    "Sleeper's published season-total half-PPR projection (the market), shown for context. The model "
    "does NOT claim to beat Sleeper — on 2021–2025 Sleeper ranks rookies/vets slightly better "
    "(Spearman +0.80 vs the model's +0.69). It is shown side-by-side by design, not as a scoreboard."
)
DIFF_HELP = (
    "Projection − Sleeper (season-total half-PPR). Positive = the model is higher than the market on "
    "this player; negative = lower. Descriptive only — it is not a recommendation."
)

_COLS = {
    "name": "Player", "position": "Pos", "team": "Team", "draft_round": "Rd", "draft_pick": "Pick",
    "hit_prob_draft": "Draft-Capital Hit-%", "hit_prob_college": "College Hit-%",
    "hit_prob_full": "Full Hit-%", "projection": "Proj (season ½-PPR)", "sleeper": "Sleeper Proj",
    "diff": "Diff vs Sleeper", "talent_score": "College Talent",
    "pff_grade": "College Grade", "pct_pff_grade": "Grade (Percentile)",
    "pct_speed_score": "Athleticism (Percentile)", "pct_cfb_final_dom": "Production (Percentile)",
}


@st.cache_data(ttl=3600)
def _load(cls: int) -> pd.DataFrame:
    f = _BOARD / f"rookie_board_{cls}.csv"
    return pd.read_csv(f) if f.exists() else pd.DataFrame()


@st.cache_data(ttl=3600)
def _load_proj() -> pd.DataFrame:
    """RB season-total projection join file (norm_name, position, entry_class, projection, sleeper, diff)."""
    if not _PROJ.exists():
        return pd.DataFrame(columns=["norm_name", "position", "entry_class", "projection", "sleeper", "diff"])
    return pd.read_csv(_PROJ)


def _attach_projection(df: pd.DataFrame, cls: int) -> pd.DataFrame:
    """Left-join the RB projection onto the board rows (RB only; blank for QB/WR/TE by design)."""
    proj = _load_proj()
    for c in ("projection", "sleeper", "diff"):
        df[c] = pd.NA
    if proj.empty or df.empty:
        return df
    proj = proj[proj["entry_class"] == cls]
    df = df.copy()
    df["_nn"] = df["name"].map(norm_name)
    key = proj.set_index(["norm_name", "position"])[["projection", "sleeper", "diff"]]
    idx = list(zip(df["_nn"], df["position"]))
    for col in ("projection", "sleeper", "diff"):
        s = key[col]
        df[col] = [s.get(k) if k in s.index else pd.NA for k in idx]
    return df.drop(columns=["_nn"])


def render():
    st.title("🧬 Rookie Board")
    st.caption("A per-position hit-probability score for drafted rookies — plus a season-total "
               "projection (RB), a college talent score, and college/athletic percentiles.")
    st.warning("**Backtested, not live-validated.** " + DISCLOSURE)

    avail = [c for c in _CLASSES if not _load(c).empty]
    if not avail:
        st.info("Rookie board data not built yet — run `python fantasy/rookie/build_rookie_board.py`.")
        return

    c1, c2 = st.columns([1, 1])
    cls = c1.selectbox("Draft class", avail, index=0)
    df = _load(cls)
    df = _attach_projection(df, cls)
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
            "Proj (season ½-PPR)": st.column_config.NumberColumn(format="%.0f", help=PROJ_HELP),
            "Sleeper Proj": st.column_config.NumberColumn(format="%.0f", help=SLEEPER_HELP),
            "Diff vs Sleeper": st.column_config.NumberColumn(format="%+.0f", help=DIFF_HELP),
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
        f"Class of {cls} · {len(show)} rookies · {HIT_DEF} **Proj (season ½-PPR)** is the projected "
        "season-total half-PPR from the RB season-total model — RB only for now (WR/TE/QB coming), "
        "shown beside Sleeper's projection with the difference; no claim to beat Sleeper. College "
        "Talent covers RB/WR/TE only (no QB) and the 2026 class only. Percentiles are within-position "
        "across the 2015–2026 drafted-skill panel. College grade/efficiency values per PFF. Hit "
        "probability and projection are backtested, not live-validated."
    )
