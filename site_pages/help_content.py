"""Searchable Help & Guide content.

The page renderer owns navigation, search, and topic state. This module owns the
FAQ registry and the small render callbacks behind each answer so the guide can
be edited without turning ``page_help.py`` into another monolithic page.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import streamlit as st

import dashboard_data
import help_models
import nav_registry
import page_common
from dashboard_utils import breakeven_verdict
from live_2026 import (
    HIGH_GAP,
    LIVE_HIGH_ATS,
    LIVE_HIGH_N,
    LIVE_HIGH_WILSON_LOWER,
    LIVE_HIGH_WINS,
    live_high_bar_sentence,
)
from video_content import LATEST_LEAGUE_HISTORY_VIDEO_SLUG


TOPICS = ("Site Guide", "Football", "Fantasy", "Betting", "Models & Data")


@dataclass(frozen=True)
class FAQItem:
    topic: str
    question: str
    keywords: tuple[str, ...]
    render: Callable[[], None]

    def matches(self, query: str) -> bool:
        haystack = " ".join((self.topic, self.question, *self.keywords)).lower()
        return query.lower().strip() in haystack


def _page_link(slug: str, label: str, icon: str = ":material/arrow_outward:", **kwargs) -> None:
    page = nav_registry.PAGES.get(slug)
    if page is not None:
        st.page_link(page, label=label, icon=icon, width="stretch", **kwargs)
    else:
        st.markdown(f"**{label}**")


def _active_build(product: str) -> dict | None:
    try:
        manifest = page_common.load_release_manifest()
        state = manifest.get("products", {}).get(product, {})
        active = state.get("active_build")
        build = state.get("builds", {}).get(active)
        return build if isinstance(build, dict) else None
    except Exception:
        return None


def _release_line(product: str, label: str) -> str:
    build = _active_build(product)
    if build is None:
        return f"**{label}:** the current published release is unavailable in this session."
    season, week = build.get("season"), build.get("week")
    if season is not None and week is not None:
        return f"**{label}:** the current published release is {season} Week {week}."
    return f"**{label}:** a current published release is available."


def _demo_stats() -> dict | None:
    """Load the small dynamic block only when the Betting answer needs it."""
    try:
        df = dashboard_data.load_predictions()
        if df is None or df.empty:
            return None
        demo = df[df["season"] == 2025] if "season" in df.columns else df
        return dashboard_data.accuracy_stats(demo if not demo.empty else df)
    except Exception:
        return None


def _render_what_is_jsa() -> None:
    st.markdown(
        """
JoScho Analytics is a public NFL data-science project. It publishes football
predictions, fantasy projections, league-history tools, and the evidence and
limitations behind them.

The site is a research and education tool. A projection is not a guarantee, a
ranking is not a command to draft a player, and a betting page is not financial
advice.
        """
    )


def _render_page_directory() -> None:
    st.markdown(
        """
Use the page that matches the question you are asking. Betting, fantasy, and
season-total products are separate systems; their numbers should not be mixed.
        """
    )
    pages = (
        ("this-week", "This Week", "A compact hub for the current spread, fantasy, and anytime-TD releases."),
        ("weekly-predictions", "Weekly Predictions", "NFL matchup margins, Tuesday HIGH qualification, and graded picks."),
        ("track-record", "Track Record", "Graded ATS results and the historical record by season and confidence tier."),
        ("season-totals", "Season Totals", "Team win projections compared with posted regular-season totals."),
        ("weekly-fantasy", "Weekly Fantasy", "Current-week half-PPR player projections and supporting stats."),
        ("dfs-optimizer", "DFS Optimizer", "DraftKings Classic lineup construction from checked direct-DK projections."),
        ("draft-board", "Draft Board", "Preseason season-total projections beside current Sleeper, ESPN, and Yahoo ADP sources."),
        ("rookie-board", "Rookie Board", "Rookie hit probabilities and season-total projection context."),
        ("anytime-tds", "Anytime TDs", "Rushing and receiving touchdown probabilities beside book prices."),
        ("film-room", "Film Room", "Short analysis videos, walkthroughs, and written context."),
        ("league-history", "League History", "Sleeper, ESPN, Yahoo, and CBS league imports and history views."),
    )
    for slug, label, description in pages:
        _page_link(slug, f"{label} — {description}")
    st.caption(
        "Yahoo does not price every one of the 180 players on Draft Board; those "
        "cells remain blank rather than being filled from another source."
    )


def _render_states() -> None:
    st.markdown(
        """
