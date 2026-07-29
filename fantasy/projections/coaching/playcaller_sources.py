"""SOURCE OF RECORD for ACTUAL offensive play-caller attribution, 2018-2026.

Every row below was transcribed from a named, dated, publicly citable source that explicitly
identifies who CALLED OFFENSIVE PLAYS -- not who held the coordinator title. Nominal OC is kept
elsewhere (`coach_identity_team_season.csv`) as staff-continuity metadata only and is NEVER
promoted to play-caller without evidence.

CONFIDENCE LEVELS
  high      the source names this person as the team's play-caller for this season.
  medium    the source establishes the play-caller is NOT the head coach for this season (e.g. a
            roundup stating "14 of 32 head coaches call their own plays" and naming those 14), and
            the nominal OC is taken as the complement. Documented inference, disclosed as such.
  conflict  two sources disagree -> routed to UNKNOWN, never silently resolved.
  (absent)  no evidence -> the team-season does not appear here at all and is UNKNOWN downstream.

ROLE IS NEVER TRUSTED FROM THE SOURCE. Several sources mislabel roles (Fantasy Index 2026 calls
Sean McVay an "offensive coordinator"; Yardbarker 2022 calls Luke Getsy a "head coach"). The
builder derives `play_caller_role` by comparing the play-caller against the authoritative nflverse
head-coach table, and flags every source/derived disagreement.
"""

SOURCES = {
    "espn2017": dict(
        url="https://www.espn.com/nfl/story/_/page/32for32x17115/"
            "nfl-2017-playcallers-all-32-nfl-teams-how-their-offense-ranks",
        date="2017-11-15", publisher="ESPN",
        note="'The playcallers for all 32 teams and where their offenses rank' — all 32, 2017."),
    "fantasyindex2018": dict(
        url="https://fantasyindex.com/2018/06/28/ian-allan/offensive-coaches",
        date="2018-06-28", publisher="Fantasy Index",
        note="'Offensive coaches - Ranking the play callers 1 thru 32' — all 32, 2018. Every "
             "head-coach caller here also appears in the independent ESPN 2018-07-12 list."),
    "cbs2017kc": dict(
        url="https://www.cbssports.com/nfl/news/"
            "andy-reid-reportedly-cedes-play-calling-duties-to-offensive-coordinator-matt-nagy/",
        date="2017-12-03", publisher="CBS Sports",
        note="Reid handed play-calling to Nagy for the Week 13 Jets game, retaining oversight."),
    "newsweek2018cle": dict(
        url="https://www.newsweek.com/"
            "hue-jackson-todd-haley-fired-cleveland-browns-midway-through-season-1192594",
        date="2018-10-29", publisher="Newsweek",
        note="Jackson and OC Haley fired after Week 8; Freddie Kitchens promoted and called "
             "plays for the remainder of the season."),
    "espn2018hc": dict(
        url="https://www.espn.com/blog/nflnation/post/_/id/277514/"
            "finding-the-next-sean-mcvay-head-coaches-who-call-offensive-plays",
        date="2018-07-12", publisher="ESPN",
        note="Names all 14 head coaches calling their own plays in 2018; states this is up from "
             "11 of 32 in 2017. Also names Ken Whisenhunt as the Chargers' play-caller."),
    "yardbarker2020": dict(
        url="https://www.yardbarker.com/nfl/articles/"
            "ranking_the_offensive_play_callers_from_every_nfl_team/s1__32555903",
        date="2020-10-22", publisher="Yardbarker", note="All 32 teams, 2020 season."),
    "yardbarker2021": dict(
        url="https://www.yardbarker.com/nfl/articles/"
            "ranking_the_offensive_play_caller_for_each_nfl_team/s1__35857394",
        date="2021-01-01", publisher="Yardbarker", note="All 32 teams, 2021 season."),
    "yardbarker2022": dict(
        url="https://www.yardbarker.com/nfl/articles/"
            "ranking_the_offensive_play_caller_for_each_nfl_team/s1__37978942",
        date="2022-12-05", publisher="Yardbarker", note="All 32 teams, 2022 season."),
    "espn2023": dict(
        url="https://www.espn.com/nfl/story/_/id/38108724/"
            "key-intel-all-32-nfl-playcallers-including-mike-mccarthy",
        date="2023-08-01", publisher="ESPN", note="All 32 playcallers, 2023 season."),
    "espn2024": dict(
        url="https://www.espn.com/nfl/story/_/id/41018846/"
            "nfl-playcallers-32-teams-mike-mcdaniel-sean-mcvay-nathaniel-hackett",
        date="2024-08-01", publisher="ESPN", note="All 32 playcallers, 2024 season."),
    "espn2025": dict(
        url="https://www.espn.com/nfl/story/_/id/46137832/"
            "nfl-playcallers-32-teams-mike-mcdaniel-sean-mcvay-brian-schottenheimer",
        date="2025-08-01", publisher="ESPN", note="All 32 playcallers, 2025 season."),
    "fantasyindex2026": dict(
        url="https://fantasyindex.com/2026/02/20/around-the-nfl/ranking-the-offensive-play-callers",
        date="2026-02-20", publisher="Fantasy Index",
        note="All 32 play-callers, 2026 season. Role labels unreliable; identity used, role derived."),
    "cbs2022phi": dict(
        url="https://www.cbssports.com/nfl/news/"
            "eagles-shane-steichen-takes-over-full-time-play-calling-duties-under-nick-sirianni-for-2022",
        date="2022-01-01", publisher="CBS Sports",
        note="Reports Steichen took full-time play-calling for 2022 -- CONFLICTS with Yardbarker 2022."),
}

# -------------------------------------------------------- 2017 (ESPN 32-team playcaller article)
PC_2017 = {
    "NE": "Josh McDaniels", "NO": "Sean Payton", "DAL": "Scott Linehan", "PHI": "Doug Pederson",
    "KC": "Andy Reid", "ATL": "Steve Sarkisian", "LV": "Todd Downing", "LA": "Sean McVay",
    "GB": "Mike McCarthy", "PIT": "Todd Haley", "WAS": "Jay Gruden", "SEA": "Darrell Bevell",
    "MIN": "Pat Shurmur", "CAR": "Mike Shula", "TB": "Dirk Koetter", "LAC": "Ken Whisenhunt",
    "JAX": "Nathaniel Hackett", "DET": "Jim Bob Cooter", "TEN": "Terry Robiskie",
    "HOU": "Bill O'Brien", "NYG": "Mike Sullivan", "BUF": "Rick Dennison", "CIN": "Bill Lazor",
    "BAL": "Marty Mornhinweg", "MIA": "Adam Gase", "DEN": "Mike McCoy", "NYJ": "John Morton",
    "ARI": "Bruce Arians", "CLE": "Hue Jackson", "IND": "Rob Chudzinski",
    "SF": "Kyle Shanahan", "CHI": "Dowell Loggains",
}

# ------------------------------------------------- 2018 (Fantasy Index 32-team play-caller rank)
# Supersedes the earlier HC-only extraction. The 2018-07-12 ESPN piece named 14 head-coach callers;
# every one of them appears here as the caller, so the two sources corroborate rather than conflict.
# Role labels in the source are NOT used (it lists Frank Reich as "OC" when he was Indianapolis's
# head coach) — role is derived from the nflverse head-coach table downstream.
PC_2018 = {
    "LA": "Sean McVay", "SF": "Kyle Shanahan", "NO": "Sean Payton", "KC": "Andy Reid",
    "NE": "Josh McDaniels", "PHI": "Doug Pederson", "WAS": "Jay Gruden", "GB": "Mike McCarthy",
    "NYG": "Pat Shurmur", "LAC": "Ken Whisenhunt", "HOU": "Bill O'Brien", "IND": "Frank Reich",
    "CHI": "Matt Nagy", "ARI": "Mike McCoy", "LV": "Jon Gruden", "DET": "Jim Bob Cooter",
    "TEN": "Matt LaFleur", "PIT": "Randy Fichtner", "MIN": "John DeFilippo",
    "DAL": "Scott Linehan", "BAL": "Marty Mornhinweg", "DEN": "Bill Musgrave",
    "JAX": "Nathaniel Hackett", "TB": "Dirk Koetter", "MIA": "Adam Gase", "BUF": "Brian Daboll",
    "CIN": "Bill Lazor", "CAR": "Norv Turner", "SEA": "Brian Schottenheimer",
    "NYJ": "Jeremy Bates", "ATL": "Steve Sarkisian",
    # CLE 2018 is a documented midseason split (Haley -> Kitchens), handled in MIDSEASON_CHANGES
}

