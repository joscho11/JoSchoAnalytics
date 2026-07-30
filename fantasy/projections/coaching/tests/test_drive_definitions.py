"""One exact drive mapping, imported by every builder.

The v3.3 fix lived only in build_segment_offense.py; build_team_offense_panel.py and
build_allocation_panel.py kept `str.contains("Touchdown")` for six more revisions, which credits
'Opp touchdown' -- an OPPONENT defensive/return score -- to the offense as +7.
"""
import pathlib
import re
import sys

import pandas as pd
import pytest

COACH = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(COACH))

import drive_definitions as DD   # noqa: E402

BUILDERS = ["build_team_offense_panel.py", "build_allocation_panel.py", "build_segment_offense.py"]


def test_opp_touchdown_scores_zero_for_the_offense():
    assert DD.DRIVE_POINTS["Opp touchdown"] == 0.0
    assert DD.DRIVE_POINTS["Touchdown"] == 7.0
    assert DD.OFFENSIVE_TD == "Touchdown"


def test_only_exact_touchdown_counts_as_an_offensive_td():
    s = pd.Series(["Touchdown", "Opp touchdown", "Punt"])
    assert list(DD.is_offensive_td(s)) == [True, False, False]
    # the defect, demonstrated
    assert list(s.str.contains("Touchdown", case=False)) == [True, True, False]


def test_drive_points_maps_every_category_exactly():
    s = pd.Series(["Touchdown", "Field goal", "Safety", "Opp touchdown", "Punt",
                   "Turnover", "Turnover on downs", "Missed field goal", "End of half",
                   "End of game"])
    assert list(DD.drive_points(s)) == [7.0, 3.0, -2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def test_unmapped_category_raises_rather_than_scoring_zero():
    with pytest.raises(AssertionError):
        DD.drive_points(pd.Series(["Touchdown", "Some New Category"]))


def test_no_builder_uses_substring_touchdown_matching():
    offenders = []
    for f in BUILDERS:
        # Strip comments first: build_segment_offense.py quotes the forbidden pattern in prose to
        # document why it is banned. A prose mention is not a call site.
        code = "\n".join(line.split("#")[0]
                         for line in (COACH / f).read_text(encoding="utf-8").splitlines())
        if re.search(r'contains\(\s*["\']Touchdown', code):
            offenders.append(f)
    assert not offenders, f"substring TD matching survives in {offenders}"


def test_every_builder_imports_the_shared_mapping():
    for f in BUILDERS:
        src = (COACH / f).read_text(encoding="utf-8")
        assert "drive_definitions" in src, f"{f} does not import the shared mapping"


def test_canonical_proxy_names_are_live_and_retired_names_are_gone():
    panel = pd.read_csv(COACH / "data" / "team_offense_panel.csv")
    assert DD.PPD_PROXY in panel.columns
    assert DD.PPG_PROXY in panel.columns
    for retired in DD.RETIRED_NAMES:
        assert retired not in panel.columns, f"retired name {retired} is still live"
