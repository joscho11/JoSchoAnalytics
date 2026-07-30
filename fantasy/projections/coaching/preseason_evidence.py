"""PRESEASON EVIDENCE LEDGER — row-level, one entry per EVIDENCE ITEM.

Answers "who was PUBLICLY ESTABLISHED to be calling plays before season Y began", which is a
strictly harder question than playcaller_sources.py's "who DID call plays". The two are never
merged: a preseason source does NOT overwrite the retrospective attribution source.

=====================================================================================================
RESEARCH STANDARD (corrected by Joseph 2026-07-29)
=====================================================================================================
**A preseason snapshot is ROW-LEVEL. A source does not need to establish all 32 teams.** A qualifying
pre-cutoff article naming one team's actual play-caller establishes THAT ONE ROW. Thirty-two
independent qualifying sources may establish all 32 rows.

My prior pass recovered ZERO rows on the reasoning that "a fragment naming one coach cannot establish
32 identities". That statement is true but irrelevant, and using it to justify recovering nothing was
the error: a fragment establishes exactly the identity it names. This pass is the correction.

QUALIFYING:
  - official team announcements; coach press conferences/transcripts
  - contemporaneous beat reporting; ESPN/NFL reporting; reputable preseason previews
  - preseason football publications that EXPLICITLY name the caller
  - "X will continue calling plays" IS positive evidence

NOT QUALIFYING:
  - job title alone (nominal OC is never promoted)
  - inferring the caller from title, or continuity from silence
  - Week 1 observation; eventual primary caller; midseason information
  - a later article without separately cited pre-cutoff evidence
  - ABSENCE of an announcement is not evidence

Eligibility uses the CONSERVATIVE UPPER BOUND of the publication date against that season's frozen
projection cutoff (day before the season's first regular-season game).
"""