# ============================================================================================
# TEAM-BY-TEAM PASS over the 2014/2015/2016/2019 rows (Joseph authorised 2026-07-28).
# No compiled 32-team table exists for these seasons, so each row below carries its OWN source.
# Every entry was confirmed by reading the article, not a search-result summary.
# ============================================================================================
PC_PARTIAL = {
    # --- 2014 -------------------------------------------------------------------------------
    (2014, "WAS"): ("Jay Gruden", "espn2017was"),
    (2014, "SEA"): ("Darrell Bevell", "espn2015sb49"),
    (2014, "HOU"): ("Bill O'Brien", "espn2016hou"),
    (2014, "CAR"): ("Mike Shula", "espn2015car"),
    # --- 2015 -------------------------------------------------------------------------------
    (2015, "WAS"): ("Sean McVay", "espn2017was"),
    (2015, "SEA"): ("Darrell Bevell", "espn2018sea"),
    (2015, "HOU"): ("George Godsey", "espn2016hou"),
    (2015, "ARI"): ("Bruce Arians", "espn2016ari"),
    (2015, "CAR"): ("Mike Shula", "espn2015car"),
    (2015, "DAL"): ("Scott Linehan", "ringer2019dal_linehan"),
    (2014, "GB"): ("Mike McCarthy", "fox2015gb"),
    (2014, "DEN"): ("Adam Gase", "espn2014den"),
    (2014, "MIN"): ("Norv Turner", "vikings2016min"),
    (2014, "BAL"): ("Gary Kubiak", "balsun2014bal"),
    (2014, "TEN"): ("Ken Whisenhunt", "nfl2014ten"),
    (2014, "MIA"): ("Bill Lazor", "espn2015mia"),
    (2014, "DET"): ("Joe Lombardi", "cbs2014det"),
    (2014, "BUF"): ("Nathaniel Hackett", "espn2016jax"),
    (2015, "MIN"): ("Norv Turner", "vikings2016min"),
    (2015, "DEN"): ("Gary Kubiak", "espn2015den"),
    (2015, "BAL"): ("Marc Trestman", "ravens2016bal"),
    (2015, "TB"): ("Dirk Koetter", "bucs2016tb"),
    (2016, "TB"): ("Dirk Koetter", "bucs2016tb"),
    (2016, "CLE"): ("Hue Jackson", "nbc2016cle"),
    (2016, "GB"): ("Mike McCarthy", "nfl2016gb"),
    (2016, "PHI"): ("Doug Pederson", "inq2021phi"),
    (2016, "SF"): ("Chip Kelly", "nbc2016sf"),
    (2014, "NO"): ("Sean Payton", "espn2016nopc"),
    (2014, "IND"): ("Pep Hamilton", "espn2016ind"),
    (2016, "IND"): ("Rob Chudzinski", "espn2016ind"),
    (2015, "NYJ"): ("Chan Gailey", "espn2017nyj"),
    (2016, "NYJ"): ("Chan Gailey", "espn2017nyj"),
    (2016, "LA"): ("Rob Boras", "yahoo2015la"),
    (2014, "DAL"): ("Scott Linehan", "nfl2014dal"),
    (2015, "PHI"): ("Chip Kelly", "espn2015phi"),
    (2014, "TB"): ("Marcus Arroyo", "si2014tb"),
    (2015, "BUF"): ("Greg Roman", "espn2016buf"),
    (2016, "MIA"): ("Adam Gase", "nbc2016mia"),
    (2016, "TEN"): ("Terry Robiskie", "nfl2016ten"),
    (2014, "CIN"): ("Hue Jackson", "nfl2014cin"),
    (2014, "KC"): ("Andy Reid", "espn2017kc"),
    (2015, "KC"): ("Andy Reid", "espn2017kc"),
    (2016, "KC"): ("Andy Reid", "espn2017kc"),
    (2015, "SF"): ("Geep Chryst", "fox2015sf"),
    (2014, "CLE"): ("Kyle Shanahan", "cle2014"),
    (2014, "NE"): ("Josh McDaniels", "espn2015ne"),
    (2015, "NE"): ("Josh McDaniels", "ne2016afc"),
    (2016, "NE"): ("Josh McDaniels", "espn2017ne"),
    (2014, "PHI"): ("Chip Kelly", "espn2014phi"),
    (2014, "NYJ"): ("Marty Mornhinweg", "nbc2014nyj"),
    (2014, "ATL"): ("Dirk Koetter", "espn2014atl"),
    (2015, "CHI"): ("Adam Gase", "espn2015chi"),
    (2016, "DET"): ("Jim Bob Cooter", "espn2016det"),
    (2014, "LA"): ("Brian Schottenheimer", "nbc2014la"),
    (2014, "NYG"): ("Ben McAdoo", "giants2014nyg"),
    (2015, "NYG"): ("Ben McAdoo", "giants2014nyg"),
    (2016, "NYG"): ("Ben McAdoo", "espn2017nygsull"),
    (2014, "LAC"): ("Frank Reich", "fox2016lac"),
    (2015, "LAC"): ("Frank Reich", "fox2016lac"),
    (2015, "NO"): ("Sean Payton", "espn2016nopc"),
    (2015, "JAX"): ("Greg Olson", "espn2016jax"),
    (2015, "ATL"): ("Kyle Shanahan", "nfl2015atl"),
    (2016, "ATL"): ("Kyle Shanahan", "nfl2015atl"),
    (2015, "LV"): ("Bill Musgrave", "cbs2017lv"),
    (2016, "LV"): ("Bill Musgrave", "cbs2017lv"),
    (2014, "PIT"): ("Todd Haley", "espn2018pit"),
    (2015, "PIT"): ("Todd Haley", "espn2018pit"),
    (2016, "PIT"): ("Todd Haley", "espn2018pit"),
    # --- 2016 -------------------------------------------------------------------------------
    (2016, "WAS"): ("Sean McVay", "espn2017was"),
    (2016, "SEA"): ("Darrell Bevell", "espn2018sea"),
    (2016, "ARI"): ("Bruce Arians", "espn2016ari"),
    (2016, "CAR"): ("Mike Shula", "espn2015car"),
    (2016, "DAL"): ("Scott Linehan", "ringer2019dal_linehan"),
    # --- 2019 -------------------------------------------------------------------------------
    (2019, "CLE"): ("Freddie Kitchens", "espn2019cle"),
    (2019, "GB"): ("Matt LaFleur", "espn2019gb"),
    (2019, "DAL"): ("Kellen Moore", "ringer2019dal"),
    (2019, "TB"): ("Byron Leftwich", "tampabay2019tb"),
    (2019, "PIT"): ("Randy Fichtner", "steelersdepot2019pit"),
    (2019, "NYJ"): ("Adam Gase", "cbs2020nyj"),
    (2019, "MIN"): ("Kevin Stefanski", "nfl2019min"),
    (2019, "DEN"): ("Rich Scangarello", "si2019den"),
    (2019, "LA"): ("Sean McVay", "nbcla2019la"),
    (2019, "HOU"): ("Bill O'Brien", "espn2020hou"),
    (2019, "CHI"): ("Matt Nagy", "espn2020chi"),
    (2019, "PHI"): ("Doug Pederson", "inq2020phi"),
    (2019, "KC"): ("Andy Reid", "forbes2026kc"),
    (2019, "SF"): ("Kyle Shanahan", "espn2020sf"),
    (2019, "LV"): ("Jon Gruden", "nbc2021lv"),
    (2019, "SEA"): ("Brian Schottenheimer", "sea2019two"),
    (2019, "CAR"): ("Norv Turner", "espn2019car"),
    (2019, "JAX"): ("John DeFilippo", "si2020jax"),
    (2019, "IND"): ("Frank Reich", "nbcp2021ind"),
    (2019, "CIN"): ("Zac Taylor", "espn2020cin"),
    (2019, "MIA"): ("Chad O'Shea", "espn2019mia"),
    (2019, "TEN"): ("Arthur Smith", "cbs2020ten"),
}