**Live** means the page is using the current season's published release or
tracking artifact. **Demo** means an older season is retained for explanation
and historical context. **Experimental** means the page is tracking an idea
without a validated edge claim. **Seasonal** means a product is most useful in
one part of the NFL calendar, such as the Draft Board before drafts.

Every product page carries its own freshness note. Read that note before using
a number, especially when a page combines current and historical material.
        """
    )
    st.markdown(_release_line("predictions", "Weekly Predictions"))
    st.markdown(_release_line("fantasy", "Weekly Fantasy"))


def _render_updates_and_locks() -> None:
    st.markdown(
        """
Weekly Predictions uses the first valid Tuesday market capture in its stated
window. The Tuesday US median drives the 2026 model input, pick, displayed edge,
and HIGH qualification; the separately displayed best captured quote is used for
execution and grading.

Weekly Fantasy releases are immutable revisions. Once a game starts, its rows
are copied unchanged in later releases while future games may be recomputed.
Season-total and draft products have their own refresh notes because their
published projections and market inputs move on different schedules.
        """
    )


def _render_filters_and_urls() -> None:
    st.markdown(
        """
Season and Week controls belong to the page that owns the data. Weekly
Predictions and Weekly Fantasy write their selected season and week into the URL,
so a filtered view can be shared. The 2025 demo prediction page also has a Min
Edge filter; the live 2026 page shows every game and highlights HIGH separately.

If a shared URL points to a release that is no longer available, the page falls
back to its current valid selection rather than inventing a result.

The site opens on **Home** every time. There is no sidebar; the top navigation
holds the product pages.
        """
    )


def _render_league_history() -> None:
    st.markdown(
        """
Choose Sleeper, ESPN, Yahoo, or CBS, enter the league ID, and load the history.
Sleeper IDs come from `sleeper.com/leagues/{ID}/league`; ESPN also needs the
season in the league URL. Yahoo IDs are the number after `/f1/` and also need
the season. CBS IDs are the subdomain of `{ID}.football.cbssports.com` and also
need that season.

Private ESPN leagues need the SWID and espn_s2 cookie values. Private Yahoo
leagues need the Y and T cookie values. CBS leagues always need the signed-in access
token. Treat all of these like passwords: retrieve them on a signed-in desktop
browser, never paste them into chat, and do not share them with the site owner.
They stay in the current browser session and are not logged or shared-cached.

Public results are cached for an hour. A brand-new league can load with empty
tabs until it has a draft or scored weeks. This page describes your league's
history; it is not a prediction model. The Film Room walkthrough shows Sleeper
and ESPN; Yahoo and CBS are on the live page and are not in that video.
        """
    )
    _page_link(
        "film-room",
        "Watch the League History walkthrough",
        icon=":material/play_circle:",
        query_params={"video": LATEST_LEAGUE_HISTORY_VIDEO_SLUG},
    )


def _render_film_room() -> None:
    st.markdown(
        """
Film Room contains short analysis videos, the site walkthrough, and the League
History walkthrough. Choose a section and episode, then open the written
breakdown when you want the assumptions and evidence behind the short.
        """
    )


def _render_scoring() -> None:
    st.markdown(
        """
An NFL game is a sequence of possessions. Teams trade opportunities to score,
and the final score is the sum of touchdowns, field goals, extra points, and
safeties. A model usually predicts a margin or a player total rather than the
exact final score, because many different game paths can produce the same
result.

**Game script** is the shape of those paths: a team playing from ahead may run
more and throw less, while a team chasing points may create more passing volume.
That is why matchup, venue, injuries, quarterback status, and rest can change a
projection without changing a player's underlying skill.
        """
    )


def _render_epa() -> None:
    st.markdown(
        """
EPA means **Expected Points Added**. It estimates how much a play changes a
team's expected scoring position after accounting for down, distance, field
position, and game state. A positive offensive EPA play helped the offense; a
negative one hurt it.

