"""Help & Guide page. Originally moved byte-identical from the retired app.py Help tab
(Batch 3d); refreshed 2026-07-14 to match the current multipage site — "tab" → "page"
throughout, the retired-sidebar references replaced (each page carries its own controls at
the top now), a Film Room entry + a site-organization note added, and the offseason /
Draft-Board and agent data-source notes corrected. Licensed-adjacent throughout: the
honest-numbers discipline (no CLV / beat-the-close claims) and the aggregate-only Draft
Board language are preserved unchanged. The live model stats the prose interpolates still
come from dashboard_data.accuracy_stats — the same shared plumbing app.py uses.
"""
import streamlit as st

import dashboard_data
import model_explanations


def render():
    try:
        df = dashboard_data.load_predictions()
    except FileNotFoundError:
        st.error("predictions_tracker.csv not found. Run the prediction pipeline first.")
        st.stop()
    except Exception as _load_err:
        st.error(f"Failed to load predictions data: {_load_err}")
        st.stop()
    if df.empty:
        st.warning("predictions_tracker.csv has no rows yet. Run the prediction pipeline to populate it.")
        st.stop()
    _stats = dashboard_data.accuracy_stats(df)   # 3a shared plumbing (byte-identical values)
    _acc_col         = _stats["acc_col"]
    _completed       = _stats["completed"]
    _overall_correct = _stats["overall_correct"]
    _overall_total   = _stats["overall_total"]
    _overall_pct     = _stats["overall_pct"]
    _hc_correct      = _stats["hc_correct"]
    _hc_total        = _stats["hc_total"]
    _hc_pct          = _stats["hc_pct"]
    st.title("❓ Help & Guide")
    st.caption("New to sports betting or just not sure how this site works? This page covers everything.")

    st.divider()

    # ── Section 1: Betting Basics ─────────────────────────────────────────────
    st.subheader("🏈 Betting Basics")

    with st.expander("What is ATS (Against The Spread)?"):
        st.markdown("""
ATS stands for **Against The Spread**. It's the most common way to bet on NFL games and it's what this whole site is built around.

Instead of just picking who wins, you're betting on whether a team wins by more or less than a set number of points. That number is called the spread.

**Here's a simple example:**

The Chiefs are favored by 7.5 points. If you bet the Chiefs, they need to win by 8 or more for you to win. If you bet the Raiders, they just need to lose by 7 or fewer or win outright. That's it.

Vegas sets the spread to try and split betting money evenly. They don't care who wins the game. They care about getting 50% of bets on each side so they profit from the juice no matter what.
        """)

    with st.expander("What is the spread and how does Vegas set it?"):
        st.markdown("""
The spread is set by oddsmakers at sportsbooks like DraftKings or FanDuel. They factor in team strength, injuries, home field, recent form, and a bunch of other stuff.

The key thing to understand is the spread is not meant to predict the actual final margin. It's meant to generate equal action on both sides. That distinction matters.

If the public loves the Chiefs and piles money on them, Vegas moves the line to make betting the Raiders more attractive. The line is always adjusting based on where money is flowing.

This is actually where edge comes from. If Vegas has to shade a line one way to balance public money, it can create value on the other side.
        """)

    with st.expander("What is edge and why does it matter?"):
        st.markdown("""
Edge is the gap between what the model predicts and what Vegas set as the spread.

If the model thinks the Chiefs will win by 10 but the spread is only 7.5, that's a 2.5 point edge on the Chiefs. The model is saying Vegas underpriced the Chiefs.

The bigger the edge, the more the model disagrees with the market. Games with a small edge (under 1 point) are basically coin flips in the model's eyes. Use the **Min Edge (pts)** slider at the top of the Weekly Predictions page to filter down to only the games where the model has real conviction.

You want to be betting games where the model has conviction, not games where it's a coin flip.
        """)

    with st.expander("What does it mean to cover?"):
        st.markdown("""
Covering just means beating the spread.

If the Chiefs are 7.5 point favorites and win 28 to 17, they won by 11. They covered. If they win 24 to 20, they won by 4. They didn't cover.

It works the other way too. If you bet the Raiders plus 7.5 and they lose by 4, the Raiders covered even though they lost the game.

The model is trying to predict the margin of victory and figure out which side of the spread is more likely to cover.
        """)

    with st.expander("How do you actually make money betting?"):
        _hc_line = f" and **{_hc_pct}%** on high confidence picks" if _hc_pct is not None else ""
        st.markdown(f"""
Honestly it's really hard and most people lose money. I want to be upfront about that.

Standard sportsbook odds are around 110 to win 100. That means you need to win about 52.4% of your bets just to break even. Most casual bettors don't hit that number.

To be profitable over time you need to consistently win more than 52.4%, bet games where there's real edge instead of gut feeling, and manage your bankroll properly. A common rule is never betting more than 2 to 5% of your total bankroll on a single game.

The model is currently at **{_overall_pct}% ATS** overall ({_overall_correct}/{_overall_total}){_hc_line}. {"Both are above break even, which is encouraging." if _hc_pct is not None else "This is above break even, which is encouraging."} But I want to be clear that past performance doesn't guarantee anything going forward. There will be bad weeks.

Never bet more than you can afford to lose.
        """)

    with st.expander("What is sharp money vs public money?"):
        st.markdown("""
Public money is casual bettors going with their gut. They tend to bet popular teams, primetime games, and whoever is on a hot streak. They're not doing deep analysis.

Sharp money is professional bettors who are placing large, calculated bets based on models and data. When sharps bet big, the line moves.

Watching line movement can tell you a lot. If the Chiefs open at 7 and move to 7.5, someone is betting the Chiefs heavily. If it's sharp money driving that, it's a signal worth paying attention to.

When the model and sharp money agree on the same side, that's a strong signal. When they disagree, the agent will flag it in the matchup analysis and it's worth being cautious.
        """)

    st.divider()

    # ── Section 2: How to Use the Website ────────────────────────────────────
    st.subheader("🖥️ How to Use This Website")

    with st.expander("How is the site organized?"):
        st.markdown("""
Everything lives in the top navigation bar, grouped into three menus:

- **Betting** — Weekly Predictions (the page you land on) and Track Record.
- **Fantasy** — Draft Board, Weekly Fantasy, and DFS Optimizer.
- **More** — Film Room, League History, and this Help & Guide.

The site opens on **Weekly Predictions** every time. There's no sidebar — each page carries its own controls (like the Season, Week, and Min Edge pickers) right at the top.
        """)

    with st.expander("How do I read the game cards?"):
        st.markdown("""
Each card shows one matchup for the week. Here's what the columns mean:

**SPREAD** is the Vegas line. A negative number means that team is favored.

**PREDICTED** is the model's version of the line — also shown sportsbook-style (favorite negative, underdog positive). When the model's number is *more* extreme than the Vegas spread on a side, that's where the edge is. Example: Vegas has SEA -7 but the model says SEA -11.3 — the model likes SEA by 4.3 more points than Vegas, so it recommends betting SEA.

**SCORE** shows the final score after the game is played. It's blank until results come in.

**BET X** shows which side the model recommends. The bold team name is who the model likes.

After results are in, each card will show either WIN or LOSS based on whether the model's pick covered.
        """)

    with st.expander("What do the agent confidence colors mean?"):
        st.markdown("""
The colored button on each game card tells you how confident the AI agent is after analyzing that matchup.

🟢 **High** means the model edge is strong and outside signals like injuries, line movement, and historical data all point the same direction. These are the games worth prioritizing.

🟡 **Medium** means there's edge but something is giving mixed signals. Maybe sharp money is split or there's an injury that could swing things. Worth considering but not a lock.

🔴 **Skip** means the agent is recommending you pass on this game. The edge is too small, signals are conflicting, or there's too much uncertainty. Not every game is worth betting.

Click the Matchup Analysis button on any card to read the full reasoning.
        """)

    with st.expander("What is the Min Edge filter?"):
        st.markdown("""
The **Min Edge (pts)** slider at the top of the Weekly Predictions page controls which games show up.

At 0.0 (the default) you see every game. At 1.0 you only see games where the model disagrees with Vegas by at least 1 point. At 3.0 you're only seeing the high conviction plays.

Slide it up to filter down to your highest-confidence plays.
        """)

    with st.expander("How often does the site update?"):
        st.markdown("""
During the season the site runs on an automated schedule through GitHub Actions.

Tuesday morning it fills in the previous week's results and posts initial predictions for the upcoming week using the opening Vegas lines. Thursday night it refreshes those predictions after injury reports drop. Sunday morning it locks in final predictions before kickoff. Then the cycle repeats on Tuesday.

During the offseason the weekly predictions pause, but the pre-season **Draft Board** stays live and refreshes daily from the latest draft data. Weekly predictions spin back up when the season kicks off in September.
        """)

    with st.expander("What is the Track Record page?"):
        st.markdown("""
The Track Record page is where you can see how the model has done across the whole season, not just one week.

It shows a week by week bar chart of ATS win percentage, a cumulative trend line showing how accuracy has moved over time, and a breakdown of how high edge games performed compared to low edge games.

There's also a best and worst weeks section, a full season table, and a separate Over/Under model section showing how the totals picks performed.
        """)

    with st.expander("What is the Over/Under (Totals) model? (Experimental)"):
        st.markdown("""
**Status: experimental — tracking only, not yet a confident pick.**

In addition to picking sides against the spread, the site runs a separate model for the over/under total. It predicts whether the final combined score will go over or under the Vegas total line. It uses the same underlying features as the spread model plus 14 totals-specific inputs: the Vegas total line, implied team totals, weather (temperature and wind), dome/outdoor status, rolling points scored and allowed by each team over the last 5 games, the league scoring environment over the last 4 weeks, pace (plays per game), and whether it's a division game.

The key finding from development: the edge only shows up on **UNDER picks**, not OVERs. The reason is that recreational bettors tend to bet OVER — everyone loves a shootout — which causes books to shade totals lines slightly high. That creates a systematic edge on the UNDER side that the model is designed to find.

A pick is only flagged as **UNDER** when both the XGBoost and Ridge models independently predict the score will come in below the line. When they disagree, the model passes.

**Where it stands:**
- Walk-forward CV (2020–2025, n=575): **55.7%** hit rate, comfortably above the 52.4% break-even.
- Live 2025 (weeks 10–17, n=46): **52.2%** hit rate, essentially at break-even. The sample is too small to distinguish real edge from CV noise (95% CI is roughly 37–67%).

That's why the badges on the game cards are amber/dashed instead of green — the model says UNDER, but I haven't yet confirmed live that it's actually profitable. I track it through the 2026 season and reassess after a full season of real evidence (~96 picks). **Don't bet these picks; treat them as something to watch.**
        """)

    with st.expander("What is the Weekly Fantasy page?"):
        st.markdown("""
The Weekly Fantasy page shows weekly half-PPR fantasy projections for every active QB, RB, WR, and TE. Each position has its own subtab.

You can filter by team or health status and see projected fantasy points alongside position-specific stat projections (passing yards, rushing yards, receptions, receiving yards). Once the week's games are played, actual stats fill in automatically.

See the Fantasy Projections section below for more detail on how the models work.
        """)

    with st.expander("What is the DFS Optimizer page?"):
        st.markdown("""
The DFS Optimizer page is a DraftKings NFL Classic lineup optimizer launching with the 2026 season.

Upload your DraftKings salary CSV and the optimizer generates the highest-projected legal 9-player lineup under the $50,000 salary cap. See the DFS Optimizer section below for a full breakdown.
        """)

    with st.expander("What is the Draft Board page?"):
        st.markdown("""
The Draft Board is a **pre-season draft tool** for the 2026 season, separate from the Weekly Fantasy page. The point estimate for each player is the market's — powered by Sleeper's season projections compared against the draft market (ADP, average draft position). My contribution is a calibrated range around that estimate: a floor and ceiling, the chance of a top-12 or top-24 finish at the position, and a bust-risk figure for players typically drafted early at their position.

**How the range was checked:** across 900 player-seasons (2021–2025), about 8 in 10 players finished inside their 80% range — close to what the math promises. The projections-vs-price comparison itself has a tested track record as a group pattern for some player groups (marked with a "Signal check" badge on the board) and is untested for others — the badge tells you which group a player falls into. None of this is a guarantee, or a recommendation, about any individual player — it describes patterns across many players.

A separate "2025 Efficiency" column shows context only — it is not part of the value signal, and testing showed it does not predict draft value.

Use the **Position** filter to narrow the board, and the **Show advanced view** toggle for the full percentiles, raw metrics, and verbatim research labels behind the plain columns.
        """)

    with st.expander("What is the Film Room page?"):
        st.markdown("""
The Film Room page collects short, model-backed video breakdowns — each TikTok short sits next to the full written analysis it's based on. Click **📖 Full breakdown** under a video to open the deep dive the short couldn't fit.

Some older videos predate my validation work and make calls I wouldn't make today. Those carry a **📼 Archived — why?** pop-out explaining what's changed; they stay up, unedited, as part of the record, and point you to what I publish now.
        """)

    st.divider()

    # ── Section 3: Fantasy Projections ───────────────────────────────────────
    st.subheader("🏆 Fantasy Projections")

    with st.expander("How do the fantasy projections work?"):
        st.markdown("""
The Weekly Fantasy page uses a separate machine learning system from the betting model. There are four XGBoost models — one for each position (QB, RB, WR, TE) — each trained on NFL player stats from 2020 through 2024 with the 2025 season held out as a real-world test.

Each model predicts **half-PPR fantasy points** for the upcoming week based on roughly 80 features, including:

- The player's recent production (3 and 5-game rolling averages for targets, carries, receiving yards, etc.)
- Their team's offensive efficiency (EPA per play, yards per play, red zone rate)
- The opponent's defensive quality (EPA allowed, pass rate faced, red zone defense)
- Vegas implied team total — how many points Vegas expects the team to score
- Injury and availability status for the player and their key teammates
- Depth chart position
- Home/away split, weather, and surface

The models are retrained each offseason as more data becomes available.
        """)

    with st.expander("How accurate are the fantasy projections?"):
        st.markdown("""
The models were evaluated on the full 2025 holdout season against a simple 3-week rolling average baseline:

| Position | Model MAE | Baseline MAE | Improvement |
|----------|-----------|--------------|-------------|
| QB | 7.0 pts | 7.5 pts | ✅ Better |
| RB | 4.5 pts | 4.6 pts | ✅ Better |
| WR | 3.9 pts | 4.1 pts | ✅ Better |
| TE | 3.2 pts | 3.5 pts | ✅ Better |

MAE (Mean Absolute Error) is the average number of points the projection was off by. So for WR, the model was off by about 3.9 points on average. Given the inherent variance in fantasy football, this is a reasonable result — but any individual week can be much higher or lower.

The projections are most useful as a relative ranking tool rather than a precise point forecast. A player projected at 18 points is likely to outscore one projected at 10, but the exact numbers should be treated as estimates.
        """)

    with st.expander("What are the prop stat columns?"):
        st.markdown("""
In addition to projected fantasy points, each position tab shows position-specific stat projections from eight separate XGBoost models:

| Column | Position | What it predicts |
|--------|----------|-----------------|
| Proj Pass Yds | QB | Passing yards |
| Proj Rush Yds | QB / RB | Rushing yards |
| Proj Rec Yds | RB / WR / TE | Receiving yards |
| Proj Receptions | WR / TE | Number of receptions |

These prop stat models were trained on the same data as the main models but with each individual stat as the target. They're useful as a rough reference when looking at player prop bets on sportsbooks (e.g. over/under pass yards, reception totals).

A few things to keep in mind:
- The prop projections are **independent** models — their values won't perfectly add up to the fantasy point total
- QB passing yards has the highest error (~70 yards off on average), so treat it as directional
- RB and TE receiving yards are the most accurate prop models (~10–14 yards MAE)
        """)

    with st.expander("What do the column headers mean?"):
        st.markdown("""
**Player** — Player name and their NFL team.

**Opponent** — This week's opponent. `@` means away game, `vs` means home game.

**Proj Pts** — Projected half-PPR fantasy points. Half-PPR scoring: 0.5 pts per reception, 1 pt per 10 rush or receiving yards, 6 pts per TD.

**Off EPA** — The team's offensive efficiency over the last 4 games, measured in Expected Points Added per play. Higher is better. See "What is Off EPA?" below for a full explanation.

**EPA Rank** — Where the team's offense ranks among all 32 teams this season (1st = best, 32nd = worst). Color-coded green to red.

**Team Total** — Vegas implied team total: how many points Vegas expects this team to score. Higher means more expected scoring opportunity for that team's players.

**Health** — The player's injury status from the NFL injury report: ✅ Healthy · 🟡 Questionable · ⚠️ Doubtful · ❌ Out. Players officially ruled Out are removed from the projections entirely.

**Actual Pts / Actual [stat]** — Once the week's games are played, actual fantasy points and stats fill in automatically. A blank cell means the player did not play (DNP) in that game.
        """)

    with st.expander("What is Off EPA?"):
        st.markdown("""
**Off EPA** stands for Offensive Expected Points Added per play, averaged over the team's last 4 games.

EPA measures how much each play moves the needle toward scoring. A 5-yard gain on 3rd and 4 is worth a lot more EPA than a 5-yard gain on 1st and 10. So EPA per play is a better measure of offensive efficiency than yards or points, because it accounts for down, distance, and field position.

- **Positive (e.g. +0.15)** — the offense has been efficient recently, generating more value per play than expected
- **Near zero (e.g. +0.01)** — average offense
- **Negative (e.g. -0.12)** — the offense has been struggling

League average hovers near 0. Values above +0.10 are strong, below -0.10 are poor.

This matters for fantasy because players on efficient offenses tend to see more opportunities in positive game scripts and convert them at a higher rate. It's one of the stronger predictors in the model for every position.
        """)

    with st.expander("How often do fantasy projections update?"):
        st.markdown("""
Fantasy projections are generated each week as part of the same automated pipeline that runs the betting predictions.

The projection file for each week is saved once and doesn't change after that — it reflects the injury and depth chart data available at the time it was run. Actual stats fill in automatically after each game is played, pulling live from nflreadpy and caching for 1 hour.

If you're looking at a past week, the actuals shown are the real NFL stats for that game.
        """)

    st.divider()

    # ── Section 3b: Talent Score & Rookie Score (Draft Board columns) ─────────
    st.subheader("🧮 Talent Score & Rookie Score")

    with st.expander("What are the two score columns on the Draft Board?"):
        st.markdown("""
The Draft Board carries two context columns I build myself, answering two different questions.

**The Talent Score** is my model-based estimate of what a player does with each opportunity — each carry, route, or throw — separated from his situation where that separation is statistically possible. It is not a summary of his production, and models can be wrong. Volume is excluded by design: how often a player is used lives in the confidence channel instead, so a thin sample gets a wider range and a lower confidence weight, not a lower score.

**The Rookie Score** is a college-production read for 2026 rookies at RB, WR, and TE, scaled against past drafted prospects at the same position. It describes what a prospect did in college; it does not claim to predict NFL careers or fantasy value.

**They are two different scales.** The Talent Score ranks NFL players against NFL players; the Rookie Score ranks prospects against past prospects. A 90 in one column is not a 90 in the other, and neither feeds any other number on this board.
        """)

    with st.expander("How the Talent Score is built (and what it doesn't measure)"):
        st.markdown("""
For running backs, receivers, and tight ends, a week-by-week model splits performance into the player's own effect, his team's effect, and the opponent's effect, then keeps the player's part. Honestly, that adjustment is small — team and opponent together explain roughly 8% of week-to-week variance; most weekly movement is noise, and the score is built to look through it.

Quarterbacks are the asterisk: one starter per team means a QB's situation cannot be separated from him, so QB scores ship **unadjusted** — a different kind of estimate under the same header. The QB facets measure completion rate versus expectation (overall and on throws of 20+ air yards), ball-placement discipline, and rushing value. They do **not** measure performance under pressure, off-script play, or pre-snap work — I screened a pressure-performance facet family under a pre-registered rule and none survived it, so that gap stays open and disclosed.

Recent seasons count more (a declared decay, roughly a 3.5-season half-life). Every score comes with a range — the honest uncertainty — plus † for lower-confidence rows and ‡ for the lowest. A 50 means the weakest draftable player at the position, not a league-average one, and an individual score is not each player's single best point estimate: ranks and ranges are the reliable reads. For early-career running backs I blend in a college prior at the weak agreement level I actually measured (about 0.385); at WR and TE the measured agreement was near zero, so their scores are NFL-only.

These columns are context only: a pre-registered test found measures like these do not predict where the draft market is wrong, so they never combine with the Gap, ranges, or chance columns anywhere on the board.

The full write-up — every design choice, the admission gates, and where it fails — lives in `fantasy/talent/GUIDE.md` in the repo.
        """)

    st.divider()

    # ── Section 4: DFS Optimizer ──────────────────────────────────────────────
    st.subheader("🎯 DFS Optimizer")

    with st.expander("What is the DFS Optimizer?"):
        st.markdown("""
The DFS Optimizer page is a DraftKings NFL Classic lineup optimizer launching with the 2026 season.

It takes this site's weekly fantasy projections and solves for the highest-projected legal lineup under the $50,000 salary cap using an integer linear program. The optimizer fills all 9 roster slots — QB, 2 RB, 3 WR, TE, FLEX, DST — subject to DraftKings' constraints.

The workflow each week is:
1. Download your DraftKings salary CSV from any NFL Classic contest lobby
2. Upload it in the DFS Optimizer page
3. The optimizer fuzzy-matches DK player names to my projected points and solves the lineup
4. Lock or exclude specific players and re-run if you want to tweak it
5. Download the finished lineup ready for DraftKings import

Note that DST currently uses DraftKings' season average since there is no team-defense projection model yet. That's listed as a known limitation on that page.
        """)

    with st.expander("How does the optimizer actually work?"):
        st.markdown("""
Under the hood it's an integer linear program (ILP) solved with the PuLP library.

The optimizer treats each player as a binary variable — either in the lineup (1) or out (0) — and maximizes total projected points subject to hard constraints:

- Exactly 1 QB
- At least 2 RBs
- At least 3 WRs
- At least 1 TE
- Exactly 1 DST
- Exactly 9 total players (the FLEX slot is filled implicitly by the solver)
- Total salary ≤ $50,000
- No more than 8 players from the same team

The solver finds the globally optimal combination given those constraints in under a second. It's not greedy — it considers every valid roster combination simultaneously.

Projections are converted to full DraftKings Classic scoring (full PPR, milestone bonuses for 300+ passing yards, 100+ rushing yards, 100+ receiving yards).
        """)

    st.divider()

    # ── Section 5: League History ─────────────────────────────────────────────
    st.subheader("🏅 League History")

    with st.expander("What is the League History page?"):
        st.markdown("""
The League History page pulls your Sleeper fantasy league's historical data and displays it in one place.

Enter your Sleeper league ID (found in your league's URL: `sleeper.com/leagues/{ID}/league`) and the page loads standings, matchup results, and season-by-season records for every manager in the league.

You can filter by season or view all-time records across every year your league has existed. It's useful for settling debates about who's actually been the best manager historically versus just the most recent champion.
        """)

    st.divider()

    # ── Section 6: Model explanations ────────────────────────────────────────
    st.subheader("🧠 What Drives the Models")
    st.caption(
        "Top-five global feature influence for every production model currently surfaced by the site."
    )

    with st.expander("Explore model feature influence"):
        st.markdown("""
These charts summarize how strongly each model uses a feature **across many predictions**. They do
not say that a feature caused an outcome, and they are not an accuracy ranking. Percentages are
normalized within each model; the five displayed bars will not usually add to 100% because the
remaining features are omitted.

Season-projection and spread charts use mean absolute Tree SHAP. Weekly fantasy and the totals
XGBoost model use the model's gain importance. The totals Ridge chart uses absolute standardized
coefficients. The production spread prediction is a fixed 75% XGBoost / 25% Ridge blend; its SHAP
chart covers the tree component that supplies 75% of the prediction.
        """)
        st.markdown(model_explanations.CHART_CSS, unsafe_allow_html=True)
        _shap_models, _stale_models = model_explanations.shap_models()
        _all_models = _shap_models + model_explanations.native_models()
        for _group in (
            "Season projections · Non-rookie models",
            "Season projections · Rookie models",
            "Weekly fantasy",
            "Betting",
        ):
            _group_models = [m for m in _all_models if m["group"] == _group]
            if not _group_models:
                continue
            st.markdown(f"#### {_group}")
            _subgroups = ("QB", "RB", "WR", "TE") if _group == "Weekly fantasy" else (None,)
            for _subgroup in _subgroups:
                _display_models = (
                    [m for m in _group_models if m.get("subgroup") == _subgroup]
                    if _subgroup else _group_models
                )
                if not _display_models:
                    continue
                if _subgroup:
                    st.markdown(f"##### {_subgroup}")
                _left, _right = st.columns(2)
                for _idx, _model in enumerate(_display_models):
                    (_left if _idx % 2 == 0 else _right).markdown(
                        model_explanations.chart_html(_model), unsafe_allow_html=True
                    )
        if _stale_models:
            st.warning(
                "Updated model artifacts detected. Explanations withheld until recomputed: "
                + ", ".join(_stale_models)
            )

    with st.expander("Review historical season-projection bias"):
        st.markdown("""
This is a **2021–2025 walk-forward out-of-sample audit** of 2,589 non-rookie season projections.
Bias is model projection minus actual half-PPR points: a negative number means the model
underprojected the player, while a positive number means it overprojected him. The top 20%
is selected by the model's prediction within each position and season—not by the eventual
result—so the comparison does not manufacture underprojection by selecting actual stars.
        """)
        st.markdown(
            model_explanations.calibration_audit_html(),
            unsafe_allow_html=True,
        )
        st.markdown("""
**What it says:** there is no global top-end compression. Non-rookie WR and TE projections are
approximately neutral at the top, and QB is slightly high. RB is the exception: its top
predicted group finished 21.3 points above its projection on average. That RB result was
found during a multi-position diagnostic scan, so it is an exploratory lead for a future
pre-registered calibration test—not a production adjustment or a guarantee for an
individual player.
        """)

    st.divider()

    # ── Section 7: Behind the Scenes ─────────────────────────────────────────
    st.subheader("🔧 Behind the Scenes")

    with st.expander("How does the prediction model work?"):
        st.markdown("""
The site runs two independent prediction systems: one for the **spread** (ATS picks) and one for the **over/under total**.

**Spread model**

Four models trained on over 3,000 NFL games spanning 11 seasons (2014–2024).

The primary model is the **Ensemble (fixed75)** — a fixed-weight blend of 75% XGBoost and 25% Ridge regression. It sets the predicted edge for each game and determines the sort order.

The three direction voters are **XGBoost**, **Ridge**, and **LightGBM** — three independent models that each predict which side of the spread they favor.

Each game is evaluated by all four models. The consensus tier is assigned based on voter agreement plus Ensemble edge size:

- **HIGH** — all three voters agree on direction *and* the Ensemble edge is 3+ points
- **MEDIUM** — all three voters agree on direction *and* the Ensemble edge is 1+ points (but under 3)
- **PASS** — the voters disagree, or they agree but edge is under 1 point

85 features were engineered, then trimmed to the top 35 via a walk-forward ablation study. The main features are rolling EPA, strength of schedule, All-Pro roster quality, injury impact, QB changes, coaching history, and home field advantage.

**Totals model (experimental)**

A separate two-model system (XGBoost + Ridge) trained to predict whether the final combined score will be over or under the Vegas total line. Uses 35 spread features plus 14 totals-specific inputs (total line, implied team totals, weather, dome status, rolling points, league scoring environment, pace, division game flag).

The CV result (2020–2025, 55.7% on 575 picks) suggests a real UNDER-side edge, consistent with the known retail OVER bias. **But live 2025 results so far (52.2% on 46 picks) are at break-even, not yet confirming the CV.** The 2025 sample is too small to tell — I'm tracking through 2026 before treating these as real picks.

All models are retrained each offseason as new data comes in.
        """)

    with st.expander("What is the LLM agent and what does it do?"):
        st.markdown("""
The agent is built on top of the prediction models using LlamaIndex and Anthropic's Claude API.

It has 5 tools it can call: model predictions, injury reports, line movement data, historical head to head matchups going back to 2015, and a model confidence analyzer.

Each week it goes through every game, calls those tools, and reasons about whether the model's prediction is backed up by real world signals. It's not overriding the model. It's asking whether everything else lines up with what the model is saying.

If the model likes a team, sharp money likes that team, they're healthy, and they dominate this matchup historically, the agent marks it high confidence. If the model likes a team but their star QB is out and sharp money is going the other way, the agent will tell you to skip it.

The idea is that raw model predictions are a starting point. The agent adds a layer of reasoning to help filter out plays where the edge might just be noise.
        """)

    with st.expander("How accurate is the model?"):
        _best_week = _completed.groupby(['season','week'])[_acc_col].agg(['sum','count'])
        _best_week['pct'] = _best_week['sum'] / _best_week['count']
        _bw = _best_week['pct'].idxmax() if not _best_week.empty else None
        _bw_str = (f"Season {_bw[0]} Week {_bw[1]} was the strongest week so far at "
                   f"{int(_best_week.loc[_bw,'sum'])} out of {int(_best_week.loc[_bw,'count'])} correct. "
                   ) if _bw else ""
        _hc_line2 = f" and **{_hc_pct}%** on high confidence picks" if _hc_pct is not None else ""
        _be_comment2 = "Both numbers are above that." if _hc_pct is not None else "That number is above break even."
        st.markdown(f"""
The model has gone **{_overall_pct}% ATS** across {_overall_total} completed games ({_overall_correct} correct){_hc_line2}. The break even threshold at standard sportsbook odds is 52.4%, so {_be_comment2}

{_bw_str}
I want to be honest though. Past performance doesn't guarantee anything going forward. There will be bad weeks. The goal is to track this over multiple seasons and see if the edge holds up.
        """)

    with st.expander("What data does it use?"):
        st.markdown("""
The model pulls play-by-play and schedule data from nflreadpy going back to 1999. Real weekly injury reports (from `nfl.load_injuries()`) feed directly into the feature set — Out and Doubtful players reduce a team's weighted All-Pro score, which is one of the stronger predictors.

The All-Pro data is a custom CSV covering selections from 1997 to 2025. It's used as a proxy for roster talent: players are weighted over a 3-year lookback (4/2/1) so recent selections matter more. This gets updated manually each January.

The agent's line-movement tool currently uses mock data for demonstration; wiring in a live odds API is on the roadmap for the 2026 season. Injury data, by contrast, is real — pulled live from nflreadpy — both in the model's features and in the agent's injury tool.
        """)

    with st.expander("Is this financial advice?"):
        st.markdown("""
No. This is a personal data science project. I built it to explore whether a machine learning model can find a consistent edge against the spread.

Nothing on this site should be taken as betting or financial advice. Sports betting involves real financial risk. Always bet responsibly.
        """)

    st.markdown("""
        <div style='text-align:center;padding:28px 0 12px 0;border-top:1px solid #2d3748;margin-top:12px'>
            <div style='font-size:11px;color:#444;margin-bottom:10px;letter-spacing:0.3px'>
                Not financial advice. Sports betting involves real risk. Bet responsibly.
            </div>
            <div style='font-size:13px;color:#666'>
                Built by <b style='color:#999'>Joseph Schoenbaum</b>
                &nbsp;·&nbsp;
                <a href='https://github.com/joscho11/JoSchoAnalytics'
                   style='color:#3D95CE;text-decoration:none'>GitHub</a>
                &nbsp;·&nbsp;
                <a href='https://venmo.com/u/JoScho'
                   style='color:#3D95CE;text-decoration:none'>💙 Venmo @JoScho</a>
            </div>
        </div>
    """, unsafe_allow_html=True)