PARTIAL_SOURCES = {
    "espn2017was": dict(
        url="https://www.espn.com/blog/washington-commanders/post/_/id/29729/"
            "without-sean-mcvay-redskins-coach-jay-gruden-could-return-to-calling-plays",
        date="2017-01-12", publisher="ESPN",
        evidence="Gruden 'called plays his first season as the Redskins' head coach' (2014); "
                 "for 'the past two seasons' (2015 and 2016) 'it was McVay who called the plays'.",
        supports="2014, 2015, 2016"),
    "espn2015sb49": dict(
        url="https://www.espn.com/nfl/playoffs/2014/story/_/id/12266535/"
            "super-bowl-xlix-darrell-bevell-seattle-seahawks-play-call-made-kill-clock",
        date="2015-02-02", publisher="ESPN",
        evidence="Bevell describes the Super Bowl XLIX goal-line call as his own play call, "
                 "establishing him as Seattle's offensive play-caller for the 2014 season.",
        supports="2014"),
    "espn2018sea": dict(
        url="https://www.espn.com/blog/nflnation/post/_/id/266192/"
            "darrell-bevell-had-successful-run-but-super-bowl-call-is-his-seahawks-legacy",
        date="2018-01-11", publisher="ESPN",
        evidence="'Darrell Bevell was the Seahawks' offensive coordinator for seven seasons' "
                 "(2011-2017), fired 2018-01-10. Combined with the SB XLIX play-call source this "
                 "establishes continuous play-calling responsibility across 2015 and 2016.",
        supports="2015, 2016"),
    "espn2016hou": dict(
        url="https://www.espn.com/nfl/story/_/id/17676861/"
            "houston-texans-coach-bill-obrien-take-play-calling-duties-offense",
        date="2016-09-30", publisher="ESPN",
        evidence="'O'Brien, who called plays during his first season with the team in 2014, gave "
                 "the duty to Godsey last year [2015].' O'Brien resumed the duties before the "
                 "Week 4 game of 2016.",
        supports="2014, 2015, 2016 (2016 as a midseason split)"),
    "espn2016ari": dict(
        url="https://www.espn.com/blog/arizona-cardinals/post/_/id/21412/"
            "harold-goodwin-to-call-cardinals-plays-knows-bruce-arians-will-be-watching",
        date="2016-08-12", publisher="ESPN",
        evidence="Arians is the regular-season play-caller who hands Goodwin the duty for three "
                 "of four PRESEASON games only; Goodwin notes he 'did call the plays three times "
                 "last year in the preseason' (2015). Regular-season attribution = Arians.",
        supports="2015, 2016"),
    "espn2015car": dict(
        url="https://www.espn.com/blog/carolina-panthers/post/_/id/21536/"
            "genius-mike-shula-focused-on-keeping-cam-newton-panthers-offense-unpredictable",
        date="2016-01-20", publisher="ESPN",
        evidence="Shula, Panthers OC 2013-2017, is described as the offense's play-caller; "
                 "corroborated by panthers.com 'Shula takes offensive reins'.",
        supports="2014, 2015, 2016"),
    "espn2019cle": dict(
        url="https://www.espn.com/blog/cleveland/post/_/id/7083/"
            "freddie-kitchens-says-handing-off-play-calling-to-todd-monken-not-gonna-happen",
        date="2019-09-23", publisher="ESPN",
        evidence="Kitchens on handing play-calling to OC Todd Monken: 'That's not even feasible. "
                 "That's not being considered, no... Not gonna happen.' 'It's me.'",
        supports="2019"),
    "espn2019gb": dict(
        url="https://www.espn.com/blog/green-bay-packers/post/_/id/46728/"
            "lafleur-hackett-plan-run-the-ball-then-let-aaron-rodgers-go-play",
        date="2019-01-18", publisher="ESPN",
        evidence="'LaFleur will call the offense but will rely heavily on Hackett's playcalling "
                 "experience.' Hackett is OC; LaFleur is the play-caller.",
        supports="2019"),
    "ringer2019dal": dict(
        url="https://www.theringer.com/nfl-preview/2019/8/15/20806357/"
            "dallas-cowboys-new-offense-dak-prescott-ezekiel-elliott-kellen-moore",
        date="2019-08-15", publisher="The Ringer",
        evidence="'The Cowboys' 2019 Hopes Lie in the Hands of the NFL's Youngest Play-caller' — "
                 "Moore took over play-calling in 2019 after Scott Linehan called plays 2014-2018. "
                 "Corroborated by dallascowboys.com 'Kellen Moore to Handle Play-Calling Duties'.",
        supports="2019"),
    "tampabay2019tb": dict(
        url="https://www.tampabay.com/sports/bucs/2019/11/09/"
            "can-byron-leftwich-keep-growing-into-his-job-as-the-bucs-play-caller/",
        date="2019-11-09", publisher="Tampa Bay Times",
        evidence="In-season piece on Leftwich 'in his job as the Bucs' play-caller'. Corroborated "
                 "by Tampa Bay Times 2019-01-09 ('Bruce Arians: Byron Leftwich will be the "
                 "Buccaneers' offensive play-caller in 2019') and 2019-09-06.",
        supports="2019"),
    "ringer2019dal_linehan": dict(
        url="https://www.theringer.com/nfl-preview/2019/8/15/20806357/"
            "dallas-cowboys-new-offense-dak-prescott-ezekiel-elliott-kellen-moore",
        date="2019-08-15", publisher="The Ringer",
        evidence="'Garrett relinquished play-calling duties in 2013 - after holding them for two "
                 "full seasons - and former Rams head coach and veteran play-caller Scott Linehan "
                 "filled that role for the past four years' (i.e. 2015-2018). 2014 is NOT inside "
                 "the stated range and is left unresolved.",
        supports="2015, 2016"),
    "fox2015gb": dict(
        url="https://www.foxnews.com/sports/mccarthy-promotes-clements-ready-to-give-up-play-calling",
        date="2015-01-01", publisher="Fox Sports / AP",
        evidence="McCarthy promotes Tom Clements to associate head coach/offense and is 'ready to "
                 "give up play calling' for 2015 - establishing that McCarthy himself called the "
                 "plays through the 2014 season. Corroborated by the 2015-12-13 reclaim reports.",
        supports="2014"),
    "steelersdepot2019pit": dict(
        url="https://steelersdepot.com/2019/12/randy-fichtner-defends-play-calling-performance-"
            "i-am-not-going-to-call-scared/",
        date="2019-12-22", publisher="Steelers Depot",
        evidence="Fichtner defends his own 2019 play-calling: 'we are not going to play scared. "
                 "I am not going to call scared.' Establishes him as the 2019 play-caller.",
        supports="2019"),
    "cbs2020nyj": dict(
        url="https://www.cbssports.com/nfl/news/adam-gase-explains-why-he-gave-up-play-calling-"
            "duties-for-the-first-time-as-jets-fell-to-0-7",
        date="2020-10-26", publisher="CBS Sports",
        evidence="'Gase had called his team's plays during his first 70 games as an NFL head "
                 "coach' and relinquished for the FIRST time in Week 7 of 2020 - an explicit "
                 "continuous range that covers the whole of the Jets' 2019 season.",
        supports="2019"),
    "nfl2019min": dict(
        url="https://www.nfl.com/news/kevin-stefanski-returning-as-minnesota-vikings-oc-0ap3000001009202",
        date="2019-01-10", publisher="NFL.com",
        evidence="Stefanski retained as Vikings OC and play-caller for 2019 after calling plays "
                 "as interim OC for the final three games of 2018; corroborated by Star Tribune "
                 "2019 season-preview reporting that Stefanski called plays from the sideline "
                 "while Kubiak advised from the booth.",
        supports="2019"),
    "si2019den": dict(
        url="https://www.si.com/nfl/broncos/news/vic-fangio-on-rich-scangarellos-play-calling-"
            "we-had-to-try-to-win-not-hope-to-win",
        date="2019-12-09", publisher="Sports Illustrated",
        evidence="In-season piece on 'Rich Scangarello's Play-Calling'; HC Fangio discusses the "
                 "coordinator's in-game calls, and GM Elway's criticism of his second-half play "
                 "selection. Establishes Scangarello as the 2019 Broncos play-caller.",
        supports="2019"),
    "cbs2020ten": dict(
        url="https://www.cbssports.com/nfl/news/arthur-smiths-ascent-as-titans-offensive-"
            "coordinator-in-2019-hasnt-surprised-the-organization",
        date="2020-01-19", publisher="CBS Sports",
        evidence="'Arthur Smith has quickly earned the respect of peers around the league for his "
                 "shrewd work in his FIRST SEASON CALLING PLAYS' - i.e. 2019.",
        supports="2019"),
    "nbcla2019la": dict(
        url="https://www.nbclosangeles.com/news/local/rams-coach-mcvay/1965805/",
        date="2019-09-16", publisher="NBC Los Angeles",
        evidence="'Since McVay calls all of the Rams' plays himself, he feels pretty confident "
                 "his target will take the criticism in the right way.'",
        supports="2019"),
    "espn2020hou": dict(
        url="https://www.espn.com/nfl/story/_/id/28780565/"
            "texans-bill-obrien-turning-playcalling-oc-tim-kelly",
        date="2020-02-25", publisher="ESPN",
        evidence="'O'Brien... had been calling the offensive plays since he took the role over "
                 "from former offensive coordinator George Godsey in September 2016.' An explicit "
                 "continuous range covering 2016 (from wk4) through 2019; he handed off for 2020.",
        supports="2019 (also corroborates the 2016 split, 2017 and 2018)"),
    "espn2020chi": dict(
        url="https://www.espn.com/nfl/story/_/id/28478023/"
            "bears-hire-bill-lazor-offensive-coordinator-matt-nagy-retains-play-calling-duties",
        date="2020-01-13", publisher="ESPN",
        evidence="'Nagy will RETAIN offensive playcalling duties moving forward', published after "
                 "the 2019 season and the firing of OC Mark Helfrich - a continuity statement "
                 "establishing Nagy held the duties through 2019. Corroborated by Bleacher Nation "
                 "2019-10-23 'Matt Nagy Remains the Offensive Play-Caller' (title only; the body "
                 "returned HTTP 403 and is therefore NOT relied upon).",
        supports="2019"),
    "inq2020phi": dict(
        url="https://www.inquirer.com/eagles/mike-groh-carson-walch-eagles-fired-offensive-"
            "coordinator-receivers-coach-doug-pederson-20200109.html",
        date="2020-01-09", publisher="Philadelphia Inquirer",
        evidence="'Groh didn't call plays or have final game-plan say, however. Pederson ran the "
                 "offense.' Explicitly rules the nominal OC OUT as play-caller for 2019.",
        supports="2019"),
    "forbes2026kc": dict(
        url="https://www.forbes.com/sites/jefffedotin/2026/01/27/"
            "why-andy-reid-remains-chiefs-playcaller-despite-eric-bieniemys-return/",
        date="2026-01-27", publisher="Forbes",
        evidence="Confirms Reid retained play-calling duties throughout Eric Bieniemy's previous "
                 "tenure as OC (2018-2022) - an explicit continuous range covering 2019. Reid: "
                 "'I'm not afraid to delegate... We do this jointly', i.e. Reid holds primary "
                 "responsibility with collaboration, not a handover.",
        supports="2019"),
    "espn2020sf": dict(
        url="https://www.espn.com/nfl/story/_/id/28648579/"
            "49ers-kyle-shanahan-says-no-regrets-super-bowl-playcalling",
        date="2020-02-06", publisher="ESPN",
        evidence="On Super Bowl LIV (the 2019 season): Shanahan on his own third-down selection, "
                 "'I called a run'; asked if he had any calls he would like back, he said he did "
                 "not. Directly establishes him as the 2019 49ers play-caller.",
        supports="2019"),
    "nbc2021lv": dict(
        url="https://www.nbcsports.com/nfl/profootballtalk/rumor-mill/news/"
            "greg-olson-to-take-over-as-raiders-play-caller-after-jon-gruden-departure",
        date="2021-10-13", publisher="NBC Sports / ProFootballTalk",
        evidence="'While Olson DEFERRED TO GRUDEN to handle the play-calling with the Raiders, it "
                 "won't be his first time handling the role in the NFL.' Establishes Gruden as "
                 "play-caller throughout Olson's OC tenure (2018 through Gruden's 2021 exit), "
                 "covering 2019, and explicitly rules the nominal OC out.",
        supports="2019"),
    "sea2019two": dict(
        url="https://www.espn.com/nfl/story/_/id/30701471/seattle-seahawks-citing-philosophical-"
            "differences-part-offensive-coordinator-brian-schottenheimer",
        date="2021-01-12", publisher="ESPN (+ NBC Sports 2018-01-13)",
        evidence="TWO-SOURCE: NBC Sports 2018-01-13 reports Seattle hiring Schottenheimer 'as "
                 "their next PLAY-CALLER' to replace Bevell; ESPN 2021-01-12 records his "
                 "'3-year run as Seattle Seahawks offensive coordinator' (2018-2020). Combined, "
                 "they establish continuous play-calling responsibility across 2019.",
        supports="2019"),
    "espn2019car": dict(
        url="https://espn.com/espn/wire?id=27281550&section=nfl",
        date="2019-07-29", publisher="ESPN",
        evidence="Rivera took over as full-time DEFENSIVE play-caller and 'has given Turner "
                 "complete autonomy over the offense' - i.e. the offensive play-caller is Turner, "
                 "not the head coach.",
        supports="2019"),
    "si2020jax": dict(
        url="https://www.si.com/nfl/jaguars/onsi/news/"
            "report-former-jaguars-oc-john-defilippo-hired-as-position-coach-by-bears",
        date="2020-01-16", publisher="Sports Illustrated",
        evidence="'This will be the first time SINCE 2017 that DeFilippo will not be an offensive "
                 "coordinator and his team's PRIMARY PLAY-CALLER.' An explicit continuous range "
                 "2017-2019 covering his 2019 Jacksonville season.",
        supports="2019"),
    "nbcp2021ind": dict(
        url="https://www.nbcsportsphiladelphia.com/nfl/philadelphia-eagles/"
            "a-closer-look-at-nick-siriannis-former-role-with-the-colts/176872/",
        date="2021-01-22", publisher="NBC Sports Philadelphia",
        evidence="Sirianni did NOT call plays as Colts OC; that duty fell to head coach Frank "
                 "Reich, across all three seasons they worked together (2018-2020). Explicitly "
                 "rules the nominal OC out for 2019.",
        supports="2019"),
    "espn2020cin": dict(
        url="https://www.espn.com/blog/cincinnati-bengals/post/_/id/32690/"
            "why-bengals-offensive-uptick-bodes-well-for-zac-taylors-future",
        date="2020-11-12", publisher="ESPN",
        evidence="Taylor was hired in 2019 as head coach AND playcaller; the piece discusses "
                 "'Taylor's status as a playcaller' being unproven on arrival and contrasts his "
                 "limited prior coordinator experience. Establishes him as the 2019 caller.",
        supports="2019"),
    "espn2019mia": dict(
        url="https://www.espn.com/blog/miami-dolphins/post/_/id/28727/"
            "expect-chad-osheas-dolphins-offense-to-emphasize-playmakers",
        date="2019-02-20", publisher="ESPN",
        evidence="Describes 'first-time PLAYCALLER and offensive coordinator Chad O'Shea' ahead "
                 "of the 2019 season - an explicit play-caller designation, not a title.",
        supports="2019"),
    "espn2014den": dict(
        url="https://www.espn.com/nfl/playoffs/2014/story/_/id/12104203/"
            "peyton-manning-denver-broncos-backs-adam-gase-jobs",
        date="2014-12-31", publisher="ESPN",
        evidence="'Gase, in his SECOND SEASON as the Broncos' PLAYCALLER...' and 'In the two "
                 "seasons Gase has CALLED PLAYS with Manning at quarterback, the Broncos finished "
                 "with... 606 points in 2013, and 486 points in 2014.' Explicit for 2014.",
        supports="2014"),
    "vikings2016min": dict(
        url="https://www.vikings.com/news/norv-turner-resigns-as-vikings-offensive-coordinator-18004050",
        date="2016-11-02", publisher="Minnesota Vikings (official)",
        evidence="Turner 'was in his 32nd NFL season and THIRD WITH THE VIKINGS' at his 2016 "
                 "resignation, i.e. OC from 2014; Star Tribune records he resigned 'despite "
                 "having total free will of Vikings offense'. Establishes him as the 2014 caller.",
        supports="2014"),
    "balsun2014bal": dict(
        url="http://www.baltimoresun.com/sports/bs-sp-ravens-kubiak-flacco-1221-20141219-story.html",
        date="2014-12-20", publisher="Baltimore Sun",
        evidence="Headline: 'With Gary Kubiak CALLING THE PLAYS, Joe Flacco is nearing career "
                 "highs'. Body: 'Every Friday, offensive coordinator Gary Kubiak hands Joe Flacco "
                 "his PLAY SHEET for the Ravens' upcoming game...'",
        supports="2014"),
    "espn2018pit": dict(
        url="https://www.espn.com/nfl/story/_/id/22133581/"
            "pittsburgh-steelers-part-ways-offensive-coordinator-todd-haley",
        date="2018-01-17", publisher="ESPN",
        evidence="Tomlin: 'I would like to thank Todd for his contributions to our offense the "
                 "PAST SIX YEARS' (2012-2017), during which Haley held play-calling duties as OC "
                 "- an explicit continuous range covering 2014, 2015 and 2016.",
        supports="2014, 2015, 2016"),
    "nfl2014ten": dict(
        url="https://nfl.com/news/story/0ap2000000314683/article/"
            "jason-michael-hired-as-tennessee-titans-oc",
        date="2014-01-17", publisher="NFL.com",
        evidence="'Although Michael will direct daily meetings and oversee the offense, this is "
                 "still Whisenhunt's scheme. The latter will RETAIN PLAY-CALLING DUTIES.' "
                 "Explicitly rules the nominal OC out for 2014.",
        supports="2014"),
    "cbs2017lv": dict(
        url="https://www.cbsnews.com/sacramento/news/"
            "oakland-raiders-replacing-offensive-coordinator-bill-musgrave/",
        date="2017-01-10", publisher="CBS Sacramento",
        evidence="Musgrave served two seasons as Raiders OC (2015-2016); Del Rio 'publicly "
                 "CRITICIZED MUSGRAVE'S PLAY-CALLING at times during the season', which "
                 "attributes in-game calls to Musgrave rather than the head coach.",
        supports="2015, 2016"),
    "espn2015mia": dict(
        url="https://www.espn.com/nfl/story/_/id/14258236/"
            "miami-dolphins-fire-offensive-coordinator-bill-lazor-promote-zac-taylor",
        date="2015-11-30", publisher="ESPN",
        evidence="Lazor was Miami's OC and play-caller until his 2015-11-30 firing, after which "
                 "'Quarterbacks coach Zac Taylor will TAKE OVER PLAY-CALLING DUTIES for the final "
                 "five games'. Establishes Lazor as caller in 2014 and through 2015 wk12.",
        supports="2014 (2015 handled as a midseason split)"),
    "nfl2015atl": dict(
        url="https://www.nfl.com/news/atlanta-falcons-plan-to-hire-dan-quinn-kyle-shanahan-0ap3000000459983",
        date="2015-01-18", publisher="NFL.com",
        evidence="Shanahan hired as Falcons OC for 2015, described as a 'talented PLAY-CALLER' who "
                 "will 'run an attack' with Matt Ryan. Corroborated for 2016 by Dan Quinn calling "
                 "him 'a play-caller' with 'experience as a play-caller' (49erswebzone 2019-12-11). "
                 "NOTE: that 2019 piece dates his ATL play-calling '2016-2017', which conflicts "
                 "with the 2015-01-18 hire and his Feb-2017 departure to SF; the contemporaneous "
                 "hiring record is taken as authoritative and the discrepancy is logged.",
        supports="2015, 2016"),
    "cbs2014det": dict(
        url="https://www.cbsnews.com/detroit/news/joe-lombardi-brings-saints-playbook-to-lions-expects-to-call-plays/",
        date="2014-02-07", publisher="CBS Detroit",
        evidence="Lombardi hired as Lions OC and expects to CALL PLAYS for 2014: 'the last few "
                 "years I've always been in that mode of, Hey, what play would I call here?' "
                 "Corroborated by ESPN 2015-10-26, which records him as the play-caller until "
                 "his in-season firing.",
        supports="2014"),
    "espn2016jax": dict(
        url="https://www.espn.com/nfl/story/_/id/17919123/"
            "jacksonville-jaguars-fire-offensive-coordinator-greg-olson-promote-qb-coach-nathaniel-hackett",
        date="2016-10-29", publisher="ESPN",
        evidence="Olson fired after wk8 of 2016 with QB coach Hackett assuming PLAYCALLING "
                 "responsibilities; the same piece records that Hackett 'previously served as the "
                 "OFFENSIVE COORDINATOR with Buffalo in 2013-14 under head coach Doug Marrone', "
                 "which with the Bills' own hiring release (Marrone 'cede[d] the offensive play "
                 "calling duties to Hackett') establishes Hackett as Buffalo's 2014 caller.",
        supports="2014 BUF, 2015 JAX, 2016 JAX split"),
    "sf2014shared": dict(
        url="https://www.espn.com/blog/san-francisco-49ers/post/_/id/11004/"
            "greg-roman-remains-49ers-offensive-coordinator",
        date="2014-01-01", publisher="ESPN",
        evidence="Roman was 49ers OC in 2014, but reporting establishes that all calls went "
                 "THROUGH head coach Jim Harbaugh, with Roman developing the game plan and "
                 "providing the call on the sideline. Shared authority, no defensible split.",
        supports="2014 (AMBIGUOUS - deliberately unassigned)"),
    "espn2015den": dict(
        url="https://www.espn.com/blog/denver-broncos/post/_/id/14196/"
            "gary-kubiak-outlines-how-play-calling-will-go-for-broncos",
        date="2015-08-13", publisher="ESPN",
        evidence="'...unless something in the game dictates otherwise, it will be KUBIAK WHO "
                 "MAKES THE CALL and Knapp who delivers the call to Manning.' OC Rick Dennison "
                 "sits in the coaches' box. Head coach is the caller for 2015.",
        supports="2015"),
    "ravens2016bal": dict(
        url="https://www.baltimoreravens.com/news/ravens-fire-offensive-coordinator-marc-trestman-17854693",
        date="2016-10-10", publisher="Baltimore Ravens (official)",
        evidence="Trestman fired after wk5 of 2016; the piece discusses 'Trestman's play-calling' "
                 "problems, attributing in-game calls to him, and records Mornhinweg replacing him "
                 "'for the rest of the season'. Establishes Trestman as caller for 2015 and "
                 "2016 wks1-5.",
        supports="2015, 2016 (2016 as a midseason split)"),
    "bucs2016tb": dict(
        url="https://www.buccaneers.com/news/dirk-koetter-to-retain-play-calling-duties-16704120",
        date="2016-01-18", publisher="Tampa Bay Buccaneers (official)",
        evidence="'New Head Coach Dirk Koetter will STILL CALL PLAYS, AS HE DID in leading the "
                 "Buccaneers to a record-breaking offensive season in 2015.' Koetter: 'I will "
                 "continue to be the play-caller for the Bucs.' Covers 2015 (as OC) and 2016 "
                 "(as HC).",
        supports="2015, 2016"),
    "nbc2016cle": dict(
        url="https://www.nbcsports.com/nfl/profootballtalk/rumor-mill/news/"
            "hue-jackson-plans-to-call-plays-not-hire-an-offensive-coordinator",
        date="2016-01-16", publisher="NBC Sports / ProFootballTalk",
        evidence="Jackson on taking the Browns HC job: 'I don't really plan on having an "
                 "offensive coordinator, because [I want to reserve that right to call plays]'. "
                 "Head coach as play-caller for 2016.",
        supports="2016"),
    "nfl2016gb": dict(
        url="https://www.nfl.com/news/mike-mccarthy-i-ll-never-give-up-play-calling-again-0ap3000000680593",
        date="2016-08-01", publisher="NFL.com",
        evidence="McCarthy on having handed play-calling to Tom Clements in 2015 and reclaiming it "
                 "midseason: 'I'll NEVER DO THAT AGAIN.' Published pre-2016, establishing McCarthy "
                 "as the Packers' play-caller for 2016.",
        supports="2016"),
    "inq2021phi": dict(
        url="https://www.inquirer.com/eagles/"
            "philadelphia-eagles-frank-reich-carson-wentz-doug-pederson-20210816.html",
        date="2021-08-16", publisher="Philadelphia Inquirer",
        evidence="Pederson was 'eager to CALL PLAYS on Sunday and to let Reich and quarterbacks "
                 "coach John DeFilippo handle the hands-on coaching during the week' - covering "
                 "Reich's 2016-2017 tenure as Eagles OC. Explicitly rules the nominal OC out.",
        supports="2016"),
    "nbc2016sf": dict(
        url="https://www.nbcsportsbayarea.com/nfl/"
            "49ers-oc-modkins-to-provide-kelly-with-input-from-upstairs/1252609/",
        date="2016-06-03", publisher="NBC Sports Bay Area",
        evidence="OC Curtis Modkins himself: 'CHIP WILL CALL THE PLAYS and he's been great at it.' "
                 "Modkins runs meetings and calls most practice plays but sits in the booth on "
                 "game day. Head coach is the 2016 caller; nominal OC explicitly ruled out.",
        supports="2016"),
    "espn2016nopc": dict(
        url="https://www.espn.com/blog/new-orleans-saints/post/_/id/23341/"
            "sean-payton-not-earth-shattering-that-pete-carmichael-jr-now-calls-plays",
        date="2016-09-13", publisher="ESPN",
        evidence="'Payton RESUMED PLAY-CALLING when he returned in 2013' and held it until handing "
                 "back to Carmichael in 2016; Carmichael 'last called plays during the 2012 "
                 "season'. An explicit continuous range establishing Payton as the caller for "
                 "2014 and 2015. Consistent with the separate 2016 shared-authority finding.",
        supports="2014, 2015"),
    "espn2016ind": dict(
        url="https://www.espn.com/blog/indianapolis-colts/post/_/id/17058/"
            "colts-oc-rob-chudzinski-putting-his-prints-on-offense-in-first-full-season",
        date="2016-06-14", publisher="ESPN",
        evidence="'Chudzinski had CONTROL OF THE PLAY-CALLING, but he wasn't running his offense. "
                 "He TOOK OVER as coordinator on a short week after PEP HAMILTON WAS FIRED IN "
                 "WEEK 9.' Confirms Hamilton as caller through 2015 wk8 (and therefore 2014), "
                 "Chudzinski from 2015 wk9, and Chudzinski retaining it for 2016.",
        supports="2014 IND, 2015 IND split, 2016 IND"),
    "espn2017nyj": dict(
        url="https://www.espn.com/nfl/story/_/id/18400965/"
            "chan-gailey-new-york-jets-retires-5-other-assistants-fired",
        date="2017-01-03", publisher="ESPN",
        evidence="Gailey 'served as Todd Bowles' offensive coordinator the past two seasons' "
                 "(2015-2016) as the Jets' offensive PLAY-CALLER, retiring after 2016.",
        supports="2015, 2016"),
    "yahoo2015la": dict(
        url="https://sports.yahoo.com/blogs/nfl-shutdown-corner/"
            "rams-fire-offensive-coordinator-frank-cignetti--rob-boras-promoted-204218400.html",
        date="2015-12-07", publisher="Yahoo Sports",
        evidence="Rams fired OC Frank Cignetti after the wk13 loss to Arizona (4-8); Rob Boras "
                 "'will be the team's new coordinator' and play-caller from wk14 of 2015, "
                 "continuing as full-time OC for 2016.",
        supports="2015 split, 2016"),
    "nfl2014dal": dict(
        url="https://www.nfl.com/news/dallas-cowboys-hire-scott-linehan-as-play-caller-0ap2000000318629",
        date="2014-01-20", publisher="NFL.com",
        evidence="Headline: 'Dallas Cowboys hire Scott Linehan as PLAY-CALLER'. Body: Linehan "
                 "'was hired Monday to CALL PLAYS' and is the team's 'primary play-caller', "
                 "replacing Bill Callahan and becoming 'Dallas' third offensive play-caller in as "
                 "many seasons'. Resolves 2014 directly - the row deliberately left outside The "
                 "Ringer's attested 2015-2018 Linehan range.",
        supports="2014"),
    "espn2015phi": dict(
        url="http://www.espn.com/nfl/story/_/id/13637802/"
            "pat-shurmur-philadelphia-eagles-prefers-stay-spotlight-nfl",
        date="2015-09-12", publisher="ESPN",
        evidence="OC Pat Shurmur disclaims the role in-season: 'It's coach's team. I'm one of the "
                 "guys here helping to put it into play', characterising the offense as designed "
                 "and led by Kelly with 'collective agreement in the play designs'. Kelly is the "
                 "2015 caller; the nominal OC rules himself out.",
        supports="2015"),
    "si2014tb": dict(
        url="https://www.si.com/nfl/2014/12/05/jeff-tedford-tampa-bay-buccaneers-released",
        date="2014-12-05", publisher="Sports Illustrated",
        evidence="Nominal OC Jeff Tedford 'took an indefinite leave of absence in September after "
                 "undergoing heart surgery and has remained away from the team ever since'; "
                 "'Quarterbacks coach MARCUS ARROYO HAS CALLED PLAYS for Tampa Bay in the "
                 "interim.' Contemporaneous reporting records Tedford never called a regular-season "
                 "play in 2014, so the full season is attributed to Arroyo, NOT the titled OC.",
        supports="2014"),
    "espn2016buf": dict(
        url="https://www.espn.com/nfl/story/_/id/17565671/"
            "rex-ryan-firing-buffalo-bills-offensive-coordinator-my-move",
        date="2016-09-16", publisher="ESPN",
        evidence="Roman fired after the 0-2 start (through wk2 of 2016); assistant head coach "
                 "Anthony Lynn assumed the playcalling duties. Establishes Roman as Buffalo's "
                 "caller for 2015 and 2016 wks1-2.",
        supports="2015, 2016 split"),
    "nbc2016mia": dict(
        url="https://www.nbcsports.com/nfl/profootballtalk/rumor-mill/news/"
            "dolphins-expected-to-hire-clyde-christensen-as-offensive-coordinator",
        date="2016-01-17", publisher="NBC Sports / ProFootballTalk",
        evidence="'One thing Christensen WON'T DO is CALL THE OFFENSIVE PLAYS, which is something "
                 "Gase said he'll do for at least the early days of his head coaching career.' "
                 "Nominal OC explicitly ruled out; head coach is the 2016 caller.",
        supports="2016"),
    "nfl2016ten": dict(
        url="http://www.nfl.com/news/story/0ap3000000624901/article/"
            "titans-hiring-terry-robiskie-as-offensive-coordinator",
        date="2016-01-20", publisher="NFL.com",
        evidence="'Terry Robiskie has been hired as the team's NEW PLAY-CALLER' - explicit "
                 "play-calling designation, not merely the coordinator title, under HC Mularkey.",
        supports="2016"),
    "fox2016lac": dict(
        url="https://www.foxnews.com/sports/ex-chargers-play-caller-frank-reich-lands-in-philadelphia",
        date="2016-01-18", publisher="Fox Sports / AP",
        evidence="Headline identifies Reich as the 'EX CHARGERS PLAY CALLER'; the body records he "
                 "served 'in two seasons with the Chargers' as offensive coordinator before "
                 "joining Philadelphia in Jan 2016 - i.e. 2014 and 2015. Corroborated by ESPN "
                 "2016-01-04, which dates his ascent to OC to 2014 when Whisenhunt left for "
                 "Tennessee.",
        supports="2014, 2015"),
    "nfl2014cin": dict(
        url="https://nfl.com/news/story/0ap2000000311090/article/"
            "hue-jackson-to-be-cincinnati-bengals-offensive-coordinator",
        date="2014-01-09", publisher="NFL.com",
        evidence="'Hue Jackson will TAKE OVER THE TEAM'S PLAY-CALLING DUTIES' for 2014, following "
                 "Jay Gruden's departure to Washington.",
        supports="2014"),
    "giants2014nyg": dict(
        url="https://www.giants.com/news/ben-mcadoo-named-offensive-coordinator-12437489",
        date="2014-01-14", publisher="New York Giants (official)",
        evidence="McAdoo on being named OC: 'This will be the first job where I CALL PLAYS ON "
                 "SUNDAY.' HC Coughlin: 'I'll be there to help him' - i.e. Coughlin delegates "
                 "rather than retains. McAdoo held the OC role for 2014 and 2015 before his "
                 "promotion to head coach (The Ringer 2017-09-23 records that he then 'held onto "
                 "play-calling responsibilities' as HC).",
        supports="2014, 2015"),
    "espn2017nygsull": dict(
        url="https://www.espn.com/nfl/story?id=21082776",
        date="2017-10-19", publisher="ESPN",
        evidence="McAdoo 'had CALLED THE PLAYS SINCE ARRIVING as the offensive coordinator under "
                 "Tom Coughlin in 2014. He kept doing the job when he became the head coach last "
                 "season' - an explicit continuous range covering 2014, 2015 and 2016. 'McAdoo "
                 "handed the job to Sullivan last week' after an 0-5 start, i.e. 2017 wk6.",
        supports="2016 (and corroborates 2014-2015; 2017 handled as a split)"),
    "nbc2014la": dict(
        url="https://www.nbcsports.com/nfl/profootballtalk/rumor-mill/news/"
            "jeff-fisher-is-all-in-with-brian-schottenheimer",
        date="2014-12-31", publisher="NBC Sports / ProFootballTalk",
        evidence="HC Jeff Fisher on his OC at the close of the 2014 season: 'I think Brian is an "
                 "OUTSTANDING PLAY-CALLER. Outstanding play-caller.' Attributes the calls to "
                 "Schottenheimer, not the head coach.",
        supports="2014"),
    "espn2017kc": dict(
        url="https://www.espn.com/nfl/story/_/id/21651814/"
            "andy-reid-kansas-city-chiefs-gives-playcalling-duty",
        date="2017-12-03", publisher="ESPN",
        evidence="Reid 'handing over playcalling responsibilities to offensive coordinator Matt "
                 "Nagy' in Dec 2017 establishes Reid as the incumbent caller. On the prior "
                 "coordinator: 'PEDERSON SCRIPTED THE FIRST 15 PLAYS a couple of times but DID "
                 "NOT HAVE A GENUINE START-TO-FINISH PLAYCALLING EXPERIENCE' during his Kansas "
                 "City tenure - which resolves 2014-2015 to Reid rather than leaving them "
                 "ambiguous. Scripting an opening series is not season-level play-calling.",
        supports="2014, 2015, 2016 (Reid remained the incumbent caller until the "
                 "Dec-2017 handover to Nagy, which is recorded separately as the "
                 "2017 wk13 split)"),
    "fox2015sf": dict(
        url="https://www.foxnews.com/sports/49ers-oc-chryst-learning-to-play-the-hand-that-youre-dealt.amp",
        date="2015-11-06", publisher="Fox Sports / AP",
        evidence="In-season, OC Geep Chryst speaking of his own in-game calls: 'You feel like you "
                 "bear it EVERY CALL THAT YOU MAKE.' Establishes him as San Francisco's 2015 "
                 "play-caller under HC Jim Tomsula.",
        supports="2015"),
    "cle2014": dict(
        url="https://www.clevelandbrowns.com/news/"
            "brian-hoyer-and-kyle-shanahan-constantly-swapping-ideas-14011288",
        date="2014-10-15", publisher="Cleveland Browns (official)",
        evidence="In-season piece on Shanahan's in-game calls with QB Brian Hoyer; Jaguars HC Gus "
                 "Bradley characterises him as 'a very good PLAY CALLER'. Establishes Shanahan as "
                 "the Browns' 2014 play-caller under HC Mike Pettine.",
        supports="2014"),
    "espn2015ten": dict(
        url="https://www.espn.com/blog/tennessee-titans/post/_/id/16730/"
            "rookie-play-caller-jason-michael-about-to-debut-for-titans",
        date="2015-11-03", publisher="ESPN",
        evidence="'Ken Whisenhunt, fired on Tuesday, CALLED PLAYS DURING ALL 23 GAMES of his "
                 "tenure with the Titans' - covering all of 2014 and 2015 wks1-8. 'Offensive "
                 "coordinator Jason Michael will have the responsibilities that traditionally "
                 "come with the job title starting Sunday' (wk9).",
        supports="2014 (corroborates), 2015 split"),
    "espn2015ne": dict(
        url="https://africa.espn.com/nfl/playoffs/2014/story/_/page/lastcall-superbowlxlix/"
            "seattle-seahawks-last-call-memorable-moments-super-bowl-xlix-clayton-last-call",
        date="2015-02-02", publisher="ESPN",
        evidence="On Super Bowl XLIX (the 2014 season): OC Josh McDaniels devised and executed "
                 "the short-passing game plan against Seattle's zones, quoted on his own "
                 "approach - 'we had to come up with some ways to get some space' - with the "
                 "in-game calls attributed to him throughout.",
        supports="2014"),
    "espn2017ne": dict(
        url="https://africa.espn.com/nfl/story/_/id/18628898/"
            "how-new-england-patriots-converted-two-point-tries-super-bowl-li",
        date="2017-02-06", publisher="ESPN",
        evidence="On Super Bowl LI (the 2016 season): 'This was when offensive coordinator Josh "
                 "McDaniels BROUGHT three-WR personnel onto the field and aligned the Patriots in "
                 "an empty set...' and 'This was A GREAT CALL BY McDANIELS after White's 1-yard "
                 "touchdown run'. In-game calls attributed to McDaniels.",
        supports="2016"),
    "ne2016afc": dict(
        url="https://www.patriots.com/news/patriots-broncos-afc-championship-performance-review-254891",
        date="2016-01-25", publisher="New England Patriots (official)",
        evidence="On the 2015-season AFC Championship: 'The trick play that OC JOSH McDANIELS "
                 "CALLED nearly worked' on 4th-and-1, and 'one of the most controversial "
                 "play-calls of the day for New England...'. In-game calls attributed to McDaniels.",
        supports="2015"),
    "espn2014phi": dict(
        url="http://www.espn.com/blog/philadelphia-eagles/post/_/id/8119/"
            "second-guessing-chip-kellys-play-calls-at-the-goal-line",
        date="2014-09-30", publisher="ESPN",
        evidence="In-season piece titled 'Second-guessing CHIP KELLY'S PLAY CALLS at the goal "
                 "line': at the 1-yard line 'coach Chip Kelly OPTED FOR passing attempts from "
                 "quarterback Nick Foles' on third and fourth down. Head coach is the 2014 caller.",
        supports="2014"),
    "nbc2014nyj": dict(
        url="https://www.nbcsports.com/nfl/profootballtalk/rumor-mill/news/"
            "marty-mornhinweg-sheldon-richardson-teamed-up-for-fateful-jets-timeout",
        date="2014-09-15", publisher="NBC Sports / ProFootballTalk",
        evidence="In-season: 'Replays showed OFFENSIVE COORDINATOR MARTY MORNHINWEG GESTURING FOR "
                 "A TIMEOUT'; he 'apparently didn't like THE PLAY CALL', and protocol required him "
                 "to 'inform Rex Ryan that he wants a timeout ON THE HEADSET'. Places Mornhinweg "
                 "on the offensive headset running the call sheet in 2014.",
        supports="2014"),
    "espn2014atl": dict(
        url="http://www.espn.com/blog/nfcsouth/post/_/id/58793/"
            "falcons-oc-dirk-koetter-on-third-down-call-sure-wed-change-it",
        date="2014-11-25", publisher="ESPN",
        evidence="In-season, headlined 'Falcons OC DIRK KOETTER ON THIRD-DOWN CALL'. Koetter "
                 "answers for his own call - 'Sure, we'd change it' - and explains the route "
                 "combination he chose on 3rd-and-2 late in the Cleveland loss. Contemporaneous "
                 "reporting names Koetter, not HC Mike Smith, as the caller.",
        supports="2014"),
    "espn2015chi": dict(
        url="http://www.espn.com/blog/chicago-bears/post/_/id/4700924/"
            "adam-gase-jay-cutler-key-parts-of-bears-resurgence",
        date="2015-11-20", publisher="ESPN",
        evidence="In-season: 'on first and second down, ADAM HAS DONE A REALLY GOOD JOB OF "
                 "PLAY-CALLING; running the ball efficiently; getting to third-and-manageable', "
                 "plus credit to 'offensive coordinator Adam Gase for coming up with realistic "
                 "game plans'. Establishes Gase as the 2015 Bears play-caller under HC John Fox.",
        supports="2015"),
    "espn2016det": dict(
        url="http://www.espn.com/blog/detroit-lions/post/_/id/21523/"
            "matthew-staffords-last-eight-games-gave-answers-about-his-lions-future",
        date="2016-01-05", publisher="ESPN",
        evidence="'It's not a coincidence the Lions went 6-2 with Stafford playing well and "
                 "COOTER CALLING THE PLAYS' - explicit attribution from his 2015 wk8 promotion "
                 "onward. CONTINUITY BASIS FOR 2016: Cooter is attested as the caller at both "
                 "ends of the span (this piece for 2015 wk8+, and the ESPN 2017 32-team table for "
                 "2017) while holding the same job continuously, and SI's 2016 MVP feature "
                 "describes 2016 as 'his first full season' in the role. Bracketed attestation "
                 "plus documented role continuity, NOT bare adjacent-season interpolation.",
        supports="2016"),
    "espn2016no": dict(
        url="https://www.espn.com/espn/wire/_/section/nfl/id/17549941",
        date="2016-09-14", publisher="ESPN",
        evidence="'Carmichael was the primary play caller in Drew Brees' ear' in the 2016 opener, "
                 "but Payton 'talks to him through his headset throughout the game, and when "
                 "Payton feels strongly about a particular play... that's what gets called.' "
                 "Shared responsibility with no defensible split -> AMBIGUOUS.",
        supports="2016 (ambiguous)"),
}