The site uses recent offensive efficiency as context, not as a guarantee. EPA
is one input among many and is not a causal explanation for every player or
team result.
        """
    )


def _render_injuries_context() -> None:
    st.markdown(
        """
Availability changes opportunity before it changes talent. A missing starting
quarterback can affect both a team's expected scoring and its pass catchers;
an injured running back can redistribute carries and receptions. Rest and venue
change the environment in which those opportunities occur.

The pages label their injury and availability rules explicitly. A player who is
Questionable may remain eligible until the relevant game or release is settled;
Out and other unavailable statuses are removed where the product contract says
they should be.
        """
    )


def _render_spread_terms() -> None:
    st.markdown(
        """
**Against The Spread (ATS)** means betting a handicap. If Kansas City is -7.5, it must win by 8 or more
for that side to cover. The underdog is +7.5 and covers by losing by 7 or fewer
or winning outright. A **push** occurs when the final margin lands exactly on a
whole-number spread; the stake is returned.

The model's predicted margin is compared with the posted number. The difference
is the model edge. A larger disagreement can be useful for a research filter,
but it is still uncertain and can lose.
        """
    )


def _render_market_terms() -> None:
    st.markdown(
        """
A **moneyline** prices who wins outright. A **total** (or over/under) prices the
combined score. American odds show the price rather than a probability. The
common -110 quote means risking 110 to win 100; the sportsbook's **juice** is
why a bettor needs about **52.4%** winners to break even at that price.

The site's 2026 Weekly Predictions page is spread-focused. Its 2025 total model
is an experimental demo and is not part of the current live week contract.
        """
    )


def _render_break_even() -> None:
    stats = _demo_stats()
    if stats is None:
        st.info("The current tracker statistics are unavailable; the definitions above still apply.")
        demo_line = "The 2025 demo tracker is unavailable in this session."
    else:
        overall_pct = stats["overall_pct"]
        hc_pct = stats["hc_pct"]
        hc_line = (
            f" and **{hc_pct}%** on high-confidence picks "
            f"({stats['hc_correct']}/{stats['hc_total']})"
            if hc_pct is not None
            else ""
        )
        demo_line = (
            f"The **2025 demo test** on this site (weeks 10-17) is **{overall_pct}% ATS** "
            f"({stats['overall_correct']}/{stats['overall_total']}){hc_line}. "
            f"{breakeven_verdict(overall_pct, hc_pct)}"
        )
    st.markdown(
        f"""
At standard -110 odds, 52.4% is the break-even rate before taxes, limits, or
other costs. A historical percentage above that line is not a promise about the
next sample. Confidence intervals, sample size, and selection rules matter.

The **current clean 2021-2025 benchmark** is median-triggered HIGH tickets
graded at the best US Tuesday number: **{LIVE_HIGH_WINS}/{LIVE_HIGH_N} =
{LIVE_HIGH_ATS * 100:.2f}%** ATS, with a one-sided 95% Wilson lower bound of
**{LIVE_HIGH_WILSON_LOWER * 100:.2f}%**. {live_high_bar_sentence()} This is Tuesday
line value, not closing-line value; betting every game is not the claim.

{demo_line}

Never bet more than you can afford to lose. Nothing here is betting or financial
advice.
        """
    )


def _render_edge_and_high() -> None:
    st.markdown(
        f"""
**Edge** is the gap between the model's predicted margin and the posted spread.
For 2026, the Tuesday US median drives the model, pick, displayed edge, and HIGH
qualification. **HIGH** is the highlighted slice when that disagreement is at
least **{HIGH_GAP:g} points** and the live line still meets the same threshold.
A later line can remove HIGH, but cannot create it mid-week. There is no live
medium tier.

HIGH is a documented threshold, not a confidence guarantee. The page still
shows every game so the filter is visible rather than hiding the misses.
        """
    )


def _render_line_movement() -> None:
    st.markdown(
        """
Lines move when sportsbooks and bettors update the price in response to new
information, injuries, limits, and market demand. I don't have sharp-money or
verified line-movement data. Background explanations about
professional and public bettors are not model inputs.