# One dict per EVIDENCE ITEM. Multiple items may target the same (season, team) so that conflicting
# sources stay visible rather than being silently collapsed.
EVIDENCE = [
    # ---------------------------------------------------------------- 2020 (cutoff 2020-09-09)
    *[dict(season=2020, team=t, person_id=p,
           url="https://www.pff.com/news/nfl-best-offensive-play-callers-heading-into-2020-season",
           publisher="PFF", raw_date="Posted Aug 12, 2020 9:15 am EDT", date="2020-08-12",
           precision="exact_day", provenance="page_byline", source_class="preseason_publication",
           statement=f"PFF's preseason ranking of the NFL's best offensive PLAY CALLERS names "
                     f"{p.replace('_', ' ').title()} as the {t} play caller heading into 2020.")
      for t, p in [("KC", "andy_reid"), ("ARI", "kliff_kingsbury"), ("DAL", "kellen_moore"),
                   ("BAL", "greg_roman"), ("SF", "kyle_shanahan")]],

    dict(season=2020, team="CAR", person_id="joe_brady",
         url="https://www.espn.com/blog/carolina-panthers/post/_/id/33978/"
             "panthers-joe-brady-brings-next-gen-approach-and-mystery-to-opener",
         publisher="ESPN", raw_date="David Newton Sep 9, 2020, 06:00 AM ET", date="2020-09-09",
         precision="exact_day", provenance="page_byline", source_class="espn_nfl_reporting",
         statement="Season-opener preview treating Brady as Carolina's play caller: 'Brady hasn't "
                   "called a complete game in his coaching career.' Published ON the 2020 cutoff "
                   "(2020-09-09), before the first regular-season game (2020-09-10)."),

    # ---------------------------------------------------------------- 2021 (cutoff 2021-09-08)
    *[dict(season=2021, team=t, person_id=p,
           url="https://www.pff.com/news/nfl-ranking-best-offensive-play-callers-entering-2021-season",
           publisher="PFF", raw_date="Posted Jun 9, 2021 6:15 am EDT", date="2021-06-09",
           precision="exact_day", provenance="page_byline", source_class="preseason_publication",
           statement=f"PFF's preseason ranking of the NFL's best offensive PLAY CALLERS names "
                     f"{p.replace('_', ' ').title()} as the {t} play caller entering 2021.")
      for t, p in [("GB", "matt_lafleur"), ("BUF", "brian_daboll"), ("KC", "andy_reid"),
                   ("LV", "jon_gruden"), ("CAR", "joe_brady"), ("TB", "byron_leftwich")]],

    dict(season=2021, team="CHI", person_id="matt_nagy",
         url="https://www.cbssports.com/nfl/news/"
             "matt-nagy-returning-to-play-calling-for-bears-offense-enthusiastic-about-andy-dalton-"
             "at-quarterback",
         publisher="CBS Sports", raw_date="April 2, 2021 at 4:45 pm ET", date="2021-04-02",
         precision="exact_day", provenance="page_byline", source_class="coach_press_conference",
         statement="Nagy, first person, on a conference call with reporters: 'I'm going to be the "
                   "one calling plays this year.' Direct statement of play-calling responsibility."),

    # ---------------------------------------------------------------- 2022 (cutoff 2022-09-07)
    *[dict(season=2022, team=t, person_id=p,
           url="https://www.pff.com/news/nfl-ranking-best-offensive-play-callers-2022",
           publisher="PFF", raw_date="Posted Jun 16, 2022 5:45 am EDT", date="2022-06-16",
           precision="exact_day", provenance="page_byline", source_class="preseason_publication",
           statement=f"PFF's preseason ranking of the NFL's best offensive PLAY CALLERS names "
                     f"{p.replace('_', ' ').title()} as the {t} play caller ahead of 2022.")
      for t, p in [("KC", "andy_reid"), ("DAL", "kellen_moore"), ("TB", "byron_leftwich"),
                   ("SF", "kyle_shanahan"), ("LA", "sean_mcvay"), ("GB", "matt_lafleur")]],

    # ---------------------------------------------------------------- 2019 (cutoff 2019-09-04)
    dict(season=2019, team="TB", person_id="byron_leftwich",
         url="https://profootballtalk.nbcsports.com/2019/01/10/"
             "byron-leftwich-will-call-offensive-plays-for-buccaneers/",
         publisher="ProFootballTalk (NBC Sports)", raw_date="January 10, 2019 (URL path date)",
         date="2019-01-10", precision="exact_day", provenance="page_metadata",
         source_class="contemporaneous_reporting",
         statement="Headline states outright that Byron Leftwich WILL CALL offensive plays for the "
                   "Buccaneers. Corroborated by Tampa Bay Times 2019-01-09, 'Bruce Arians: Byron "
                   "Leftwich will be the Buccaneers' offensive play-caller in 2019', reporting "
                   "Arians' announcement on The Rich Eisen Show."),

    dict(season=2019, team="CLE", person_id="freddie_kitchens",
         url="https://dawgpounddaily.com/2019/01/14/"
             "cleveland-browns-freddie-kitchens-calling-plays-hc-not-concern/",
         publisher="Dawg Pound Daily", raw_date="January 14, 2019", date="2019-01-14",
         precision="exact_day", provenance="page_byline", source_class="contemporaneous_reporting",
         statement="Reports Kitchens' own announcement: 'Kitchens announced the expected on "
                   "Monday, saying that he will continue to be the offensive play-caller in 2019, "
                   "despite his new role as the head coach.' The later explicit Kitchens quote "
                   "('That's not gonna happen', ESPN/Tony Grossi) is 2019-09-23 -- POST-cutoff and "
                   "therefore NOT used."),

    # ---------------------------------------------------------------- 2025 (cutoff 2025-09-03)
    # PFSN "2025 NFL Offensive Play-Caller Rankings", 2025-06-25. Ranks all 32 teams explicitly as
    # PLAY-CALLERS (not as coordinators), so it identifies play-calling responsibility rather than
    # job title. 31 of 32 name a single person matching the retrospective opener; NYG names TWO
    # people and is entered below as ambiguous, NOT eligible.
    *[dict(season=2025, team=t, person_id=p,
           url="https://www.profootballnetwork.com/2025-nfl-offensive-play-caller-rankings/",
           publisher="Pro Football Network", raw_date="June 25, 2025 | 10:15 AM EDT",
           date="2025-06-25", precision="exact_day", provenance="page_byline",
           source_class="preseason_publication",
           statement=f"PFSN's 2025 offensive PLAY-CALLER rankings name "
                     f"{p.replace('_', ' ').title()} as the {t} play caller for 2025.")
      for t, p in [
          ("SF", "kyle_shanahan"), ("LA", "sean_mcvay"), ("CHI", "ben_johnson"),
          ("MIN", "kevin_oconnell"), ("GB", "matt_lafleur"), ("KC", "andy_reid"),
          ("DEN", "sean_payton"), ("BAL", "todd_monken"), ("MIA", "mike_mcdaniel"),
          ("BUF", "joe_brady"), ("WAS", "kliff_kingsbury"), ("JAX", "liam_coen"),
          ("CAR", "dave_canales"), ("NO", "kellen_moore"), ("ARI", "drew_petzing"),
          ("CLE", "kevin_stefanski"), ("LV", "chip_kelly"), ("CIN", "zac_taylor"),
          ("IND", "shane_steichen"), ("ATL", "zac_robinson"), ("NE", "josh_mcdaniels"),
          ("PIT", "arthur_smith"), ("SEA", "klint_kubiak"), ("TEN", "brian_callahan"),
          ("LAC", "greg_roman"), ("DAL", "brian_schottenheimer"), ("DET", "john_morton"),
          ("NYJ", "tanner_engstrand"), ("TB", "josh_grizzard"), ("PHI", "kevin_patullo"),
          ("HOU", "nick_caley")]],

    dict(season=2025, team="NYG", person_id="AMBIGUOUS_daboll_or_kafka",
         url="https://www.profootballnetwork.com/2025-nfl-offensive-play-caller-rankings/",
         publisher="Pro Football Network", raw_date="June 25, 2025 | 10:15 AM EDT",
         date="2025-06-25", precision="exact_day", provenance="page_byline",
         source_class="preseason_publication",
         statement="AMBIGUOUS: the entry reads 'Brian Daboll/Mike Kafka, New York Giants' -- it "
                   "names TWO people and does not resolve which would call plays. Not a "
                   "contradiction of the retrospective opener (mike_kafka), but not an unambiguous "
                   "identification either, so it is flagged and REFUSED rather than resolved in "
                   "favour of coverage."),
]