# ============================================================================================
# REJECTED SOURCES — examined and deliberately NOT used. Recorded so no later pass "rediscovers"
# them and treats them as an easy win.
# ============================================================================================
REJECTED_SOURCES = {
    "espn2015_10hc": dict(
        url="https://www.espn.com/blog/nflnation/post/_/id/161224/"
            "kelly-one-of-10-head-coaches-to-call-plays",
        date="2015-02-10", publisher="ESPN",
        content="Table 'NFL Head Coaches Who Call Plays': Arians (ARI), Jay Gruden (WAS), Chip "
                "Kelly (PHI), Gary Kubiak (DEN), Bill O'Brien (HOU), Sean Payton (NO), Andy Reid "
                "(KC), Ken Whisenhunt (TEN) on offense; Rex Ryan (BUF) and Zimmer (MIN) on defense.",
        reason="SEASON IS INDETERMINATE AND THE TABLE IS INTERNALLY INCONSISTENT. Published "
               "2015-02-10, between seasons. 'Gary Kubiak (Broncos)' can only be 2015 -- he was "
               "Baltimore's OC in 2014 and became Denver's HC in Jan 2015. But 'Jay Gruden "
               "(Washington)' and 'Bill O'Brien (Texans)' can only be 2014 -- Gruden handed "
               "play-calling to McVay for 2015 (ESPN 2017-01-12) and O'Brien handed it to Godsey "
               "for 2015 (ESPN 2016-09-30), both already sourced here. The table is therefore a "
               "point-in-time snapshot of INTENT in Feb 2015, not a season-level record, and "
               "cannot attribute any team-season. Using it would have silently mis-stamped "
               "several rows across two different seasons.",
        would_have_added="ARI 2014/2015, PHI 2014/2015, DEN 2015, NO 2014/2015, KC 2014/2015 "
                         "-- all refused."),
}