The 2026 release documents exactly which Tuesday market capture and locked quote
it uses. If a source cannot prove where a market claim came from, the site does
not publish that claim.
        """
    )


def _render_uncertainty() -> None:
    st.markdown(
        """
Variance is the natural spread of outcomes around a forecast. A good projection
can lose one game, one week, or one player matchup. A small sample can look
excellent or terrible by chance, so an honest evaluation names the sample,
the holdout period, the metric, and the uncertainty around it.

Backtests describe the tested period. They do not prove that a live season will
repeat the result, and model comparison does not establish causation.
        """
    )


def _render_half_ppr() -> None:
    st.markdown(
        """
Half-PPR gives **0.5 points per reception**, plus the usual yardage and
touchdown scoring. Full PPR gives a full point per reception; standard scoring
gives no reception bonus. The same player can rank differently across formats,
so check the scoring system before comparing projections.
        """
    )


def _render_projection_vs_rank() -> None:
    st.markdown(
        """
A **projection** is an estimated point total. A **ranking** orders players by
that estimate within a position or player pool. **ADP** is where the market is
drafting players. Those are related but different numbers: a player can have a
good projection and still be expensive at his ADP.

Weekly Fantasy is a current-week projection page. Draft Board is a preseason
season-total comparison page. They should not be treated as the same model.
        """
    )


def _render_role_and_matchup() -> None:
    st.markdown(
        """
Fantasy opportunity comes from role: snaps, routes, carries, targets, red-zone
work, and quarterback or offensive context. Efficiency tells you what a player
did with those chances. A projection combines both, but opportunity is often the
more immediate reason a player's weekly outlook changes.

Matchup and team context can move the estimate without turning into a guarantee.
Late injury news and role changes are reasons to check the release freshness note
before setting a lineup.
        """
    )


def _render_dfs() -> None:
    st.markdown(
        """
The DFS Optimizer solves a DraftKings Classic lineup under the contest's salary
and roster rules. It uses direct-DK projections from a checked artifact; it does
not convert Weekly Fantasy half-PPR points into DK points. A valid lineup still
requires the contest's salary CSV and late-news review.

The optimizer is a constrained research tool, not a claim that the lineup will
beat a field.
        """
    )


def _render_rookies_and_talent() -> None:
    st.markdown(
        """
The Rookie Board's **hit probability** is the share of historical players with a
similar profile who produced at least one startable season in their first three
years. It is not a per-season probability or a guarantee about one rookie.

Talent Scores are descriptive context. NFL Talent Score is a per-opportunity
estimate for NFL players; College Talent Score describes college production for
prospects. They use different scales, do not measure the same thing, and do not
feed the Draft Board's projections or ranks.
        """
    )


def _render_pipeline() -> None:
    st.markdown(
        """
The public workflow is:

1. Collect and validate the published source data.
2. Build features without using information from the future game or holdout.
3. Train the product-specific model in a private producer workflow.
4. Evaluate it on held-out or walk-forward data.
5. Validate the release artifact and publish an immutable pointer.
6. Render the release on the site and grade outcomes when the games finish.

The public site reads checked CSV/JSON artifacts. It does not train models or
load serialized training objects in the browser.
        """
    )


def _render_metrics() -> None:
    st.markdown(
        """
**MAE** is average absolute point or margin error; lower is better. **Rank
correlation** measures whether the ordering of players or teams tracks the
ordering of actual outcomes. **AUC** measures ranking skill for a binary outcome
such as a rookie hit. **ATS record** counts spread picks graded against the line.

A **confidence interval** shows how uncertain an estimated rate is. **Feature
importance** describes which inputs the fitted model used most, not which inputs
caused the outcome. None of these metrics proves a future individual result.
        """
    )


def _render_limits_and_data() -> None:
    st.markdown(
        """
The site uses published NFL play-by-play, schedules, player and roster context,
injury/availability information, market captures, and product-specific fantasy
or league data. Each product has a narrower contract; the product page and model
rundown state what is actually included.

