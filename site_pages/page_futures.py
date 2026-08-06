"""Season Win Totals page. The futures/ subproject's only public surface.

READ-ONLY over two pre-built artifacts. No model, no simulator, no training dependency runs
here: the page reads `futures/futures_predictions.csv` with pandas and the evidence block from
`futures/artifacts/model_metadata.json` with stdlib json. That is PREREGISTRATION §8's runtime
separation: LightGBM, scipy and any solver stay out of the deployed runtime.

WHAT THIS PAGE MAY AND MAY NOT SAY
----------------------------------
`futures/PREREGISTRATION.md` §7 gate A passed (the projection is usable) and **gate B failed for
every model tested**. None is closer to the realized win count than the archived market consensus.
Gate C is permanently shut (`tier_c_open: false`), because the archive carries no named book. So
this page shows projected wins and the win distribution, states the gate B result plainly, and
carries the claim licence. It shows no side, no probability against a posted line, and no
confidence tier, and it carries none of the fenced vocabulary. `tests/test_page_futures.py`
enforces that mechanically against `futures/season_team_totals/tier_lock.py`'s own word list.

The benchmark is named an **archived market consensus of unattributed sportsbook origin**, never
"the sportsbook line", "Vegas", or "the market". That naming rule is `model_metadata.json`'s
`claim_licence.naming`.

The label under `claim_licence.required_label` is read from the artifact rather than typed here, so
the sentence on the page is the one notebook 04 recorded and cannot drift from it.
"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

_HERE = Path(__file__).resolve().parents[1]
_CSV = _HERE / "futures" / "futures_predictions.csv"
_META = _HERE / "futures" / "artifacts" / "model_metadata.json"
_COMPARISON = _HERE / "futures" / "artifacts" / "model_comparison.json"
_EVIDENCE = _HERE / "futures" / "artifacts" / "season_totals_evidence.json"

# NOTE: the site-wide ORIENTATION line ("...models for NFL betting and fantasy...") is
# deliberately NOT used on this page. §7's fence forbids that vocabulary here while gate C is
# shut, and the fence outranks shared copy. Only the flagship Draft Board carries orientation
# anyway; Rookie Board does not either. `tests/test_page_futures.py` would fail if it returned.
ORIENTATION = ("Model-built NFL projections, run in the open: the numbers, the honest "
               "backtest, and the code on my GitHub.")
PURPOSE = ("My pre-season projection of how many games each team wins, with the full range of "
           "outcomes the model considers plausible, not just a single number.")

# Shown verbatim. The backtest result is the headline, not a footnote.
HONEST_HEADLINE = (
    "**This model does not beat the archived market consensus.** Over a ten-season backtest it "
    "landed slightly further from each team's actual win count than an archived market consensus "
    "of unattributed sportsbook origin did. It is published because it is a sound projection with "
    "an honest range, not because it is sharper than the number the books opened."
)

PROJ_HELP = (
    "Projected regular-season wins, averaged over 20,000 simulated seasons. Ties count as half a "
    "win. The 32 projections always sum to 272, the number of games on the schedule, so no team "
    "can be raised without another coming down."
)
MEDIAN_HELP = (
    "The middle outcome: in half the simulated seasons this team won this many games or fewer."
)
RANGE_HELP = (
    "The width of the 10th-to-90th percentile interval, in wins. A wider number means the schedule "
    "and the team profile leave more room for the season to go either way."
)
P_HELP = (
    "Percentiles of the simulated win count. 10 percent of simulated seasons finished at or below "
    "p10, and 10 percent at or above p90, so the p10-to-p90 span covers the middle 80 percent of "
    "outcomes. These intervals were calibrated against ten seasons of held-out results."
)
METHOD = """
**How the number is produced.** Each team gets a season profile built only from information that
exists before Week 1: last season's record, point differential and efficiency, three-year form,
coaching change, and the shape of the 2026 schedule (opponents, rest, byes, and which games are
played at a neutral or international venue). A ridge model turns the difference between two teams'
profiles into an expected scoring margin for a single game, home field is added only where the game
actually has a home team, and then the whole 272-game season is simulated 20,000 times. The
projection is the average win count across those simulations; the percentiles are their spread.

