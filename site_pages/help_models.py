"""Help-page model rundowns. Streamlit render only. Data lives in model_explanations."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_BETTING = _ROOT / "betting"
if str(_BETTING) not in sys.path:
    sys.path.insert(0, str(_BETTING))

import model_explanations as me
from live_2026 import HIGH_GAP, LIVE_HIGH_ATS, LIVE_HIGH_N, LIVE_HIGH_WILSON_LOWER, LIVE_HIGH_WINS, live_high_bar_sentence

BREAKEVEN = 52.4
ACCENT = "#8abcf5"


def _bar(labels, values, *, y_title, text=None, colors=None, hline=None, hline_text=None,
         height=280):
    import plotly.graph_objects as go

    fig = go.Figure(go.Bar(
        x=list(labels),
        y=list(values),
        text=list(text) if text is not None else None,
        textposition="outside",
        marker_color=colors or ACCENT,
        hovertemplate="%{x}<br>%{y}<extra></extra>",
    ))
    if hline is not None:
        fig.add_hline(
            y=hline, line_dash="dash", line_color="#888",
            annotation_text=hline_text or "", annotation_position="right",
            annotation_font=dict(size=11, color="#9aa4b2"),
        )
    ymax = max(list(values) + ([hline] if hline is not None else [0]))
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font_color="white",
        yaxis=dict(
            title=y_title,
            gridcolor="#2d3748",
            range=[0, ymax * 1.18 if ymax else 1],
        ),
        xaxis=dict(gridcolor="#2d3748"),
        showlegend=False,
        height=height,
        margin=dict(t=24, b=20, r=112 if hline is not None else 24, l=8),
    )
    st.plotly_chart(fig, width="stretch")


def _cards(models):
    if not models:
        return
    for model in models:
        st.markdown(me.chart_html(model), unsafe_allow_html=True)


def render_rundowns():
    st.markdown(me.CHART_CSS, unsafe_allow_html=True)
    st.subheader("How the models work")
    st.caption(
        "Plain-language rundown for every number this site currently publishes. "
        "The bars show which inputs the model leans on, or how it scored on held-out seasons. "
        "They are not a promise that any one game or player will hit."
    )

    _spread_2026()
    _spread_2025_demo()
    _season_totals()
    _draft_board()
    _weekly_fantasy()
    _dfs_optimizer()
    _anytime_td()
    _totals_demo()
    _rookie_board()


def _spread_2026():
    with st.expander("How the 2026 spread model works"):
        st.markdown(f"""
Each week the model guesses the **margin leftover versus the first valid Tuesday market capture (09:00–15:30 ET)**.
It is a Ridge regression with **43 core features and 46 fitted inputs**. It removes
the five general injury-availability features and vacated snaps, while retaining
the four QB features. The three market features are Sunday 11:20 p.m. ET-to-Tuesday
spread movement, Sunday-to-Tuesday total movement, and the Tuesday moneyline–spread
gap; three missingness flags are fitted with the model. The Tuesday US median is
its frozen market input; the 2026 release shops the captured books and locks the
best quote for the selected side as its execution line. Other inputs describe
team form, quarterbacks, coaching, rest, and venue.

**Every game still gets a pick.** **HIGH** (green) is the only highlighted slice: the
model disagrees with the Tuesday US median by {HIGH_GAP:g} or more points, and the live line still
does. If the line moves and that gap falls under {HIGH_GAP:g}, HIGH is dropped. A later market
move alone cannot add HIGH, but an explicitly published model-version correction can change
predictions and HIGH labels at the same frozen line. There is no medium tier. The last regular-season week is skipped
for HIGH. Totals are not on the 2026 week page.

**The QB-retaining model's 2021-2025 walk-forward benchmark** uses median-triggered HIGH tickets scored at the best US Tuesday number:
**{LIVE_HIGH_WINS}/{LIVE_HIGH_N} = {LIVE_HIGH_ATS * 100:.2f}%**
ATS (7 pushes among 397 HIGH labels), one-sided 95% Wilson lower bound **{LIVE_HIGH_WILSON_LOWER * 100:.2f}%**, walk-forward
2021-2025. {live_high_bar_sentence()} Starting with 2026 releases, the model, pick,
edge, and HIGH flag use the Tuesday US median. The selected shopped quote is displayed
separately and used for grading, matching the benchmark's execution rule. Betting every
game is not the claim. Week 1 is now graded on the Track Record page; the live 2026
sample is still early and should not be read as a long-run performance claim.
This is Tuesday line value, not closing-line value.