The main limits are ordinary but important: data can be incomplete, a role can
change after a release, a holdout can be unrepresentative, and a model can be
wrong. The site labels missing or unverified sources instead of filling them
with an estimate.
        """
    )


def _render_model_rundowns() -> None:
    help_models.render_rundowns()


FAQS = (
    FAQItem("Site Guide", "What is JoScho Analytics?", ("about", "purpose", "advice"), _render_what_is_jsa),
    FAQItem("Site Guide", "Which page should I use?", ("directory", "pages", "products", "navigation"), _render_page_directory),
    FAQItem("Site Guide", "What do Live, Demo, Experimental, and Seasonal mean?", ("status", "current", "historical", "beta"), _render_states),
    FAQItem("Site Guide", "How often do pages update, and when do values lock?", ("freshness", "cadence", "kickoff", "release", "immutable"), _render_updates_and_locks),
    FAQItem("Site Guide", "How do filters and shareable URLs work?", ("season", "week", "min edge", "query", "url"), _render_filters_and_urls),
    FAQItem("Site Guide", "How does League History work?", ("sleeper", "espn", "yahoo", "cbs", "cookies", "credentials", "league id"), _render_league_history),
    FAQItem("Site Guide", "What is the Film Room?", ("video", "walkthrough", "breakdown"), _render_film_room),
    FAQItem("Football", "How does an NFL game become a score and a margin?", ("scoring", "possessions", "touchdown", "field goal", "game script"), _render_scoring),
    FAQItem("Football", "What is EPA?", ("expected points added", "efficiency", "play"), _render_epa),
    FAQItem("Football", "Why do injuries, rest, venue, and role matter?", ("availability", "quarterback", "depth chart", "context"), _render_injuries_context),
    FAQItem("Betting", "What do spread, favorite, underdog, cover, and push mean?", ("ats", "margin", "handicap"), _render_spread_terms),
    FAQItem("Betting", "What are moneylines, totals, odds, juice, and break-even?", ("american odds", "implied probability", "over", "under", "52.4"), _render_market_terms),
    FAQItem("Betting", "What win rate is needed to break even?", ("profit", "rate", "benchmark", "wilson", "record"), _render_break_even),
    FAQItem("Betting", "What are model edge and HIGH?", ("edge", "threshold", "tuesday", "2.5", "confidence"), _render_edge_and_high),
    FAQItem("Betting", "What moves a betting line, and what does this site track?", ("sharp money", "public money", "line movement", "market", "provenance"), _render_line_movement),
    FAQItem("Betting", "Why can a good projection still lose?", ("variance", "uncertainty", "sample size", "backtest", "chance"), _render_uncertainty),
    FAQItem("Fantasy", "What is half-PPR scoring?", ("ppr", "points per reception", "standard", "full ppr"), _render_half_ppr),
    FAQItem("Fantasy", "What is the difference between a projection, ranking, and ADP?", ("draft", "market", "model proj", "positional rank"), _render_projection_vs_rank),
    FAQItem("Fantasy", "How do role, opportunity, efficiency, and matchup affect fantasy?", ("snaps", "routes", "targets", "carries", "red zone"), _render_role_and_matchup),
    FAQItem("Fantasy", "How is DFS different from season-long fantasy?", ("draftkings", "classic", "salary", "lineup", "dk points"), _render_dfs),
    FAQItem("Fantasy", "What do the Rookie Board and Talent Scores mean?", ("rookie", "hit probability", "nfl talent", "college talent"), _render_rookies_and_talent),
    FAQItem("Models & Data", "How does a published model become a page?", ("pipeline", "features", "training", "holdout", "walk-forward", "artifact", "grading"), _render_pipeline),
    FAQItem("Models & Data", "How should I read the evaluation metrics?", ("mae", "rank correlation", "auc", "ats", "confidence interval", "feature importance"), _render_metrics),
    FAQItem("Models & Data", "What data does the site use, and what are the limits?", ("sources", "nflreadpy", "data", "limitations", "missing"), _render_limits_and_data),
    FAQItem("Models & Data", "How do the product-specific models work?", ("spread", "season totals", "draft board", "weekly fantasy", "dfs", "anytime td", "rookie", "charts", "shap", "xgboost", "lightgbm"), _render_model_rundowns),
)


def items_for_topic(topic: str) -> tuple[FAQItem, ...]:
    return tuple(item for item in FAQS if item.topic == topic)


def search_items(query: str) -> tuple[FAQItem, ...]:
    return tuple(item for item in FAQS if item.matches(query))