**Why the range is so wide.** The 10-to-90 span runs about seven wins. That is not vagueness for
its own sake. It is what the backtest says honest uncertainty looks like at this level of
information. An earlier version of the model produced tighter intervals that were wrong: its
nominal 80 percent interval contained the real answer only 65 percent of the time. A
pre-registered correction widened it, and the corrected version now covers 75 percent, inside the
72-to-88 percent band that was written down before the correction was fitted.

**What it does not know.** Nothing about the current roster: no quarterback situation, no trades or
signings after last season, no injuries, no training-camp news. Those were deliberately left to a
declared second version with its own pre-registration, so that this one could not be quietly tuned
until it looked good.

**Honesty about the benchmark itself.** The comparison number is a free public archive of preseason
win totals with no named sportsbook attached and only day-level timestamps. That is why it is
called an archived market consensus of unattributed sportsbook origin rather than a book's line,
and it is the reason the strongest class of claim about this model was ruled out before any model
was fitted.
"""


def _render_evidence():
    """The honest scorecard: how accurate, and the disconfirming directional result.

    Authorised by PREREGISTRATION Amendment 5, which licenses publishing a result showing the
    projection FAILS to beat the posted numbers and licenses nothing else. Every number is read
    from the artifact; none is retyped here. The wording carries no fenced vocabulary, which
    `tests/test_page_futures.py` checks against tier_lock's own word list.
    """
    ev = _read_json(str(_EVIDENCE))
    if not ev:
        return
    acc, dr = ev.get("accuracy", {}), ev.get("direction", {})

    st.subheader("How good is this, honestly")

    if acc.get("ladder"):
        st.markdown(
            "**On accuracy.** Average miss per team over ten held-out seasons, in wins. "
            "Lower is better."
        )
        ladder = pd.DataFrame(acc["ladder"]).rename(
            columns={"name": "Approach", "mae": "Average miss (wins)"})
        st.dataframe(ladder, hide_index=True, width="stretch",
                     column_config={"Average miss (wins)":
                                    st.column_config.NumberColumn(format="%.2f")})
        st.caption(
            f"Repeating last season's record is worse than assuming nothing. Measured against "
            f"that flat 8.5-win assumption, this model closes about "
            f"**{acc['model_share_of_available_improvement']:.0%}** of the distance the archived "
            f"market consensus closes, and remains {acc['gap_to_consensus']:.2f} wins further from "
            "the truth than the consensus is."
        )

    if dr.get("n_graded"):
        st.markdown(
            "**On direction, the question everyone actually asks.** For each team the projection "
            "was compared with the posted season number and recorded as higher or lower. Then the "
            "real result settled it."
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("Landed correctly", f"{dr['correct_rate']:.1%}",
                  help=f"{dr['n_graded']} team-seasons where the projection differed from the "
                       f"posted number. {dr['n_excluded_exact']} exact matches were excluded "
                       "because there is nothing to settle.")
        c2.metric("Needed to break even", f"{dr['break_even_rate']:.1%}",
                  help="The rate the posted numbers themselves imply is required simply to come "
                       "out level, before anything is gained. It sits above 50% because neither direction "
                       "is ever quoted at even money.")
        c3.metric("Return per unit", f"{dr['return_per_unit']:+.1%}",
                  help="What a flat, unweighted unit on every one of these comparisons would have "
                       "returned across the ten seasons.")
        lo, hi = dr["ci95_shortfall"]
        # st.warning, NOT st.error. An error banner reads as "the page broke" rather than "the
        # finding is negative", and `tests/test_page_futures.py` treats any error element as a
        # render failure. Keeping that check strict is worth more than the redder box.
        st.warning(
            f"**{dr['verdict'].title()}.** The projection landed correctly "
            f"{dr['correct_rate']:.2%} of the time against the {dr['break_even_rate']:.2%} needed "
            f"to break even, a shortfall of {abs(dr['shortfall']) * 100:.2f} points "
            f"(95% interval {lo * 100:+.2f} to {hi * 100:+.2f}). It cleared break-even in "
            f"{dr['seasons_above_break_even']} of {dr['seasons_total']} seasons. "
            "This is published because it is the honest answer, not because it is a useful one."
        )
        pn = dr.get("power_note", {})
        if pn:
            st.caption(
                f"**Read the interval carefully.** It spans zero, so the shortfall is not "
                f"statistically established either. That is a sample-size problem, not a hidden "
                f"positive: with 32 teams a season this comparison needs roughly "
                f"{pn['n_needed_for_two_point_claim']:,} settled team-seasons, about "
                f"{pn['seasons_needed']} seasons, to establish a two-point difference in either "
                f"direction. The current interval is {pn['ci_halfwidth_points']:.1f} points wide "
                "in each direction. Absence of a demonstrated difference is not a demonstrated absence."
            )


def _rg_color(ratio: float) -> str:
    """Site-wide red-to-green semantic ramp (matches Weekly Fantasy and the Draft Board).

    Encodes magnitude only. A greener cell means a higher projected win count, nothing more.
    """
    ratio = max(0.0, min(1.0, float(ratio)))
    r = int(round(255 * (1 - ratio)))
    g = int(round(82 + 118 * ratio))
    return f"rgb({r},{g},82)"


@st.cache_data(ttl=3600)
def _load() -> pd.DataFrame:
    return pd.read_csv(_CSV) if _CSV.exists() else pd.DataFrame()


@st.cache_data(ttl=3600)
def _read_json(path_str: str) -> dict:
    p = Path(path_str)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}


def _load_meta() -> dict:
    """Evidence block. Absent metadata degrades to the label the CSV already carries."""
    return _read_json(str(_META))


def _benchmark_mae():
    """The archived consensus's own backtest error, read from notebook 02's artifact.

    Never typed as copy: a benchmark number that drifts from the artifact would quietly
    misstate the one comparison this page exists to report honestly. Absent artifact ->
    None, and the comparison clause is omitted rather than guessed.
    """
    comp = _read_json(str(_COMPARISON))
    try:
        return float(comp["pooled_mae"]["headline"]["B0_market"])
    except (KeyError, TypeError, ValueError):
        return None


def _style(view: pd.DataFrame):
    """Colour the projection column by magnitude, on the shared ramp."""
    wins = pd.to_numeric(view["Proj Wins"], errors="coerce")
    lo, hi = float(wins.min()), float(wins.max())
    span = hi - lo

    def _apply(df: pd.DataFrame) -> pd.DataFrame:
        styles = pd.DataFrame("", index=df.index, columns=df.columns)
        if "Proj Wins" in df.columns and span > 0:
            col = df.columns.get_loc("Proj Wins")
            for row, w in enumerate(wins.to_numpy()):
                if not pd.isna(w):
                    styles.iat[row, col] = (f"color: {_rg_color((w - lo) / span)}; "
                                            f"font-weight: 700; font-size: 15px")
        return styles

    return _apply


def render():
    st.title("📊 Season Win Totals")
    st.caption(ORIENTATION)
    st.markdown(f"**{PURPOSE}**")

    df = _load()
    if df.empty:
        st.info("Season win-total projections are not built yet. Run "
                "`futures/season_team_totals/05_predict_futures.ipynb`.")
        return

    meta = _load_meta()
    season = int(df["season"].iloc[0])
    label = str(df["claim_label"].iloc[0])

    st.warning(HONEST_HEADLINE)

    view = pd.DataFrame({
        "Team": df["team"],
        "Proj Wins": pd.to_numeric(df["proj_wins"], errors="coerce"),
        "p10": pd.to_numeric(df["p10"], errors="coerce"),
        "p25": pd.to_numeric(df["p25"], errors="coerce"),
        "Median": pd.to_numeric(df["p50"], errors="coerce"),
        "p75": pd.to_numeric(df["p75"], errors="coerce"),
        "p90": pd.to_numeric(df["p90"], errors="coerce"),
    })
    view["80% Range"] = view["p90"] - view["p10"]
    view = view.sort_values("Proj Wins", ascending=False).reset_index(drop=True)
    view.insert(0, "#", range(1, len(view) + 1))

    st.dataframe(
        view.style.apply(_style(view), axis=None),
        hide_index=True, width="stretch", height=min(720, 60 + 35 * len(view)),
        column_config={
            "#": st.column_config.NumberColumn(
                # 50px is the grid minimum; pinned so it keeps that exact width instead of
                # absorbing an even share of the table's leftover space (grow=0 when pinned).
                format="%d", width=50, pinned=True,
                help="Row number in this table as currently sorted. A counter to keep your "
                     "place, not a ranking."),
            "Proj Wins": st.column_config.NumberColumn(format="%.2f", help=PROJ_HELP),
            "p10": st.column_config.NumberColumn(format="%.1f", help=P_HELP),
            "p25": st.column_config.NumberColumn(format="%.1f", help=P_HELP),
            "Median": st.column_config.NumberColumn(format="%.1f", help=MEDIAN_HELP),
            "p75": st.column_config.NumberColumn(format="%.1f", help=P_HELP),
            "p90": st.column_config.NumberColumn(format="%.1f", help=P_HELP),
            "80% Range": st.column_config.NumberColumn(format="%.1f", help=RANGE_HELP),
        },
    )

    st.caption(
        f"{season} regular season · {len(view)} teams · projections sum to "
        f"{view['Proj Wins'].sum():.0f} wins, the exact number of games scheduled · the 10-to-90 "
        f"interval averages {view['80% Range'].mean():.1f} wins. Colour on the projection column "
        "encodes magnitude only."
    )

    # The evidence block. Numbers come from the artifact, never from copy typed here.
    ev = meta.get("evidence", {})
    if ev:
        mae = ev.get("pooled_mae_headline")
        cov = ev.get("coverage80")
        band = ev.get("coverage80_band") or []
        c1, c2, c3 = st.columns(3)
        if mae is not None:
            bench = _benchmark_mae()
            c1.metric("Average miss, backtest", f"{mae:.2f} wins",
                      help="Mean absolute error across ten held-out seasons (320 team-seasons). "
                           + (f"The archived market consensus scored {bench:.2f} over the same "
                              f"rows, a gap of {mae - bench:+.2f} wins. " if bench is not None
                              else "The archived market consensus scored lower over the same "
                                   "rows. ")
                           + "That is why this model is published as a projection and nothing "
                             "stronger.")
        if cov is not None:
            c2.metric("Interval accuracy", f"{cov * 100:.0f}%",
                      help=("Share of held-out seasons whose actual win count fell inside the "
                            "80 percent interval. The acceptable band "
                            + (f"({band[0]:.0%} to {band[1]:.0%}) " if len(band) == 2 else "")
                            + "was written down before this was measured."))
        c3.metric("Beats the archived consensus?",
                  "No" if ev.get("gate_B_passed") is False else "See notes",
                  help="A pre-registered test, fired once, on a frozen set of seasons chosen "
                       "before any model was fitted.")

    _render_evidence()

    with st.expander("How this is built, and what it does not know"):
        st.markdown(METHOD)

    stamp = str(df["generated_at"].iloc[0])[:19].replace("T", " ")
    st.caption(
        f"**{label}** · model {df['model_family'].iloc[0]} · artifact "
        f"`{str(df['model_sha256'].iloc[0])[:12]}` · audit `{df['audit_verdict'].iloc[0]}` · "
        f"generated {stamp} UTC. Built from a frozen pre-registration in `futures/`; the "
        "acceptance thresholds and the held-out seasons were fixed before any model was fitted, "
        "and each test fired exactly once."
    )