# ---------------------------------------------------------------------------- full-season tables
PC_2020 = {
    "ARI": "Kliff Kingsbury", "ATL": "Dirk Koetter", "BAL": "Greg Roman", "BUF": "Brian Daboll",
    "CAR": "Joe Brady", "CHI": "Matt Nagy", "CIN": "Zac Taylor", "CLE": "Kevin Stefanski",
    "DAL": "Kellen Moore", "DEN": "Pat Shurmur", "DET": "Darrell Bevell", "GB": "Matt LaFleur",
    "HOU": "Tim Kelly", "IND": "Frank Reich", "JAX": "Jay Gruden", "KC": "Andy Reid",
    "LV": "Jon Gruden", "LAC": "Shane Steichen", "LA": "Sean McVay", "MIA": "Chan Gailey",
    "MIN": "Gary Kubiak", "NE": "Josh McDaniels", "NO": "Sean Payton", "NYG": "Jason Garrett",
    "NYJ": "Adam Gase", "PHI": "Doug Pederson", "PIT": "Randy Fichtner", "SF": "Kyle Shanahan",
    "SEA": "Brian Schottenheimer", "TB": "Byron Leftwich", "TEN": "Arthur Smith",
    "WAS": "Scott Turner",
}
PC_2021 = {
    "KC": "Andy Reid", "NO": "Sean Payton", "LA": "Sean McVay", "SF": "Kyle Shanahan",
    "GB": "Matt LaFleur", "NE": "Josh McDaniels", "IND": "Frank Reich", "CLE": "Kevin Stefanski",
    "LV": "Jon Gruden", "ATL": "Arthur Smith", "TB": "Byron Leftwich", "BAL": "Greg Roman",
    "CHI": "Matt Nagy", "JAX": "Darrell Bevell", "DAL": "Kellen Moore", "ARI": "Kliff Kingsbury",
    "BUF": "Brian Daboll", "NYG": "Jason Garrett", "CAR": "Joe Brady", "WAS": "Scott Turner",
    "LAC": "Joe Lombardi", "DEN": "Pat Shurmur", "CIN": "Zac Taylor", "PHI": "Nick Sirianni",
    "DET": "Anthony Lynn", "TEN": "Todd Downing", "HOU": "Tim Kelly", "PIT": "Matt Canada",
    "MIN": "Klint Kubiak", "NYJ": "Mike LaFleur", "SEA": "Shane Waldron",
    # MIA 2021 listed as co-OCs George Godsey / Eric Studesville -> ambiguous, see AMBIGUOUS below
}
PC_2022 = {
    "KC": "Andy Reid", "LA": "Sean McVay", "SF": "Kyle Shanahan", "GB": "Matt LaFleur",
    "JAX": "Doug Pederson", "TB": "Byron Leftwich", "MIA": "Mike McDaniel",
    "LV": "Josh McDaniels", "IND": "Frank Reich", "DAL": "Kellen Moore", "CIN": "Zac Taylor",
    "CLE": "Kevin Stefanski", "BAL": "Greg Roman", "NO": "Pete Carmichael",
    "ARI": "Kliff Kingsbury", "WAS": "Scott Turner", "LAC": "Joe Lombardi", "ATL": "Arthur Smith",
    "BUF": "Ken Dorsey", "SEA": "Shane Waldron", "MIN": "Kevin O'Connell", "DET": "Ben Johnson",
    "NYG": "Mike Kafka", "NYJ": "Mike LaFleur", "PIT": "Matt Canada", "HOU": "Pep Hamilton",
    "TEN": "Todd Downing", "CAR": "Ben McAdoo", "DEN": "Nathaniel Hackett", "CHI": "Luke Getsy",
    # PHI 2022 conflicts (Yardbarker: Sirianni; CBS: Steichen) -> CONFLICT below
    # NE 2022 listed as Matt Patricia / Joe Judge -> ambiguous
}
PC_2023 = {
    "ARI": "Drew Petzing", "ATL": "Arthur Smith", "BAL": "Todd Monken", "BUF": "Ken Dorsey",
    "CAR": "Frank Reich", "CHI": "Luke Getsy", "CIN": "Zac Taylor", "CLE": "Kevin Stefanski",
    "DAL": "Mike McCarthy", "DEN": "Sean Payton", "DET": "Ben Johnson", "GB": "Matt LaFleur",
    "HOU": "Bobby Slowik", "IND": "Shane Steichen", "JAX": "Doug Pederson", "KC": "Andy Reid",
    "LV": "Josh McDaniels", "LAC": "Kellen Moore", "LA": "Sean McVay", "MIA": "Mike McDaniel",
    "MIN": "Kevin O'Connell", "NE": "Bill O'Brien", "NO": "Pete Carmichael", "NYG": "Mike Kafka",
    "NYJ": "Nathaniel Hackett", "PHI": "Brian Johnson", "PIT": "Matt Canada",
    "SF": "Kyle Shanahan", "SEA": "Shane Waldron", "TB": "Dave Canales", "TEN": "Tim Kelly",
    "WAS": "Eric Bieniemy",
}
PC_2024 = {
    "ARI": "Drew Petzing", "ATL": "Zac Robinson", "BAL": "Todd Monken", "BUF": "Joe Brady",
    "CAR": "Dave Canales", "CHI": "Shane Waldron", "CIN": "Zac Taylor", "CLE": "Kevin Stefanski",
    "DAL": "Mike McCarthy", "DEN": "Sean Payton", "DET": "Ben Johnson", "GB": "Matt LaFleur",
    "HOU": "Bobby Slowik", "IND": "Shane Steichen", "JAX": "Press Taylor", "KC": "Andy Reid",
    "LV": "Luke Getsy", "LAC": "Greg Roman", "LA": "Sean McVay", "MIA": "Mike McDaniel",
    "MIN": "Kevin O'Connell", "NE": "Alex Van Pelt", "NO": "Klint Kubiak", "NYG": "Brian Daboll",
    "NYJ": "Nathaniel Hackett", "PHI": "Kellen Moore", "PIT": "Arthur Smith",
    "SF": "Kyle Shanahan", "SEA": "Ryan Grubb", "TB": "Liam Coen", "TEN": "Brian Callahan",
    "WAS": "Kliff Kingsbury",
}
PC_2025 = {
    "ARI": "Drew Petzing", "ATL": "Zac Robinson", "BAL": "Todd Monken", "BUF": "Joe Brady",
    "CAR": "Dave Canales", "CHI": "Ben Johnson", "CIN": "Zac Taylor", "CLE": "Kevin Stefanski",
    "DAL": "Brian Schottenheimer", "DEN": "Sean Payton", "DET": "John Morton",
    "GB": "Matt LaFleur", "HOU": "Nick Caley", "IND": "Shane Steichen", "JAX": "Liam Coen",
    "KC": "Andy Reid", "LAC": "Greg Roman", "LA": "Sean McVay", "LV": "Chip Kelly",
    "MIA": "Mike McDaniel", "MIN": "Kevin O'Connell", "NE": "Josh McDaniels",
    "NO": "Kellen Moore", "NYG": "Mike Kafka", "NYJ": "Tanner Engstrand",
    "PHI": "Kevin Patullo", "PIT": "Arthur Smith", "SF": "Kyle Shanahan", "SEA": "Klint Kubiak",
    "TB": "Josh Grizzard", "TEN": "Brian Callahan", "WAS": "Kliff Kingsbury",
}
PC_2026 = {
    "LA": "Sean McVay", "SF": "Kyle Shanahan", "CHI": "Ben Johnson", "DEN": "Sean Payton",
    "JAX": "Liam Coen", "NE": "Josh McDaniels", "KC": "Andy Reid", "MIN": "Kevin O'Connell",
    "GB": "Matt LaFleur", "IND": "Shane Steichen", "LAC": "Mike McDaniel", "NO": "Kellen Moore",
    "DAL": "Brian Schottenheimer", "LV": "Klint Kubiak", "CLE": "Todd Monken",
    "TEN": "Brian Daboll", "BUF": "Joe Brady", "CIN": "Zac Taylor", "CAR": "Dave Canales",
    "ATL": "Tommy Rees", "TB": "Zac Robinson", "PIT": "Mike McCarthy", "HOU": "Nick Caley",
    "DET": "Drew Petzing", "SEA": "Brian Fleury", "ARI": "Mike LaFleur", "MIA": "Bobby Slowik",
    "PHI": "Sean Mannion", "BAL": "Declan Doyle", "WAS": "David Blough", "NYJ": "Frank Reich",
    "NYG": "Matt Nagy",
}

