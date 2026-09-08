"""Help & Guide page.

FAQ plus a model-rundown section for every prediction product the site currently
publishes. Licensed-adjacent throughout: no CLV / beat-the-close claims, no
public naming of the Draft Board Sleeper mix, aggregate-only Draft Board language.
Live ATS numbers interpolate from live_2026.py. 2025 demo ATS interpolates from
dashboard_data.accuracy_stats.
"""
import streamlit as st

import dashboard_data
import help_models
import nav_registry
from dashboard_utils import breakeven_verdict
from live_2026 import HIGH_GAP, LIVE_HIGH_ATS, LIVE_HIGH_N, LIVE_HIGH_WILSON_LOWER, LIVE_HIGH_WINS, live_high_bar_sentence
from video_content import LATEST_LEAGUE_HISTORY_VIDEO_SLUG


def render():
    st.title("Help & guide")
    st.caption("New to the site, or to betting the spread? Start here.")
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
    _demo = df[df["season"] == 2025] if "season" in df.columns else df
    _stats = dashboard_data.accuracy_stats(_demo if not _demo.empty else df)
    _overall_correct = _stats["overall_correct"]
    _overall_total   = _stats["overall_total"]
    _overall_pct     = _stats["overall_pct"]
    _hc_correct      = _stats["hc_correct"]
    _hc_total        = _stats["hc_total"]
    _hc_pct          = _stats["hc_pct"]
    st.subheader("Start here")
    with st.container(horizontal=True, gap="small", key="jsa-help-start"):
        for slug, label, icon in (
            ("draft-board", "Build a draft plan", ":material/list_alt:"),
            ("weekly-predictions", "Read this week's slate", ":material/query_stats:"),
            ("anytime-tds", "Compare anytime TDs", ":material/sports_score:"),
            ("dfs-optimizer", "Build a DK lineup", ":material/target:"),
            ("track-record", "Audit the results", ":material/monitoring:"),
        ):
            page = nav_registry.PAGES.get(slug)
            if page is not None:
                st.page_link(page, label=label, icon=icon, width="stretch")
            else:
                st.markdown(f"**{label}**")

    st.subheader("🏈 Betting Basics")

    with st.expander("What is ATS (Against The Spread)?"):
        st.markdown("""
ATS stands for **Against The Spread**. It's the most common way to bet NFL games, and it's what the Weekly Predictions page is built around.

Instead of picking who wins, you bet whether a team wins by more or less than a set number of points. That number is the spread.

**Example:** the Chiefs are favored by 7.5. Bet the Chiefs, they need to win by 8 or more. Bet the Raiders, they need to lose by 7 or fewer, or win outright.

Sportsbooks set the spread to split money, not to predict the final margin. They profit from the juice either way.
        """)

    with st.expander("What is the spread and how does Vegas set it?"):
        st.markdown("""
Oddsmakers set the spread from team strength, injuries, home field, and recent form.

The spread is not a forecast of the actual margin. It is a price meant to attract bets on both sides. If the public piles onto the Chiefs, the line moves to make the other side more attractive.

That movement is where a model can find a gap: the number on the board is a market price, not a true score prediction.
        """)

    with st.expander("What is edge and why does it matter?"):
        st.markdown(f"""
Edge is the gap between what the model predicts and the posted spread.

If the model has the Chiefs by 10 and the spread is 7.5, that is 2.5 points on the Chiefs. Games under 1 point of disagreement are coin flips in the model's eyes.

On **2026**, every game still shows. HIGH is the green highlight ({HIGH_GAP:g} or more points off the Tuesday line, and still {HIGH_GAP:g} off the live line). On the **2025 demo** weeks, use the **Min Edge (pts)** slider to hide the coin flips.
        """)

    with st.expander("What does it mean to cover?"):
        st.markdown("""
Covering means beating the spread.

Chiefs -7.5, win 28-17 (by 11): they covered. Win 24-20 (by 4): they did not.

The other way works too. Raiders +7.5, lose by 4: the Raiders covered even though they lost the game.

The model predicts the margin, then asks which side of the posted number is more likely to cover.
        """)

    with st.expander("How do you actually make money betting?"):
        _hc_line = (f" and **{_hc_pct}%** on high confidence picks "
                    f"({_hc_correct}/{_hc_total})" if _hc_pct is not None else "")
        _be_comment = breakeven_verdict(_overall_pct, _hc_pct)
        st.markdown(f"""
Standard sportsbook odds are about 110 to win 100. You need about **52.4%** of bets to break even. Most casual bettors don't hit that.

The **2026 live book** is Tuesday HIGH scored at the best US Tuesday number: **{LIVE_HIGH_WINS}/{LIVE_HIGH_N} = {LIVE_HIGH_ATS * 100:.2f}%** ATS, one-sided 95% Wilson lower bound **{LIVE_HIGH_WILSON_LOWER * 100:.2f}%**, walk-forward 2021-2025. {live_high_bar_sentence()} HIGH still flags off the Tuesday median. Take the best number. All-bets is not the claim. No 2026 games are graded yet. This is Tuesday line value, not closing-line value.

The **2025 demo test** on this site (weeks 10-17) is **{_overall_pct}% ATS** ({_overall_correct}/{_overall_total}){_hc_line}. {_be_comment} That walkthrough is the old three-model consensus, not the 2026 live book. Past performance doesn't guarantee anything going forward. There will be bad weeks.

Never bet more than you can afford to lose.
        """)

    with st.expander("What is sharp money vs public money?"):
        st.markdown("""
Public money is casual bettors. Popular teams, primetime, whoever is hot.

Sharp money is professional bettors placing large, calculated bets. When they bet, the line often moves.

**What this site does not know:** I don't have sharp-money or line-movement data. Nothing here tracks where professional money is going. The paragraph above is background on how betting markets work, not an input to the model.
        """)

    st.divider()
    st.subheader("🖥️ How to Use This Website")

    with st.expander("What is live vs demo on this site?"):
        st.markdown(f"""
**Live 2026 (the current season)**

- **Draft Board:** 180-player Model Proj, frozen until the early-September snapshot. Sleeper ADP (default), ESPN ADP, and Yahoo ADP, plus Sleeper Proj, refresh daily.
- **Rookie Board:** hit % and RB/WR/TE season-total projections for the 2024-2026 classes.
- **Season Totals:** 32-team win projections. HIGH is the only certified pick.
- **Weekly Predictions:** 2026 matchups are up. The public spread card uses the first valid Tuesday market capture from 09:00–15:30 ET. HIGH is the green {HIGH_GAP:g}-point Tuesday ticket.
- **Weekly Fantasy:** 2026 Week 1 rankings land once that file is published. Until then the page opens on the latest published file (the 2025 Week 17 demo in the 2026 layout).
- **DFS Optimizer:** DraftKings Classic lineup builder. Upload a salary CSV. Uses a published direct-DK file when one exists; otherwise upload your own. No 2026 Week 1 projection file is published yet. Not a performance claim.

**Demo / walkthrough (not the live book)**

- **2025 Weekly Predictions** weeks 10-end: old three-model consensus, HIGH / MED / PASS badges, Min Edge slider.
- **2025 Weekly Fantasy** weeks 10-17: previous per-position XGBoost system, extra prop columns.
- **Anytime TDs:** 2025 weeks 10-17, rushing and receiving TDs only. Not even money. The book was still a hair more accurate. For fun. Not a proven edge.
- **Over/Under totals:** 2025 demo only, experimental, not on the 2026 week page.

**Not a prediction model**

Talent Scores are descriptive context. League History is your Sleeper, ESPN, Yahoo, or CBS league, not a forecast. Film Room is video.
        """)

    with st.expander("How is the site organized?"):
        st.markdown("""
Everything lives in the top navigation bar, grouped into three menus:

- **Home**: a stable overview of what is live and where to start.
- **Fantasy**: Draft Board, Rookie Board, Weekly Fantasy, and DFS Optimizer.
- **Betting**: Weekly Predictions, Anytime TDs, Track Record, and Season Totals.
- **More**: Film Room, League History, and this Help & Guide.

The site opens on **Home** every time. There is no sidebar. Each product page carries its own controls (Season and Week, plus a Min Edge slider on the 2025 demo weeks) near the top. Season and Week selections on Weekly Predictions and Weekly Fantasy are reflected in the URL, so a filtered view can be shared.
        """)

    with st.expander("How do I read the game cards?"):
        st.markdown(f"""
Each card is one matchup.

**SPREAD** is the Vegas line. Negative means that team is favored.

**PREDICTED** is the model's version of the line, sportsbook-style (favorite negative). When the model's number is more extreme than Vegas on a side, that is the edge. Example: Vegas SEA -7, model SEA -11.3. The model likes SEA by 4.3 more points, so it recommends SEA.

**SCORE** fills in after the game. Blank until then.

**BET X** is the recommended side. The bold name is who the model likes.

**2026 live:** every game gets a pick. **HIGH** (green) is a {HIGH_GAP:g}+ point disagreement with the Tuesday market snapshot, and the live line still {HIGH_GAP:g}+. If the line moves and that gap falls under {HIGH_GAP:g}, HIGH is dropped. It cannot be created mid-week. No medium tier. No totals on the 2026 week page.

**2025 demo test:** weeks 10 through the end of that season still use HIGH / MED / PASS consensus badges. Those weeks are unchanged.

After results land, each card shows WIN or LOSS based on whether the pick covered.
        """)

    with st.expander("What is the Min Edge filter?"):
        st.markdown("""
On **2026**, every game is shown. HIGH picks are the green highlight. The Min Edge slider is hidden.

On the **2025 demo** weeks, **Min Edge (pts)** at the top of Weekly Predictions controls which games show up. 0.0 (default) is every game. 3.0 is only the high-conviction plays from that old consensus.
        """)

    with st.expander("How often does the site update?"):
        st.markdown(f"""
**2026 live.** Picks use the first valid Tuesday capture in the 09:00–15:30 ET window. After that, the only change on the week page is dropping HIGH if the live line shrinks the gap under {HIGH_GAP:g} points. A later line cannot promote a game into HIGH. Totals stay off this season's week page.

**2025 demo test** used the older Monday / Thursday / Sunday refresh. Those weeks are frozen as a walkthrough.

During the offseason, 2026 matchups stay on Weekly Predictions with no picks until the Tuesday market capture window. The pre-season **Draft Board** refreshes
Sleeper ADP, ESPN ADP, Yahoo ADP, and Sleeper projections daily for its fixed 180-player universe; draft-price
ranks, Sleeper ranks, and both gap columns move with those updates. Model Proj points and
ranks remain frozen until the dated early-September public-information snapshot.
        """)

    with st.expander("What is the Track Record page?"):
        st.markdown(f"""
Season-long ATS, not one week.

Week-by-week bars, a cumulative line, and a breakdown of HIGH versus the rest. Best and worst weeks, a season table, and (on the 2025 demo) a separate Over/Under section.

2026 Track Record grades HIGH by the Tuesday {HIGH_GAP:g}-point rule. There is no medium bucket. 2026 Track Record does not include totals.
        """)

    with st.expander("What is the Season Totals page?"):
        st.markdown("""
The Season Totals page leads with the **high-confidence** win record on held-out
seasons (projection at least 1 win off the posted number). Every team still gets
a projection; only those high-confidence rows are highlighted with a check mark.

The footnote states once that the all-team projection does not beat the posted
win total on average, and once that the one-sided 95% Wilson lower bound on
high confidence sits under the 52.4% bar.

How the number is built sits in **How Season Totals are built** below.
        """)

    with st.expander("What is the Weekly Fantasy page?"):
        st.markdown("""
Weekly half-PPR projections for QB, RB, WR, and TE.

The page currently opens on the latest published file: the **2025 Week 17** demo in the 2026 layout. Rankings are simple by default; **More info** reveals projected yards and matchup context when that file has them. **2026 Week 1** rankings land once that file is published. Older 2025 weeks are a demo from the previous weekly model.

Out, Doubtful, IR, inactives, and anyone who did not play are removed from the board. Questionable stays until box scores exist.

Search by player. Older demo weeks also show extra columns (team EPA, implied total, health, some stat projections). Actual points fill in after the games.

How those files are built sits in **How weekly fantasy projections are built** below.
        """)

    with st.expander("What is the DFS Optimizer page?"):
        st.markdown("""
A DraftKings NFL Classic lineup builder. Upload the salary CSV for the contest you want. The page uses a published direct-DK projection file when one exists, or a CSV you upload.

Classic roster: 1 QB, 2 RB, 3 WR, 1 TE, 1 FLEX, 1 DST, $50,000 salary cap. OUT, IR, Doubtful, PUP, SUSP, and NFI players are excluded. Questionable players stay eligible. DST uses opponent implied total when a game line exists, otherwise DraftKings average.

This site does not generate DFS projections. Those files come from a private producer and have to pass the same release checks as the other products. No 2026 Week 1 projection file is published yet.

The optimizer picks the highest projected legal lineup under your locks and exclusions. Historical diagnostics have not shown a projection edge. Treat the output as research, not a performance claim. Check late news and the DraftKings import preview before you enter.

How the file contract works sits in **How the DFS optimizer works** below.
        """)

    with st.expander("What is the Anytime TDs page?"):
        st.markdown("""
A 2025 weeks 10-17 board of rushing and receiving anytime-TD probabilities
versus the book. Priced players only, sorted by our P(TD). Passing TDs are out.
Not even money: a typical quote is around one in five, so misses will outnumber
hits. For fun. Not a proven edge. Bet responsibly.

Over full 2025 the sportsbooks were still about 0.08% more accurate. On these
eight demo weeks our numbers were closer in 5; that is not a betting record.
How the number is built sits in **How the Anytime TD demo works** below.
        """)

    with st.expander("What is the Draft Board page?"):
        st.markdown("""
A **pre-season comparison table** for 2026, separate from Weekly Fantasy. The universe is fixed: 24 QBs, 60 RBs, 72 WRs, 24 TEs. Each row puts draft price and positional rank next to **Model Proj**. Use **Draft price** to switch Sleeper ADP (the default), ESPN ADP, Yahoo ADP, or **Model Draft Rank** for the same 180 players. Sleeper's current season projection is shown when the player record matches. Each projection also has a gap versus draft-price rank at that position. **Model Draft Rank** fills the draft-price column with Model Proj after subtracting a replacement starter at each position (QB14, RB30, WR36, TE14), shown as 1.0, 2.0, and so on. Position Rank and both gaps stay on Sleeper ADP.

**What the gap is.** Position Rank minus that projection's position rank. Positive means the projection ranks him above his draft cost; negative means below. It is arithmetic between two ranks on the same row, never a recommendation.

**How good is the number?** On 2021-2025 Model Proj scored .7101 pairwise versus ADP's .6965, MAE 49.31 versus 51.75, and beat ADP ordering in 5 of 6 seasons (it lost 2020). That comparison is vs Sleeper ADP. It is **not live-validated**. The first live test is the 2026 season.

Model Proj values are frozen until the planned dated early-September public-information snapshot. **Sleeper ADP, ESPN ADP, Yahoo ADP, and Sleeper Proj refresh daily; their positional ranks, Sleeper Gap, and Model Gap recalculate from each successful pull.**

The two talent columns are described further down this page. They are descriptive context and feed no other column.

Yahoo does not price every one of the 180 players. Those ADP cells stay blank and sort to the bottom. They are never filled from Sleeper or ESPN.

Use **Draft price**, **Position**, **Player search**, **Sort by**, and **Order**. No-data rows always sort to the bottom. **Show projection and talent detail** is on by default. On a phone the board shows player, position, ADP, rank, both gaps, and NFL Talent Score. The CSV download always contains all thirteen columns.
        """)

    with st.expander("What is the Rookie Board page?"):
        st.markdown("""
Drafted rookies from the 2024, 2025, and 2026 classes. **Hit probability** is the share of historical players with a similar profile who had at least one startable season in their first three years (top-24 for RB/WR, top-12 for QB/TE, season-total half-PPR). That is a best-of-three-years outcome, not a per-season rate.

Three versions sit side by side: draft capital only, college production and athletic testing only, and both. They land close together. At this sample, college production and testing added no measured edge beyond draft position. Backtested on the 2019-2023 classes, not live-validated.

Beside those sit rookie-year **season-total projections** for RB, WR, and TE, next to Sleeper when Sleeper has one. Rookie QBs show no projection: a rookie QB season hinges on whether he starts, which the features cannot see.

Collapsed lists of **college players who are not in this year's rookie class** use the same College Talent instrument. Most are still in college. They appear on no rookie board and say nothing about whether any of them will be drafted.
        """)

    with st.expander("What is the Film Room page?"):
        st.markdown("""
Short analysis videos, the site walkthrough, and the League History walkthrough. Choose a section, then an episode. **📖 Full breakdown** opens the context the short couldn't fit.
        """)

    with st.expander("What is the League History page?"):
        st.markdown("""
Choose Sleeper, ESPN, Yahoo, or CBS, paste the league ID, and hit Load. Sleeper IDs come from `sleeper.com/leagues/{ID}/league`; ESPN also needs the most recent season shown in the league URL. Yahoo IDs are the number after `/f1/` and also need that season. CBS IDs are the subdomain of `{ID}.football.cbssports.com` and also need that season. Private ESPN leagues need the SWID and espn_s2 cookie values from a signed-in browser session. Private Yahoo leagues need the Y and T cookie values. CBS leagues always need the signed-in access token. The page pulls standings, drafts, weekly scores, and a few chart-first views: Draft & Roster Insights, All-Time Leaderboard, Hall of Fame, Rivalries, Report Cards, and Consistency & Luck.

**Finding the ID:** In the Sleeper phone app, open league settings, choose **General**, and use **Copy League ID** at the bottom; on a computer, copy the number at the end of the league URL. In the ESPN Fantasy phone app, open **League → League Info**; on a computer, copy the digits after `leagueId=` in the league URL. Your League Manager must enable ESPN's **viewable to public** setting for public imports. ESPN keeps membership invite-only. For Yahoo, copy the digits after `/f1/` in `football.fantasysports.yahoo.com`; a URL like `/2025/f1/123456` is season 2025 and league ID 123456. Ask the commissioner to make a Yahoo league publicly viewable for the public importer. For CBS, copy the subdomain of `{ID}.football.cbssports.com`; a URL like `https://cbshelp.football.cbssports.com` is league ID `cbshelp`. CBS has no public-view importer.

**Private ESPN, Yahoo, or CBS:** Get the League ID on either device, but retrieve the session values from a signed-in desktop browser. Chrome and Edge show cookies under **Developer Tools → Application → Storage → Cookies**; Firefox uses **Developer Tools → Storage → Cookies**. For CBS, copy the **Authorization** header from an `/api/league` Network request, or the `var token` value from the page source. Normal iPhone and Android browser menus do not expose these values. Treat them like passwords and never paste them into chat.

First load is usually a few seconds per Sleeper season and 10-25 seconds per ESPN, Yahoo, or CBS season. Public results are cached for an hour. Private ESPN, Yahoo, and CBS results stay only in the current browser session; credential fields clear after a successful load and the session values are never logged or shared-cached. A brand-new 2026 league can load successfully with empty tabs until it has a draft or scored weeks. The Film Room walkthrough shows Sleeper and ESPN; Yahoo and CBS are on the live page and are not in that video. Filter by season or view all-time. Info icons on the cards explain each statistic. This page is your league's history, not a prediction model.
        """)
        film_room_page = nav_registry.PAGES.get("film-room")
        if film_room_page is not None:
            st.page_link(
                film_room_page,
                label="Watch the League History walkthrough",
                icon=":material/play_circle:",
                width="stretch",
                query_params={"video": LATEST_LEAGUE_HISTORY_VIDEO_SLUG},
            )

    with st.expander("What is the LLM agent and what does it do?"):
        st.markdown(f"""
The agent sat on top of the prediction models using LlamaIndex and Anthropic's Claude API.

**Paused as of August 2026.** The agent's line-movement tool was never connected to
a real market feed. It returned hardcoded example values, and the one cached week it
produced stated those as if they were observed sharp-money and line-movement figures. I've
taken that cached analysis down, disabled the weekly agent run, and the site now refuses to
render any market claim that can't prove where it came from.

The colored High / Medium / Skip buttons are not on the game cards right now. What you see
on **2026** Weekly Predictions is **Tuesday HIGH**: a green highlight when the model
disagrees with the Tuesday market snapshot by {HIGH_GAP:g}+ points and the live line still does. The
**2025 demo** weeks still show **Model Consensus** (HIGH / MED / PASS).

When an approved agent artifact is present again, High means the model edge is strong and outside signals lined up, Medium means mixed signals, and Skip means pass.
        """)

    st.divider()
    help_models.render_rundowns()

    st.divider()
    st.subheader("🏆 Fantasy Projections")

    with st.expander("How do the fantasy projections work?"):
        st.markdown("""
The Weekly Fantasy page uses a separate system from the betting model. The DFS Optimizer is a third system: Classic DK points, not half-PPR.

**2025 demo (weeks 10-17 on this page).** Four per-position XGBoost models trained on 2020-2024, with 2025 held out. Walkthrough only. Not the 2026 live weekly model.

**2026 live, starting Week 1.** One LightGBM for all four positions. Same scoring: 0.5 per reception, yards and touchdowns as usual. Last four played games plus this week's closing line, opponent, and injury report as of that game's kickoff. The first live week is 2026 Week 1.

The models are rebuilt in the offseason as more data lands.
        """)

    with st.expander("How accurate are the fantasy projections?"):
        st.markdown("""
**2025 demo.** Those weeks were scored against a simple 3-week rolling average, on the previous per-position XGBoost system:

| Position | Model MAE | Baseline MAE | Improvement |
|----------|-----------|--------------|-------------|
| QB | 7.0 pts | 7.5 pts | Better |
| RB | 4.5 pts | 4.6 pts | Better |
| WR | 3.9 pts | 4.1 pts | Better |
| TE | 3.2 pts | 3.5 pts | Better |

MAE is the average number of points the projection was off by. For WR, about 3.9 points. Any individual week can be much higher or lower. Treat the numbers as a ranking tool, not a precise point forecast.

**2026 live holdout** (train 2021-2024, grade Sleeper's top 180 each week, n=3,060). MAE **4.999** vs Sleeper **5.188**. Rank correlation **0.395** vs Sleeper **0.402**. Walk-forward rank 2023-2025: **0.394**. Point error is a bit better. Ordering is a bit worse. That is not a claim it beats Sleeper. No 2026 week has been graded yet.
        """)

    with st.expander("What are the prop stat columns?"):
        st.markdown("""
These extra stat columns appear on the **2025 demo weeks**. Week 17 is the 2026 layout preview: rankings start with a four-column simple view, and **More info** reveals the available stat and matchup context in the same table. Its frozen source CSV is unchanged. 2026 live weeks show the detailed toggle when their release includes those fields.

On the 2026 preview and live weekly layout, enable **More info** to see the available passing, rushing, and receiving-yard estimates beside the fantasy rankings. You can compare them with sportsbook player-prop over/under lines. They are model estimates, not sportsbook lines or betting recommendations.

Eight separate XGBoost models, trained on the same data with each stat as the target:

| Column | Position | What it predicts |
|--------|----------|-----------------|
| Proj Pass Yds | QB | Passing yards |
| Proj Rush Yds | QB / RB | Rushing yards |
| Proj Rec Yds | RB / WR / TE | Receiving yards |
| Proj Receptions | WR / TE | Number of receptions |

Useful as a rough look at player props. They are **independent** models, so they will not add up to the fantasy-point total. QB passing yards has the highest error (about 70 yards). RB and TE receiving yards are the tightest (about 10-14 yards MAE).
        """)

    with st.expander("What do the column headers mean?"):
        st.markdown("""
**Player:** name and NFL team.

**Opponent:** this week's opponent. `@` is away, `vs` is home.

**Proj Pts:** projected half-PPR points. 0.5 per reception, 1 per 10 rush or receiving yards, 6 per TD.

**Off EPA:** the team's offensive efficiency over the last 4 games, Expected Points Added per play. Higher is better. Legacy 2025 demo weeks only; it is not in the Week 17 preview or 2026+ layout.

**EPA Rank:** where that offense ranks among 32 teams this season. Green to red.

**Team Total:** Vegas implied team total, how many points Vegas expects this team to score.

**Health:** injury report. ✅ Healthy · 🟡 Questionable. Out, Doubtful, IR, and anyone who did not play are removed from the board.

**Actual Pts / Actual [stat]:** fills in after the game for players who played.
        """)

    with st.expander("What is Off EPA?"):
        st.markdown("""
**Off EPA** is Offensive Expected Points Added per play, averaged over the team's last 4 games. It appears only in the legacy 2025 demo layout, not the Week 17 preview or 2026+ layout.

EPA measures how much each play moves the needle toward scoring. A 5-yard gain on 3rd and 4 is worth more than a 5-yard gain on 1st and 10, because it accounts for down, distance, and field position.

- **Positive (e.g. +0.15):** efficient recently
- **Near zero (e.g. +0.01):** average
- **Negative (e.g. -0.12):** struggling

League average hovers near 0. Above +0.10 is strong, below -0.10 is poor. Players on efficient offenses tend to see more opportunities in good game scripts. It is one of the stronger predictors in the 2025 demo models.
        """)

    with st.expander("How often do fantasy projections update?"):
        st.markdown("""
Fantasy projections are generated separately from the weekly betting GitHub Action. That job only papermills the spread and totals notebooks. Weekly fantasy is not on that Tuesday cron.

A 2026 Fantasy release is an immutable revision: the first build precedes kickoff, and each later revision copies every started game's rows exactly while recomputing only future games. Thursday, Sunday, and Monday games therefore lock on different clocks. Actual stats fill in after each game, pulling live from nflreadpy and caching for 1 hour.

If you're looking at a past week, the actuals shown are the real NFL stats for that game.
        """)

    st.divider()
    st.subheader("🧮 NFL Talent Score & College Talent Score")

    with st.expander("What are the two score columns on the Draft Board?"):
        st.markdown("""
The Draft Board carries two context columns I build myself, answering two different questions.

**The NFL Talent Score** is my model-based estimate of what a player does with each opportunity (each carry, route, or throw), separated from his situation where that separation is statistically possible. It is not a summary of his production, and models can be wrong. Volume is excluded by design: how often a player is used tells you about his coach's plans, not his per-play skill. Every position reads its own dedicated build, scored against qualified starters at that position. A player below his position's volume floor is left **blank** rather than quietly placed on another position's scale.

**The College Talent Score** is a college-production read for 2026 rookies at all four positions (QB, RB, WR and TE), each from its own dedicated college build, scaled against past prospects at that position who reached the NFL. It describes what a prospect did in college; it does not claim to predict NFL careers or fantasy outcomes.

**Two limits on the college side, stated plainly.** There is no strength-of-schedule adjustment: production against a weaker opponent counts exactly the same as production against a stronger one, which is why several of the highest college scores belong to small-school players the draft market rated far lower. And the underlying data covers FBS only, so a prospect from a smaller division can never be scored. That blank is by construction, not a missing lookup.

**They are two different scales.** The NFL column ranks NFL players against NFL players; the college column ranks prospects against past prospects. A 90 in one is not a 90 in the other, and neither feeds any other number on this board.
        """)

    with st.expander("How the talent scores are built (and what they don't measure)"):
        st.markdown("""
There are eight builds behind these two columns, one for each of NFL and college at each of the four positions. Each takes a small set of per-opportunity measures I call facets (broken tackles per carry, yards per route run, completion rate versus expectation, and so on), scores every player against his own position in his own season, and then shrinks each measure toward the position average according to how much data sits behind it. A thin sample gets pulled toward the middle rather than being trusted at face value.

That shrinkage has a consequence worth stating: **a facet measured on very few plays contributes far less than its nominal weight suggests.** Contested catches are the clearest case. A tight end sees a handful of them a season, so that facet ends up carrying a few percent of the score no matter what weight I assign it. I measured this before reading any results, and where I tried to compensate by raising the weight, the players the facet exists to reward generally got *worse*, not better. So the weights ship as ratified.

Quarterbacks are the asterisk on the NFL side: one starter per team means a QB's situation cannot be separated from him, so QB scores ship **unadjusted**, a different kind of estimate under the same header. The QB build does now measure performance under pressure, though on a small enough sample that it contributes little. A consequence I have not engineered away: an immobile quarterback cannot score well here, because designed rushing carries a quarter of the composite.

Recent seasons count more, on a decay I chose and wrote down rather than fitted. Scores are clipped to a 50-99 display range (40-99 for college quarterbacks), so **50 is the floor of the display, not a league-average player**. Ranks are a more reliable read than any single number.

These columns are context only. A test found that efficiency measures like these do not predict where the draft market misprices players, so they never combine with the projections, the ranks, or the gap columns anywhere on the board. The college instruments in particular were each measured against NFL outcomes and each came back **dead**. They ship as description of college production, and nothing more.

The full write-up covering every design choice, the admission gates, and where it fails lives in my research notes.
        """)

    st.divider()
    st.subheader("🔧 Behind the Scenes")

    with st.expander("What data does the site use?"):
        st.markdown("""
Play-by-play and schedule data come from nflreadpy, going back far enough to build each model's training window (2018 for the 2026 spread model, 2014 for older demo files).

Injury reports feed availability: Out and Doubtful players reduce a team's talent and lineup features. The All-Pro CSV (1997-2025) is a custom roster-talent file, updated manually each January.

Posted win totals on Season Totals are a sportsbook snapshot with an as-of date on that page. Sleeper ADP, ESPN ADP, Yahoo ADP, and Sleeper projections on the Draft Board refresh daily. DFS Optimizer projections are checked producer artifacts, not generated on this site. The LLM agent is paused (August 2026).
        """)

    with st.expander("Is this financial advice?"):
        st.markdown("""
No. This is a personal data science project. I built it to see whether a machine learning model can find a consistent edge against the spread.

Nothing on this site should be taken as betting or financial advice. Sports betting involves real financial risk. Always bet responsibly.
        """)

    with st.container(border=True, horizontal_alignment="center"):
        st.caption(
            "Not financial advice. Sports betting involves real risk. Bet responsibly.",
            text_alignment="center",
        )
        st.markdown("Built by **Joseph Schoenbaum**", text_alignment="center")
        st.link_button(
            "View methodology and code",
            "https://github.com/joscho11/JoSchoAnalytics",
            icon=":material/code:",
            type="tertiary",
        )