# Back-compat shim for the previous dict-keyed interface.
PRESEASON_EVIDENCE = {(e["season"], e["team"]): e for e in EVIDENCE}

# ---------------------------------------------------------------------------------------------
# AVENUES ATTEMPTED AND REFUSED — kept so the same dead ends are not re-walked.
# ---------------------------------------------------------------------------------------------
AVENUES_ATTEMPTED = {
    "pff_playcaller_series": (
        "PFF's 'best offensive play callers' preseason series is the single highest-yield source "
        "found: it EXPLICITLY ranks play callers (not coordinators) and is published preseason. "
        "Editions located and used: 2020-08-12, 2021-06-09, 2022-06-16. The series names only the "
        "top 5-6 callers per year, so it establishes 5-6 rows per season, not 32. NO 2025 edition "
        "exists (the author left PFF); searched pff.com directly and found none."),
    "fantasyindex_annual": (
        "'Ranking the play callers 1 thru 32' confirmed to run in the target years but the "
        "2020/2021/2022/2025 editions are paywalled/unindexed. Retrievable editions: 2018, "
        "2023-06-15, 2026. The 2023-06-15 edition predates the ESPN 2023-08-23 source already in "
        "use, but 2023 is already at 100% so it would recover nothing."),
    "panthers_com_brady_hire_2020": (
        "REFUSED. panthers.com 2020-01-16 announces Brady as offensive coordinator but the fetch "
        "confirms it does NOT state play-calling responsibility. Title alone is insufficient. "
        "(2020 CAR was instead recovered from the dated ESPN opener preview.)"),
    "browns_stefanski_2020": (
        "REFUSED. The Feb-2020 reporting says Stefanski 'said it's yet to be decided if Van Pelt "
        "will call plays' -- that is explicitly UNDECIDED, so it establishes nothing. Later "
        "sources confirming Stefanski called plays are retrospective."),
    "returning_caller_continuity": (
        "REFUSED ON PRINCIPLE, not availability. That a person called plays late in Y-1 does not "
        "establish he would call them in Y; that is inference from silence. Proposed instead as "
        "labelled sensitivity design C, requiring a separate prefit amendment and Joseph's "
        "approval before any use."),
    "2025_row_level": (
        "RESOLVED for 31 of 32 rows. ESPN's 2025 list (2025-09-09) is six days post-cutoff and no "
        "PFF 2025 edition exists, but PFSN's '2025 NFL Offensive Play-Caller Rankings' "
        "(2025-06-25) covers all 32 teams and ranks them explicitly as PLAY-CALLERS, which is an "
        "identification of play-calling responsibility rather than of job title. 31 entries name a "
        "single person matching the retrospective opener. NYG is the exception -- see below."),
    "2025_NYG": (
        "REFUSED. PFSN's entry reads 'Brian Daboll/Mike Kafka' -- two names, unresolved. Under the "
        "standing rule an ambiguous identification is flagged and refused, never resolved toward "
        "whichever name improves coverage. Needs a separate row-level source naming one person."),
    # ---------------------------------------------------------------------------------------
    # 2019 -- NOT RESOLVED. Dispositions below are honest records of avenues actually walked.
    # ---------------------------------------------------------------------------------------
    "2019_league_wide_sources": (
        "EXHAUSTED WITHOUT RECOVERY. (a) PFF's 2019 play-caller article "
        "(nfl-ranking-the-nfls-top-offensive-play-callers-2019) is explicitly 'through the first "
        "nine weeks of the 2019 season' -- MID-SEASON, post-cutoff, ineligible. (b) The Yardbarker "
        "32-team article at s1__32555903, which surfaced on a 2019 query, fetches as 'Updated "
        "October 22, 2020' covering the 2020 season -- it is the yardbarker2020 source already in "
        "the table, not a 2019 edition. (c) Fantasy Index's annual series: no retrievable 2019 "
        "edition. No qualifying league-wide 2019 preseason source was found."),
    "2019_new_head_coach_cohort": (
        "RE-ATTEMPTED under the v3.5 as-of rule, which removed the wrong reason for the original "
        "refusal (a preseason expectation no longer has to match the eventual opener). The Boston "
        "Globe 2019-01-12 piece was FETCHED: it discusses the new HCs' lack of play-calling "
        "experience but does NOT state who would call plays for any team. Refused on the correct "
        "ground -- it establishes no play-calling responsibility."),
    "2019_TB": (
        "RECOVERED. ProFootballTalk 2019-01-10 headline states Leftwich WILL CALL offensive plays; "
        "Tampa Bay Times 2019-01-09 reports Arians announcing it on The Rich Eisen Show. NOTE: the "
        "earlier pass refused a second-hand claim that Arians himself would call plays. That claim "
        "was simply wrong -- the contemporaneous reporting names Leftwich."),
    "2019_CLE": (
        "STRONG LEAD, NOT ENTERED. Search surfaces that Kitchens said on hiring (January 2019) he "
        "would continue to call plays despite hiring Todd Monken, and that Monken 'agreed to "
        "surrender that role'. Not entered because no byline was FETCHED to confirm the statement "
        "and date on a specific page. Resolve by fetching the SI 2019-01-13 hire piece or the "
        "contemporaneous Cleveland beat coverage."),
    "2019_eight_unresolved_attribution_rows": (
        "SCOPE CORRECTED by v3.5. ARI, ATL, BAL, BUF, DET, NE, NO, NYG have no resolved "
        "retrospective opener, but that NO LONGER excludes them: a qualifying pre-cutoff source "
        "naming the expected caller makes the preseason identity eligible even when the eventual "
        "attribution is never resolved. Previously (wrongly) treated as out of scope. Not yet "
        "individually researched."),
}