The public spread release uses the first valid Tuesday market capture from 09:00–15:30 ET. Published matchups appear on Weekly Predictions as releases become available.
        """)
        rows = me.spread_high_season_rows()
        _bar(
            [r["season"] for r in rows],
            [r["pct"] for r in rows],
            y_title="HIGH ATS %",
            text=[r["record"] for r in rows],
            colors=["#00c853" if r["pct"] >= BREAKEVEN else "#ff5252" for r in rows],
            hline=BREAKEVEN,
            hline_text="Break even (52.4%)",
        )
        st.caption(
            "HIGH cover rate by season on the 2021-2025 as-of walk-forward book, "
            "scored at the best US Tuesday number. "
            "This does not prove 2026 will look like any one of those years."
        )


def _spread_2025_demo():
    with st.expander("How the 2025 demo spread worked"):
        st.markdown("""
Weeks 10 through the end of 2025 on this site are a **frozen walkthrough** of the old
three-model consensus, not the 2026 Tuesday model.

The old system blended 75% XGBoost with 25% Ridge for the predicted margin, then let
XGBoost, Ridge, and LightGBM vote on the side. HIGH meant all three agreed and the
edge was 3 or more points. MEDIUM meant they agreed with a 1-point edge. PASS meant
they disagreed or the edge was tiny.

Those weeks still show HIGH / MED / PASS badges and a Min Edge slider. They will not
be restated as the live book.
        """)
        card = me.card_by_id("spread_xgb")
        if card:
            st.caption("What the old XGBoost piece leaned on (mean absolute Tree SHAP, 2014-2024 training games).")
            _cards([card])
            st.caption(
                "The Tuesday line is the largest bar. That is expected. The model is scoring "
                "leftover versus a line that already prices most of the game. These shares "
                "are not a ranking of accuracy."
            )


def _season_totals():
    with st.expander("How Season Totals are built"):
        st.markdown("""
Every team gets a **projected regular-season win total** (ties count as half a win).
The 32 projections always sum to 272 scheduled games.

The model is a linear fit on last year's passing and special-teams efficiency, leftover
opportunity, quarterback status, coaching change, rest, schedule, and **the posted win
total itself**. 2026 numbers are then recentered so the league still sums to 272.

**HIGH** (the check mark) fires when the projection is at least 1 full win off the
posted number. Every other team still shows a projection. HIGH is the only certified
pick on that page.

The all-team sheet does **not** beat the posted win total on average (held-out MAE
2.26 wins versus 2.21 for the posted number). HIGH's one-sided 95% Wilson lower bound
sits under the 52.4% bar. Backtested, not live-validated. 2026 reserve counts are
withheld because camp rosters do not match post-cutdown history.
        """)
        ladder = [
            ("Repeat last year", 2.7955),
            ("Retired Monte Carlo", 2.3650),
            ("This model", 2.2578),
            ("Posted win total", 2.2088),
        ]
        _bar(
            [name for name, _ in ladder],
            [val for _, val in ladder],
            y_title="Average miss (wins)",
            text=[f"{val:.2f}" for _, val in ladder],
            colors=["#8abcf5", "#8abcf5", "#d3ad63", "#00c853"],
        )
        st.caption(
            "Average miss per team on 352 held-out team-seasons (2015-2025). Lower is "
            "better. The posted number is still the tightest sheet. This chart is the "
            "all-teams projection, not the HIGH slice."
        )
        imp = me.season_totals_importance()
        _cards([{
            "label": "Season Totals · what the fit leans on",
            "method": "absolute ridge coefficient share",
            "n": 384,
            "features": imp,
        }])
        st.caption(
            "The posted win total is the largest term. The other bars are the nudges: "
            "true home games, a missing starter QB, and last year's efficiency. Signs "
            "matter on the page (unavailable QB pulls the projection down). This is not "
            "a causal ranking."
        )


def _draft_board():
    ev = me.DRAFT_BOARD_EVAL
    with st.expander("How Model Proj is built"):
        st.markdown(f"""
**Model Proj** is the published season-total half-PPR number for the 180-player board
(24 QB, 60 RB, 72 WR, 24 TE). It is a machine-learning forecast from last year's
production, draft capital, age, and leftover opportunity on the new roster. **ADP and
the two Talent Scores are not inputs.** **Model Draft Rank** is that same Model Proj
turned into an overall snake-draft order by subtracting a replacement starter at each
position (QB14, RB30, WR36, TE14). It is a Draft price toggle: the draft-price column
shows that overall rank (1.0 = first). Not a separate forecast.

Points and positional ranks stay frozen until the dated early-September public-information
snapshot. Sleeper ADP (the default), ESPN ADP, and Yahoo ADP still refresh daily, as does Sleeper Proj;
those live values rewrite the market ranks and both gap columns, not Model Proj. The 5-of-6
ADP-ordering result is vs Sleeper ADP.