SEASON_TABLES = {2017: (PC_2017, "espn2017"), 2018: (PC_2018, "fantasyindex2018"),
                 2020: (PC_2020, "yardbarker2020"), 2021: (PC_2021, "yardbarker2021"),
                 2022: (PC_2022, "yardbarker2022"), 2023: (PC_2023, "espn2023"),
                 2024: (PC_2024, "espn2024"), 2025: (PC_2025, "espn2025"),
                 2026: (PC_2026, "fantasyindex2026")}

# ------------------------------------------------------------- explicitly unresolved team-seasons
# Routed to UNKNOWN / league prior. Never resolved by guessing.
AMBIGUOUS = {
    (2021, "MIA"): dict(reason="co-play-callers George Godsey / Eric Studesville; no single "
                               "attributable person", source_key="yardbarker2021"),
    (2022, "NE"): dict(reason="Matt Patricia / Joe Judge shared offensive duties; no single "
                              "attributable play-caller", source_key="yardbarker2022"),
    (2022, "PHI"): dict(reason="CONFLICT: Yardbarker names Nick Sirianni, CBS reports Shane "
                               "Steichen took full-time play-calling for 2022",
                        source_key="cbs2022phi"),
    (2014, "SF"): dict(reason="SHARED: Roman developed the game plan and handed Harbaugh the "
                              "call on the sideline, but 'all calls went through head coach Jim "
                              "Harbaugh'. No single attributable in-game caller and no defensible "
                              "split -> ambiguous, not assigned to either man.",
                       source_key="sf2014shared"),
    (2016, "NO"): dict(reason="SHARED: ESPN 2016-09-14 has Carmichael as 'primary play caller' "
                              "while Payton overrides in-game via headset. No defensible split.",
                       source_key="espn2016no"),
}

