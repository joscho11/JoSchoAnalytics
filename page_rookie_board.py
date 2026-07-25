"""Rookie Board page — the rookie hit-probability product (ships regardless; research REJECTED).

Additive page: reads the pre-built board CSVs in fantasy/rookie/board_data/ (no model runs here,
no network). The hit-probability research was fired 2026-07-20 and REJECTED (college/athletic add no
measured edge beyond draft capital: full AUC 0.843 vs draft-only 0.838, 2019-2023 hold-out). The
disclosure below rides on every surface.

The rookie-year PROJECTION columns are sourced from the RB, WR, and TE season-total models
(`fantasy/projections/results/*_rookie_board_projection.csv`). The old starved per-game
`rookie_ppg` surface is retired from display; its pkl is untouched in-repo. The projections are
shown beside Sleeper's projection when Sleeper has published one, with a descriptive difference;
they make no claim to beat Sleeper.
"""
import sys
from pathlib import Path
import pandas as pd
import streamlit as st

_HERE = Path(__file__).resolve().parent
_BOARD = _HERE / "fantasy" / "rookie" / "board_data"
_PROJ_DIR = _HERE / "fantasy" / "projections" / "results"
_PROJ_FILES = ["rb_rookie_board_projection.csv", "wr_rookie_board_projection.csv",
               "te_rookie_board_projection.csv", "qb_rookie_board_projection.csv"]  # RB+WR+TE rookie;
# QB rookie arm HELD (too thin — file is empty), so QB rookies show no projection. QB non-rookie
# projections ship as a data export only (results/qb_projection_2026.csv), not on this rookie board.
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
    "in their first three years: top-24 for RB/WR or top-12 for QB/TE in season-total half-PPR. "
    "A best-of-three outcome, not a per-year rate."
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
    "Projected SEASON-TOTAL half-PPR points for the rookie year, from the RB, WR, and TE season-total "
    "models (under fantasy/projections/). They model opportunity (vacated backfield share, drafting-team "
    "context, ADP-implied role) and college/athletic/draft profile — so a rookie drafted into a crowded "
    "room can project lower than his draft slot alone would suggest. "
    "For the 2026 class this is the deploy projection; for 2024/2025 it is the walk-forward "
    "out-of-sample projection. Backtested 2021–2025 (pooled Spearman ~0.69–0.74 vs actual season "
    "totals), NOT live-validated. RB, WR, and TE rookies for now. TE is the thinnest of those (small "
    "rookie sample, zero-heavy scoring) — noisier, disclosed. The QB rookie arm was built but HELD (too "
    "thin — 7–13 QBs/year, and a rookie QB's season hinges on whether he starts, which the features can't "
    "see) — QB rookies show no projection; QB non-rookie projections exist only as a data export."
)
SLEEPER_HELP = (
    "Sleeper's published season-total half-PPR projection (the market), shown for context. The model "
    "does NOT claim to beat Sleeper — on 2021–2025 Sleeper ranks rookies/vets slightly better "
    "(Spearman +0.80 vs the model's +0.69). It is shown side-by-side by design, not as a scoreboard. "
    "Blank means Sleeper has not published a projection for that player."
)
DIFF_HELP = (
    "Projection − Sleeper (season-total half-PPR). Positive = the model is higher than the market on "
    "this player; negative = lower. Descriptive only — it is not a recommendation. Note: the models are "
    "known to be conservative at the very top (they compress the highest projections), so a large "
    "negative Diff on a top-projected player is the model's low-bias, not a read. Blank means one or "
    "both projections are unavailable."
)

_COLS = {
    "name": "Player", "position": "Pos", "team": "Team", "draft_round": "Rd", "draft_pick": "Pick",
    "hit_prob_draft": "Draft-Capital Hit-%", "hit_prob_college": "College Hit-%",
    "hit_prob_full": "Full Hit-%", "projection": "Proj (season ½-PPR)", "sleeper": "Sleeper Proj",
    "diff": "Diff vs Sleeper", "talent_score": "College Talent",
    "pct_speed_score": "Athleticism (Percentile)", "pct_cfb_final_dom": "Production (Percentile)",
}


@st.cache_data(ttl=3600)
def _load(cls: int) -> pd.DataFrame:
    f = _BOARD / f"rookie_board_{cls}.csv"
    return pd.read_csv(f) if f.exists() else pd.DataFrame()


@st.cache_data(ttl=3600)
def _load_proj() -> pd.DataFrame:
    """Season-total projection join files (norm_name, position, entry_class, projection, sleeper, diff).
    Concatenates the per-position files (RB + WR + TE); position is in the join key, so each row draws
    its position's model. Missing files are skipped (positions not built yet stay blank)."""
    frames = []
    for name in _PROJ_FILES:
        path = _PROJ_DIR / name
        if path.exists():
            frame = pd.read_csv(path)
            if not frame.empty:  # the intentionally held QB file is header-only
                frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["norm_name", "position", "entry_class", "projection", "sleeper", "diff"])
    return pd.concat(frames, ignore_index=True)


def _attach_projection(df: pd.DataFrame, cls: int) -> pd.DataFrame:
    """Left-join RB/WR/TE season-total projections; QB stays blank by design."""
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
    st.caption("A per-position hit-probability score for drafted rookies — plus season-total "
               "projections for RB/WR/TE, a college talent score, and college/athletic percentiles.")
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
            "Athleticism (Percentile)": st.column_config.NumberColumn(format="%.0f", help=PCT_HELP),
            "Production (Percentile)": st.column_config.NumberColumn(format="%.0f", help=PCT_HELP),
        },
    )
    model_available = int(show["Proj (season ½-PPR)"].notna().sum())
    sleeper_available = int(show["Sleeper Proj"].notna().sum())
    st.caption(
        f"Projection availability in this view — Model: {model_available}/{len(show)}; Sleeper: "
        f"{sleeper_available}/{len(show)}. A blank Sleeper Proj means Sleeper has not published one for "
        "that player; Diff stays blank unless both projections are available. Rookie QB model projections "
        "are intentionally withheld."
    )
    st.caption(
        f"Class of {cls} · {len(show)} rookies · {HIT_DEF} **Proj (season ½-PPR)** is the projected "
        "season-total half-PPR from the RB, WR, and TE season-total models — RB/WR/TE rookies (the QB "
        "rookie arm was held as too thin), shown beside Sleeper's projection with the difference; no claim "
        "to beat Sleeper. College "
        "Talent covers RB/WR/TE only (no QB) and the 2026 class only. Percentiles are within-position "
        "across the 2015–2026 drafted-skill panel. Hit "
        "probability and projection are backtested, not live-validated."
    )