**How it scored historically.** On 2021-2025 Model Proj pairwise **{ev['model_pairwise']:.4f}**
versus ADP **{ev['adp_pairwise']:.4f}**, MAE **{ev['model_mae']:.2f}** versus **{ev['adp_mae']:.2f}**,
and beat ADP ordering in {ev['seasons_beat_adp']} seasons (it lost {ev['lost_season']}).
It is **not live-validated**. The first live test is the 2026 season.
        """)
        _bar(
            ["Model Proj", "ADP"],
            [ev["model_mae"], ev["adp_mae"]],
            y_title="Average miss (half-PPR points)",
            text=[f"{ev['model_mae']:.1f}", f"{ev['adp_mae']:.1f}"],
            colors=[ACCENT, "#888888"],
        )
        st.caption(
            "Average miss versus actual season-total half-PPR on the 180-player universe, "
            "2021-2025. Lower is better. Pairwise ordering (how often the higher-ranked "
            "player scored more) is the other score on the Draft Board page. This does "
            "not prove any one 2026 row is right."
        )


def _weekly_fantasy():
    with st.expander("How weekly fantasy projections are built"):
        st.markdown("""
**The current 2026 release is live.** Each published release covers the scheduled
QB, RB, WR, and TE universe in the captured Sleeper projection payload with a
numeric half-PPR benchmark. The independent model supplies the score; Sleeper's
projection is not an input.

**What you can read today** is the **2025 demo** (weeks 10-17). Those files came from
four per-position XGBoost models trained on 2020-2024, with 2025 held out. Scoring is
half-PPR: 0.5 per reception, yards and touchdowns as usual. Demo weeks also carry extra
stat columns (pass/rush/rec yards, receptions) from eight smaller models. Those extras
will not appear on a 2026 live week unless that file has them.

**2026 live model.** One LightGBM across QB, RB, WR,
and TE. It predicts this week's half-PPR points. Form is the last four played games,
most recent weighted 40/25/20/15. Early in the year it blends prior-season games.
Missed games are skipped, not zeroed. Early-season releases use history through the
prior season, the current roster and depth chart, reviewed venue context, and the
captured Tuesday market. Missing
rookie history stays missing rather than becoming zero. Sleeper's weekly projection is
the benchmark and universe definition, not an input.

Releases are immutable revisions. The first build precedes the first kickoff; later
builds copy every started game's rows exactly and recompute only games that have not begun.

On the 2025 holdout (train 2021-2024, n=3,060 Sleeper-covered top-180 player-weeks):
MAE **4.999** vs Sleeper **5.188**. Rank correlation **0.395** vs Sleeper **0.402**.
Walk-forward rank 2023-2025: **0.394**. Point error is a bit better. Ordering is a
bit worse. That is not a claim it beats Sleeper.
        """)
        points = me.weekly_point_cards()
        if points:
            st.caption("2025 demo: which inputs the four fantasy-point models leaned on (XGBoost gain).")
            _cards(points)
            st.caption(
                "Recent snaps and recent fantasy points dominate every position. That is "
                "the honest story: last week's role is most of next week's projection. "
                "Top five bars do not sum to 100%."
            )


def _dfs_optimizer():
    with st.expander("How the DFS optimizer works"):
        st.markdown("""
The public page builds a DraftKings NFL Classic lineup from **direct DK-point**
projections. It is not the half-PPR Weekly Fantasy model, and it does not convert
those rankings into DK points.

You supply the salary file for the contest. The projection file is either a checked
producer artifact or an upload with the same contract: direct DK points plus a sidecar
that names the product, scoring, season, week, and file hash. The solver is a reviewed
vendored integer program: $50,000 cap, standard Classic slots, one FLEX from RB/WR/TE.

DST is not a trained player model. It uses opponent implied total mapped to
Classic points-allowed buckets plus a locked league-mean bonus. No line: DraftKings
average, labeled on the page. Injured and unmatched skill players are dropped.
Questionable stays in.

No projection-edge claim. A current direct-DK artifact may be published; a real
lineup still requires the DraftKings salary CSV for the contest.
        """)
        st.caption(
            "This page does not prove a Classic lineup will beat the field. It is a "
            "constrained optimizer on this model's DK-point estimates."
        )


def _anytime_td():
    with st.expander("How Touchdown Props works"):
        st.markdown("""
**Status: current live release plus historical demo. For fun. Do not bet this.**

The live board is built from manually pasted US-book Yes prices. The page
defaults to the current published 2026 release and keeps the historical demo
selectable for context. New live slates are appended as Joseph supplies them; started-game rows are
frozen, and no odds API is used.

Use the **Market** control to switch between three touchdown-scorer markets.
Only one renders at a time.

**Anytime TD.** The chance a skill player scores a **rushing or receiving**
touchdown in that game. Passing touchdowns are out. The model is a Poisson
rate on 34 locked usage features plus that week's Sleeper half-PPR
projection. It does not use the anytime price as an input.

