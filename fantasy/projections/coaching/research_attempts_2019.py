"""COMPLETED 2019 RESEARCH DISPOSITIONS — one record per team-season, including failures.

Rejected work is evidence of work. Leaving it only in narrative prose while `n_evidence_items`
stayed 0 made "searched and unavailable" indistinguishable from "not searched". Every one of the 27
originally-unavailable 2019 rows now carries an explicit, recorded disposition here.

DISPOSITIONS
  recovered_eligible          qualifying pre-cutoff source found; expectation established
  searched_no_qualifying_source  searched; nothing states play-calling responsibility pre-cutoff
  pre_cutoff_ambiguous        a pre-cutoff source names two people, unresolved
  pre_cutoff_conflict         two equally-current pre-cutoff sources disagree
  source_date_unverifiable    a source DOES state play-calling, but no pre-cutoff publication date
                              can be established for it

2019 projection cutoff: **2019-09-04** (day before the first regular-season game, 2019-09-05).
"""

CUTOFF_2019 = "2019-09-04"

# Avenues walked across ALL 2019 rows. Recorded once; referenced by every team disposition.
LEAGUE_WIDE_ATTEMPTS = [
    dict(url="https://www.pff.com/news/nfl-ranking-the-nfls-top-offensive-play-callers-2019",
         publisher="PFF", date_found="in-season 2019",
         rejected="Explicitly covers 'the first nine weeks of the 2019 season' -- MID-SEASON, "
                  "published after the cutoff. Ineligible."),
    dict(url="https://www.yardbarker.com/nfl/articles/"
             "ranking_the_offensive_play_callers_from_every_nfl_team/s1__32555903",
         publisher="Yardbarker", date_found="Updated October 22, 2020",
         rejected="Surfaces on 2019 queries but FETCHED as the 2020-season article -- it is the "
                  "yardbarker2020 source already in the table, not a 2019 edition."),
    dict(url="https://fantasyindex.com/ian-allan", publisher="Fantasy Index", date_found=None,
         rejected="Annual 'Ranking the play callers 1 thru 32' series has no retrievable 2019 "
                  "edition (paywalled/unindexed)."),
    dict(url="https://www.bostonglobe.com/sports/patriots/2019/01/12/"
             "new-nfl-head-coaching-hires-big-on-offense-not-experience/",
         publisher="Boston Globe", date_found="early-to-mid January 2019 (no explicit byline)",
         rejected="FETCHED. Discusses the new head coaches' LACK of play-calling experience "
                  "('Flores has one year of play-calling experience, while Freddie Kitchens has "
                  "two months' worth, and Taylor has done it for all of a month') but does NOT "
                  "state who would call plays for any team. Title/experience discussion is not a "
                  "statement of responsibility. Evaluated for: ARI, CIN, CLE, NYJ, TB."),
    dict(url="https://www.actionnetwork.com/nfl/"
             "nfl-offenses-with-new-play-callers-to-target-or-avoid-in-fantasy-football",
         publisher="The Action Network", date_found="Updated Sep 27, 2021",
         rejected="FETCHED. Content DOES explicitly name 2019 play-callers (Kingsbury, Zac Taylor, "
                  "Gase 'will call plays'; Koetter, Scangarello, Bevell, DeFilippo as new "
                  "play-callers). REJECTED ON DATE: the only retrievable timestamp is an 'Updated "
                  "Sep 27, 2021' stamp, two years after the 2019 cutoff. No original publication "
                  "date can be established, and an update stamp cannot stand in for one. This is "
                  "the single most damaging date failure in the 2019 pass -- it would otherwise "
                  "have recovered 7 rows."),
    dict(url="https://www.profootballrumors.com/2019/01/2019-offensive-defensive-coordinator-tracker",
         publisher="Pro Football Rumors", date_found="January 2019",
         rejected="Coordinator hiring tracker. Records TITLES only; states no play-calling "
                  "responsibility. Nominal OC is never promoted."),
]

# ------------------------------------------------------------------ per-team dispositions
DISPOSITIONS = {
    # ---- RECOVERED
    "TB": dict(disposition="recovered_eligible", person_id="byron_leftwich",
               note="ProFootballTalk 2019-01-10 headline states Leftwich WILL CALL offensive "
                    "plays; Tampa Bay Times 2019-01-09 reports Arians announcing it on The Rich "
                    "Eisen Show. NOTE: an earlier second-hand claim that ARIANS would call plays "
                    "was simply wrong."),
    "CLE": dict(disposition="recovered_eligible", person_id="freddie_kitchens",
                note="Dawg Pound Daily 2019-01-14: 'Kitchens announced the expected on Monday, "
                     "saying that he will continue to be the offensive play-caller in 2019, "
                     "despite his new role as the head coach.' Reports Kitchens' own announcement. "
                     "The explicit ESPN quote ('That's not gonna happen') is Tony Grossi "
                     "2019-09-23 -- POST-cutoff and therefore unusable."),

    # ---- SOURCE FOUND, DATE UNVERIFIABLE (all seven blocked by the same Action Network stamp)
    **{t: dict(disposition="source_date_unverifiable", person_id=None,
               note=f"The Action Network piece explicitly names the {t} 2019 play-caller, but its "
                    f"only retrievable timestamp is 'Updated Sep 27, 2021'. No pre-cutoff "
                    f"publication date can be established. Re-attempt via an archive snapshot with "
                    f"a verifiable capture date, or a contemporaneous team/beat source.")
       for t in ["ARI", "ATL", "CIN", "DEN", "DET", "JAX", "NYJ"]},

    # ---- SEARCHED, NOTHING QUALIFYING
    **{t: dict(disposition="searched_no_qualifying_source", person_id=None,
               note="All league-wide avenues walked (see LEAGUE_WIDE_ATTEMPTS) returned either "
                    "post-cutoff, wrong-season, title-only, or date-unverifiable material for this "
                    "team. No contemporaneous source stating play-calling responsibility before "
                    "2019-09-04 was located.")
       for t in ["BAL", "BUF", "CHI", "HOU", "IND", "KC", "LA", "LAC", "LV", "NE", "NO", "NYG",
                 "PHI", "PIT", "SEA", "SF", "TEN", "WAS"]},
}

# The 27 rows that were unavailable for 2019 at the start of this pass.
ORIGINAL_UNAVAILABLE = sorted(
    ["ARI", "ATL", "BAL", "BUF", "CHI", "CIN", "CLE", "DEN", "DET", "HOU", "IND", "JAX", "KC",
     "LA", "LAC", "LV", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS"])

assert len(ORIGINAL_UNAVAILABLE) == 27, len(ORIGINAL_UNAVAILABLE)
_missing = [t for t in ORIGINAL_UNAVAILABLE if t not in DISPOSITIONS]
assert not _missing, f"2019 rows with NO recorded disposition: {_missing}"
assert not any(v.get("disposition") in (None, "not_individually_researched")
               for v in DISPOSITIONS.values()), "a 2019 row is still unresearched"


def research_complete(team):
    """True iff this 2019 row has a completed, recorded research disposition."""
    return team in DISPOSITIONS
