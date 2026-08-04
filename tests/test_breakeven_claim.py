"""The Help page must never claim a rate beats break-even without comparing it.

Regression of record (2026-08-03): with a real 56.4% overall (66/117) beside a 33.3%
agent high-confidence rate (2/6), the page rendered "Both are above break even, which is
encouraging." The verdict string was selected on `_hc_pct is not None` — on whether the
statistic EXISTED — and never on 52.4. These tests pin the comparison, not the wording's
mere presence.
"""
import os
import re
import sys
from pathlib import Path

import pytest

os.environ["APP_OFFLINE"] = "1"
_HERE = Path(__file__).resolve().parents[1]
for _p in (str(_HERE), str(_HERE / "site_pages"), str(_HERE / "betting")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dashboard_utils import BREAKEVEN_PCT, breakeven_verdict  # noqa: E402

_ABOVE = re.compile(r"\babove\b", re.I)
_BELOW = re.compile(r"\bbelow\b", re.I)
_BOTH_ABOVE = re.compile(r"both are above", re.I)


def test_threshold_constant_matches_the_number_the_page_prints():
    assert BREAKEVEN_PCT == 52.4


# ---- the four mandated cases -------------------------------------------------
def test_overall_above_hc_below_never_says_both_are_above():
    """THE regression case: 66/117 = 56.4% overall, 2/6 = 33.3% high confidence."""
    s = breakeven_verdict(56.4, 33.3)
    assert not _BOTH_ABOVE.search(s), f"claimed both above with a 33.3% rate: {s!r}"
    # It must name BOTH directions, not collapse to one.
    assert _ABOVE.search(s) and _BELOW.search(s), s
    assert "encouraging" not in s.lower(), "must not editorialise over a losing rate"


def test_both_above():
    s = breakeven_verdict(56.4, 64.7)
    assert _BOTH_ABOVE.search(s), s
    assert not _BELOW.search(s), s


def test_both_below():
    s = breakeven_verdict(43.2, 41.0)
    assert _BELOW.search(s) and not _ABOVE.search(s), s
    assert "encouraging" not in s.lower(), s


def test_hc_missing_uses_the_singular_form_and_still_compares():
    assert _ABOVE.search(breakeven_verdict(56.4, None))
    below = breakeven_verdict(43.2, None)
    assert _BELOW.search(below) and not _ABOVE.search(below), below
    assert "encouraging" not in below.lower(), below


# ---- boundary + unavailable --------------------------------------------------
def test_exactly_at_the_threshold_is_not_reported_as_above():
    s = breakeven_verdict(52.4, None)
    assert not _ABOVE.search(s) and not _BELOW.search(s), s
    assert "exactly at" in s.lower(), s


def test_nothing_comparable_renders_no_claim_at_all():
    assert breakeven_verdict(None, None) == ""


@pytest.mark.parametrize("overall,hc", [
    (52.5, None), (52.3, None), (52.4, 52.5), (52.5, 52.3), (0.0, 100.0), (100.0, 0.0),
])
def test_no_output_ever_asserts_above_for_a_rate_that_is_below(overall, hc):
    """Property: a rate strictly below the bar can never appear in an 'above'-only claim."""
    s = breakeven_verdict(overall, hc).lower()
    rates = [r for r in (overall, hc) if r is not None]
    if any(r < BREAKEVEN_PCT for r in rates) and not any(r > BREAKEVEN_PCT for r in rates):
        assert "above" not in s, (overall, hc, s)
    if any(r > BREAKEVEN_PCT for r in rates) and not any(r < BREAKEVEN_PCT for r in rates):
        assert "below" not in s, (overall, hc, s)


# ---- the live tracker, end to end -------------------------------------------
def test_live_repo_data_does_not_render_a_false_claim():
    """Runs against the real tracker + real agent caches, not a fixture."""
    import dashboard_data
    import dashboard_utils as du
    df = du.load_tracker(str(_HERE))
    stats = dashboard_data.accuracy_stats(df)
    s = breakeven_verdict(stats["overall_pct"], stats["hc_pct"])
    if stats["hc_pct"] is not None and stats["hc_pct"] < BREAKEVEN_PCT:
        assert not _BOTH_ABOVE.search(s), (
            f"live data renders a false claim: overall={stats['overall_pct']} "
            f"hc={stats['hc_pct']} -> {s!r}")


def test_rendered_help_page_carries_no_false_break_even_claim():
    """Drive the real page and scan every rendered markdown block."""
    from streamlit.testing.v1 import AppTest
    import dashboard_data
    import dashboard_utils as du

    stats = dashboard_data.accuracy_stats(du.load_tracker(str(_HERE)))
    at = AppTest.from_function(lambda: __import__("page_help").render()).run(timeout=120)
    assert not at.exception, at.exception
    blob = " ".join(str(m.value) for m in at.markdown)
    if stats["hc_pct"] is not None and stats["hc_pct"] < BREAKEVEN_PCT:
        assert not _BOTH_ABOVE.search(blob), "page still claims both rates beat break-even"
        assert not re.search(r"both numbers are above", blob, re.I), blob