# Documented MIDSEASON play-calling changes. Where a defensible effective week exists it is given;
# otherwise the team-season is ambiguous. Sourced from cached Wikipedia team-season prose.
MIDSEASON_CHANGES = {
    (2015, "GB"): dict(from_pc="Tom Clements", to_pc="Mike McCarthy", effective_week=15,
                       source_url="https://en.wikipedia.org/wiki/2015_Green_Bay_Packers_season",
                       note="McCarthy reclaimed play-calling; NFL.com dated December 13, 2015."),
    (2017, "KC"): dict(from_pc="Andy Reid", to_pc="Matt Nagy", effective_week=13,
                       source_url="https://www.cbssports.com/nfl/news/"
                                  "andy-reid-reportedly-cedes-play-calling-duties-to-offensive-"
                                  "coordinator-matt-nagy/",
                       note="CBS 2017-12-03: Reid handed play-calling to Nagy for the Week 13 "
                            "Jets game. Reid retained oversight, so the split is by primary "
                            "in-game caller. Supersedes the earlier undated Wikipedia note."),
    (2018, "CLE"): dict(from_pc="Todd Haley", to_pc="Freddie Kitchens", effective_week=9,
                        source_url="https://www.newsweek.com/hue-jackson-todd-haley-fired-"
                                   "cleveland-browns-midway-through-season-1192594",
                        note="HC Jackson and OC Haley fired 2018-10-29 after Week 8; Kitchens "
                             "promoted and called plays for the remainder."),
    (2020, "CHI"): dict(from_pc="Matt Nagy", to_pc="Bill Lazor", effective_week=11,
                        source_url="https://en.wikipedia.org/wiki/2020_Chicago_Bears_season",
                        note="Nagy relinquished play-calling after the first nine games."),
    (2016, "HOU"): dict(from_pc="George Godsey", to_pc="Bill O'Brien", effective_week=4,
                        source_url="https://www.espn.com/nfl/story/_/id/17676861/"
                                   "houston-texans-coach-bill-obrien-take-play-calling-duties-offense",
                        note="ESPN 2016-09-30: O'Brien took play-calling back from Godsey before "
                             "the Week 4 game. Godsey wks 1-3, O'Brien wks 4-17."),
    (2019, "LAC"): dict(from_pc="Ken Whisenhunt", to_pc="Shane Steichen", effective_week=8,
                        source_url="https://www.chargers.com/news/"
                                   "shane-steichen-assumes-offensive-play-calling-qb-coach",
                        note="chargers.com 2019-10-30: Whisenhunt dismissed 2019-10-28; Steichen "
                             "'will begin calling plays Week 8 against the Green Bay Packers'. "
                             "Lynn: 'I'm going to let (Steichen) call it.'"),
    (2015, "TEN"): dict(from_pc="Ken Whisenhunt", to_pc="Jason Michael", effective_week=9,
                        source_url="https://www.espn.com/blog/tennessee-titans/post/_/id/16730/"
                                   "rookie-play-caller-jason-michael-about-to-debut-for-titans",
                        note="ESPN 2015-11-03: Whisenhunt fired after a 1-6 start having 'called "
                             "plays during all 23 games of his tenure'; OC Jason Michael takes "
                             "the play-calling from wk9."),
    (2016, "BUF"): dict(from_pc="Greg Roman", to_pc="Anthony Lynn", effective_week=3,
                        source_url="https://www.espn.com/nfl/story/_/id/17565671/"
                                   "rex-ryan-firing-buffalo-bills-offensive-coordinator-my-move",
                        note="ESPN 2016-09-16: Roman fired after 0-2; Anthony Lynn assumed "
                             "playcalling from wk3."),
    (2015, "LA"): dict(from_pc="Frank Cignetti", to_pc="Rob Boras", effective_week=14,
                       source_url="https://sports.yahoo.com/blogs/nfl-shutdown-corner/"
                                  "rams-fire-offensive-coordinator-frank-cignetti--rob-boras-promoted-204218400.html",
                       note="Yahoo 2015-12-07 (after wk13): Cignetti fired, Boras named "
                            "coordinator for the final weeks."),
    (2015, "IND"): dict(from_pc="Pep Hamilton", to_pc="Rob Chudzinski", effective_week=9,
                        source_url="https://www.espn.com/blog/indianapolis-colts/post/_/id/17058/"
                                   "colts-oc-rob-chudzinski-putting-his-prints-on-offense-in-first-full-season",
                        note="ESPN 2016-06-14: Chudzinski 'took over as coordinator on a short "
                             "week after Pep Hamilton was fired in Week 9' and 'had control of "
                             "the play-calling'."),
    (2017, "NYG"): dict(from_pc="Ben McAdoo", to_pc="Mike Sullivan", effective_week=6,
                        source_url="https://www.espn.com/nfl/story?id=21082776",
                        note="ESPN 2017-10-19: after an 0-5 start McAdoo 'handed the job to "
                             "Sullivan last week'. Refines the ESPN 2017 32-team row (which lists "
                             "Sullivan) into a split."),
    (2017, "CIN"): dict(from_pc="Ken Zampese", to_pc="Bill Lazor", effective_week=3,
                        source_url="http://profootballtalk.nbcsports.com/2017/09/15/"
                                   "bill-lazor-takes-over-as-bengals-offensive-coordinator/",
                        note="Zampese fired two games into 2017; QB coach Bill Lazor elevated. "
                             "Refines the ESPN 2017 32-team row (which lists Lazor) into a split."),
    (2016, "BAL"): dict(from_pc="Marc Trestman", to_pc="Marty Mornhinweg", effective_week=6,
                        source_url="https://www.baltimoreravens.com/news/"
                                   "ravens-fire-offensive-coordinator-marc-trestman-17854693",
                        note="Ravens official 2016-10-10 (after wk5): Trestman fired, Mornhinweg "
                             "OC 'for the rest of the season'. Mornhinweg is independently "
                             "recorded as Baltimore's play-caller in the ESPN 2017 32-team table."),
    (2016, "MIN"): dict(from_pc="Norv Turner", to_pc="Pat Shurmur", effective_week=9,
                        source_url="https://www.vikings.com/news/"
                                   "norv-turner-resigns-as-vikings-offensive-coordinator-18004050",
                        note="Vikings official 2016-11-02: Turner resigned in his third season "
                             "(2014-2016); TE coach Pat Shurmur assumed the interim OC role and "
                             "play-calling for the remainder."),
    (2016, "JAX"): dict(from_pc="Greg Olson", to_pc="Nathaniel Hackett", effective_week=9,
                        source_url="https://www.espn.com/nfl/story/_/id/17919123/"
                                   "jacksonville-jaguars-fire-offensive-coordinator-greg-olson-promote-qb-coach-nathaniel-hackett",
                        note="ESPN 2016-10-29 (after wk8, 2-5 start): Olson fired, QB coach "
                             "Hackett assumes playcalling for the remainder."),
    (2015, "DET"): dict(from_pc="Joe Lombardi", to_pc="Jim Bob Cooter", effective_week=8,
                        source_url="https://www.espn.com/nfl/story/_/id/13979338/"
                                   "detroit-lions-fire-offensive-coordinator-joe-lombardi-two-ol-coaches",
                        note="ESPN 2015-10-26 (Lions 1-6, after wk7): Lombardi fired; 'Cooter WILL "
                             "CALL PLAYS' upon promotion from QB coach."),
    (2015, "MIA"): dict(from_pc="Bill Lazor", to_pc="Zac Taylor", effective_week=13,
                        source_url="https://www.espn.com/nfl/story/_/id/14258236/"
                                   "miami-dolphins-fire-offensive-coordinator-bill-lazor-promote-zac-taylor",
                        note="ESPN 2015-11-30: Lazor fired; QB coach Zac Taylor takes over "
                             "play-calling 'for the final five games of the season'."),
    (2019, "WAS"): dict(from_pc="Jay Gruden", to_pc="Kevin O'Connell", effective_week=6,
                        source_url="http://dcsportsking.com/2019/10/07/"
                                   "redskins-offensive-coordinator-kevin-oconnell-will-take-over-play-calling/",
                        note="Gruden fired after the Week 5 loss to New England (Washington Post "
                             "2019-10-07); interim HC Callahan confirmed OC Kevin O'Connell would "
                             "take over play-calling. Before the firing the head coach relayed the "
                             "calls. SOURCE TIER NOTE: the firing is major-outlet sourced; the "
                             "play-calling handover rests on regional/secondary outlets - flagged "
                             "for audit."),
    (2021, "DET"): dict(from_pc="Anthony Lynn", to_pc=None, effective_week=9,
                        source_url="https://en.wikipedia.org/wiki/Ben_Johnson_(American_football_coach)",
                        note="Lynn stripped of play-calling after an 0-8 start; successor not "
                             "reliably attributable -> ambiguous."),
}

# Seasons for which NO qualifying play-caller source has been located.
UNSOURCED_SEASONS = [2014, 2015, 2016, 2019]   # no qualifying 32-team source located