On the full 2025 overlap (n=5,310) the book still wins: Brier **0.13985** vs our
**0.13996**. Sleeper's dump has no freeze timestamp. The last regular week is skipped
because those box scores are rest and backups.

The page is a **priced comparison board**: every skill player the books quoted
that week, with Model ATTD Odds beside Book ATTD Odds, sorted by ATTD Value Gap
(our probability minus the book probability, highest first). This is not even money.
About one in five hits. It is not a pick list. A cut of the biggest
disagreements lost on 2025. Full 2025: the books were about 0.08% more accurate.
Demo weeks 10-17: closer in 5 of 8 weeks. That is not a betting record.

**2+ TD.** Not backtested: no historical 2+ model-quality or betting
test results are published yet. Its probabilities and cards are forward-looking
paper tracking only, not evidence of accuracy or profitability. Since
2026-09-19 its candidate rule is model probability at least 1.25x DraftKings'
price, with that price at least 2% (replaces a flat +0.5pp gap, which mostly
flagged long shots where a small model error reads as a huge relative edge).

**First TD.** A different kind of probability than the other two: exactly one
player can score a game's first touchdown, so it is a competing-risk
allocation across both rosters (each player's share of the game's
Anytime-TD rate), not a per-player marginal chance. There is no historical
First TD backtest of any kind, for any season, anywhere in this project --
only a forward live-week board. Treat it as entertainment even more than 2+ TD.
Its paper-bet rule is a wider +3.0pp gap than Anytime's +1.0pp, because the
allocation method has a known bias toward underweighting bell-cow backs and
starting QBs that a narrow gap rule would misread as value. Since 2026-09-19
it also requires a positive expected return at DraftKings' actual, vigged
price, since the de-vigged gap alone can still pass on a bet that loses
money once the real price (which sums to about 121% per game) is paid.
        """)
        st.caption(
            "The live board is a comparison, not a claim it beats the book. "
            "Pregame outcomes remain blank until grading is attached."
        )


def _totals_demo():
    with st.expander("How the Over/Under model works (2025 demo, experimental)"):
        st.markdown("""
**Status: experimental. Tracking only. Do not bet these.** 2026 Weekly Predictions
does not show totals.

The 2025 demo runs a second pair of models (XGBoost and Ridge) on whether the combined
score lands under the Vegas total. A card only flags **UNDER** when both models agree.
There are no OVER bets. Recreational money shades totals high, which is the only reason
an UNDER-only rule was worth testing.

Walk-forward CV (2020-2025, n=575) hit **55.7%**. Live 2025 weeks 10-17 (n=46) hit
**52.2%**, which is break-even inside a wide interval. The amber dashed badge is there
on purpose.
        """)
        cards = [c for c in (me.card_by_id("totals_xgboost"), me.card_by_id("totals_ridge")) if c]
        _cards(cards)
        st.caption(
            "XGBoost uses gain. Ridge uses absolute standardized coefficients. Do not "
            "read either as proof the live 2025 sample has an edge."
        )


def _rookie_board():
    auc = me.ROOKIE_HIT_AUC
    with st.expander("How the Rookie Board numbers are built"):
        st.markdown(f"""
Two different numbers sit on the Rookie Board.

**Hit %** is the share of historical players with a similar profile who had at least
one startable season in their first three years (top-24 RB/WR, top-12 QB/TE, season-total
half-PPR). Three columns: draft capital only, college production and testing only, and
both. They land close together. On the {auc['holdout']} hold-out, full-model AUC was
**{auc['full']}** versus **{auc['draft_only']}** from draft slot alone. College added no
measured edge beyond where he was picked. Backtested, not live-validated. First live
test: end of 2026.

**Season-total projections** (RB, WR, TE) come from the rookie arms of the older
season-total models. They see draft slot, age, vacated opportunity, and college
production. Rookie QBs have no projection: a rookie QB season hinges on whether he
starts, which those features cannot see.
        """)
        _bar(
            ["Draft slot only", "Full model"],
            [auc["draft_only"], auc["full"]],
            y_title="Hit-probability AUC",
            text=[f"{auc['draft_only']:.3f}", f"{auc['full']:.3f}"],
            colors=["#888888", ACCENT],
            height=260,
        )
        st.caption(
            "AUC on the 2019-2023 hold-out classes. 0.50 is a coin flip. The two bars "
            "are almost the same height: draft capital is doing the work. This does not "
            "say college production is meaningless. It says it is already priced into "
            "draft slot at this sample."
        )
        rook = me.rookie_projection_cards()
        if rook:
            st.caption("Rookie season-total projections: top inputs (mean absolute Tree SHAP).")
            _cards(rook)
