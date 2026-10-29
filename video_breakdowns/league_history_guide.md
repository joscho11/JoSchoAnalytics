# How to see your league's history

*Recorded August 20, 2026 · Sleeper and ESPN walkthrough; current steps below*

**The one-liner:** Load a Sleeper or ESPN league once, then explore its drafts, transactions, standings, titles, rivalries, scoring, and luck across every available season. The live page also imports Yahoo and CBS; this video does not show them.

---

## 1. Open the page

On the site, choose **More → League History**. The video selects Sleeper or ESPN, enters the league ID, then **Load league history**. The live page also has Yahoo and CBS.

- **Sleeper:** Copy the long number from `sleeper.com/leagues/{ID}/league`, or use **League settings → General → Copy League ID** in the phone app.
- **ESPN:** Copy the digits after `leagueId=` and enter the latest season shown in the league URL. A private league also needs the `SWID` and `espn_s2` values from a signed-in desktop browser.

The first import can take a few seconds per season. Public results are cached for an hour. Private ESPN credentials are cleared after a successful load and are not shared-cached.

---

## 2. Explore the archive

The page organizes the record into six views:

- **Draft & Roster Insights:** historical lineup production, values, transactions, and draft tendencies.
- **All-Time Leaderboard:** results and scoring compared with each week's league average.
- **Hall of Fame:** the league's record games and biggest extremes.
- **Rivalries:** head-to-head records, matchup exploration, and generated weekly slates.
- **Report Cards:** one manager's winning, scoring, and consistency over time.
- **Consistency & Luck:** scoring volatility and actual wins versus all-play expectation.

Use the season filter for one year or select all-time for the full record. The page works on a phone, but the wider charts and tables are easier to compare on a computer.

---

## 3. Read it as history, not a forecast

League History describes what happened. It does not rank the best manager for you, predict the next season, or turn draft tendencies into recommendations. The value is having the full record in one place so those arguments can start from the same evidence.

---

## 4. Not in the video

Yahoo and CBS imports landed after this walkthrough. Both use the same six views. Public leagues use the number after `/f1/` plus the season in the URL. Private leagues need the Y and T cookie values from a signed-in desktop browser, the same class as ESPN's SWID and espn_s2. Yahoo Best Values still has no FAAB or trade ledger. A brand-new 2026 league can load with empty tabs until it has a draft or scored weeks. Yahoo ADP lives on the Draft Board, not here.

For CBS, use the subdomain of `{ID}.football.cbssports.com` as the league ID, choose the season, and supply the signed-in access token. CBS has no public-view importer. Retrieve credentials on a signed-in desktop browser; never paste them into chat. Private credentials stay in the current browser session and are not logged or shared-cached.

[Open League History](/league-history) · [Current import help](/help?help_topic=Site+Guide&guide=league-history-guide)
