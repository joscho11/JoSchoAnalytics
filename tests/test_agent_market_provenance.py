"""The agent gate is STRUCTURAL and fail-closed. Free text is never policed by keyword.

Regression of record (2026-08-03): `betting/agent_analysis_2025_week10.json` carried 14
"Sharp Money" and 14 "Line Movement" assertions produced by the hardcoded `WEEK_10_LINES`
dict in `betting/sports_betting_agent.ipynb`, and the Weekly Predictions page rendered them.

Second regression (same day): the FIRST fix was a keyword filter over the free-form text,
and it was demonstrably defeated by an ordinary paraphrase carrying no banned phrase. The
gate is now structural — an artifact without adapter-attested provenance is rejected
WHOLE — and these tests exist to stop anyone re-introducing enumeration.
"""
import glob
import json
import os
import sys
from pathlib import Path

import pytest

os.environ["APP_OFFLINE"] = "1"
_HERE = Path(__file__).resolve().parents[1]
for _p in (str(_HERE), str(_HERE / "site_pages"), str(_HERE / "betting")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import dashboard_utils as du  # noqa: E402
from dashboard_utils import (agent_artifact_status,  # noqa: E402
                             market_provenance_ok, sanitize_agent_analysis)

_TIERS = {"SEA_ARI": "HIGH"}


def _payload(text, provenance=None):
    p = {"game_analysis": {"SEA_ARI": text}, "game_confidence": dict(_TIERS)}
    if provenance is not None:
        p["provenance"] = provenance
    return p


def _approved_prov():
    return {"market_data": {
        "source_adapter": "odds_api_v4",
        "adapter_version": "1.2.0",
        "source": "The Odds API v4 /historical",
        "captured_at": "2026-09-10T13:00:00Z",
    }}


# ---------------------------------------------------------------------------
# RED: paraphrases that defeated the old keyword filter
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text,why", [
    ("Market opened -3.5 and is now -2.5; 45% professionals back the dog",
     "THE reported evasion: no 'Line Movement', no 'Sharp Money'"),
    ("45% professionals versus 60% bettors",
     "sharp/public split with both trigger words paraphrased away"),
    ("The number steamed from 6 to 7.5 overnight",
     "steam move, no marker phrase"),
    ("Money is coming in on the underdog while the number moves the other way",
     "reverse line movement, described not named"),
    ("Wiseguy money hit this at open; it has since ticked a half point",
     "slang paraphrase"),
    ("Opened 3.5, now 2.5 (down 1.0)", "bare numeric line move"),
])
def test_paraphrased_market_claims_cannot_render(text, why):
    """No enumeration required: the whole artifact is refused for lack of provenance."""
    payload = _payload(text)
    status, reason = agent_artifact_status(payload)
    assert status == "rejected", f"{why}: gate accepted it ({reason})"
    clean, report = sanitize_agent_analysis(payload)
    assert clean is None, f"{why}: artifact was not rejected whole, got {clean!r}"
    assert report["provenance_ok"] is False


# ---------------------------------------------------------------------------
# RED: self-declared verification is not verification
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("prov,why", [
    (None, "no provenance"),
    ({}, "empty provenance"),
    ({"market_data": {}}, "empty market_data"),
    ({"market_data": {"verified": True}},
     "the old self-asserted boolean, now meaningless on its own"),
    ({"market_data": {"source_adapter": "my_own_adapter", "adapter_version": "1",
                      "source": "internal", "captured_at": "2026-09-10"}},
     "well-formed but the adapter is NOT on the allowlist"),
    ({"market_data": {"source_adapter": "odds_api_v4", "adapter_version": "1",
                      "source": "The Odds API", "captured_at": ""}},
     "approved adapter name but an empty timestamp"),
    ({"market_data": {"source_adapter": "", "adapter_version": "1",
                      "source": "x", "captured_at": "t"}},
     "empty adapter name"),
])
def test_unapproved_or_self_declared_provenance_is_refused(prov, why):
    payload = _payload("Sharp Money: 45% sharp vs 60% public", prov)
    ok, reason = market_provenance_ok(payload)
    assert ok is False, f"{why}: accepted ({reason})"
    assert sanitize_agent_analysis(payload)[0] is None, why


def test_verified_true_alone_is_not_machine_verification():
    """Explicit: the exact shape the previous gate honoured must now fail."""
    payload = _payload("Line Movement: opened 3.5 now 2.5",
                       {"market_data": {"source": "The Odds API",
                                        "captured_at": "2026-09-10", "verified": True}})
    ok, reason = market_provenance_ok(payload)
    assert ok is False
    assert "source_adapter" in reason, reason


def test_the_production_allowlist_is_empty():
    """No real adapter exists, so nothing may render today. Changing this is deliberate."""
    assert du.APPROVED_MARKET_ADAPTERS == frozenset(), (
        "an adapter was allowlisted — it must ship with a real market-data adapter and "
        "its own tests")


# ---------------------------------------------------------------------------
# GREEN: a genuine adapter-attested artifact is allowed through
# ---------------------------------------------------------------------------
def test_valid_structured_artifact_from_an_allowlisted_adapter_is_approved(monkeypatch):
    monkeypatch.setattr(du, "APPROVED_MARKET_ADAPTERS", frozenset({"odds_api_v4"}))
    payload = _payload("Line Movement: opened 3.5 now 2.5", _approved_prov())
    ok, reason = market_provenance_ok(payload)
    assert ok is True, reason
    clean, report = sanitize_agent_analysis(payload)
    assert clean is not None and report["status"] == "approved"
    # An approved artifact passes through INTACT — no scrubbing, no rewriting.
    assert clean["game_analysis"]["SEA_ARI"] == payload["game_analysis"]["SEA_ARI"]
    assert clean["game_confidence"]["SEA_ARI"] == "HIGH"


def test_approval_is_revoked_when_the_adapter_leaves_the_allowlist(monkeypatch):
    payload = _payload("Line Movement: opened 3.5 now 2.5", _approved_prov())
    monkeypatch.setattr(du, "APPROVED_MARKET_ADAPTERS", frozenset({"odds_api_v4"}))
    assert sanitize_agent_analysis(payload)[0] is not None
    monkeypatch.setattr(du, "APPROVED_MARKET_ADAPTERS", frozenset())
    assert sanitize_agent_analysis(payload)[0] is None


# ---------------------------------------------------------------------------
# The public loading path and the statistics path
# ---------------------------------------------------------------------------
def test_the_fabricated_artifact_is_out_of_the_public_path():
    assert not (_HERE / "betting" / "agent_analysis_2025_week10.json").exists()
    assert (_HERE / "betting" / "quarantine" / "agent_analysis_2025_week10.json").exists(), \
        "quarantined artifact must be retained, not deleted"
    assert glob.glob(str(_HERE / "betting" / "agent_analysis_*.json")) == []


def test_loader_rejects_an_unverified_artifact_planted_on_the_real_path():
    import page_common
    target = _HERE / "betting" / "agent_analysis_2099_week1.json"
    assert not target.exists(), "fixture name collides with a real artifact"
    target.write_text(json.dumps(_payload("Opened 3.5, now 2.5")), encoding="utf-8")
    try:
        assert page_common.load_agent_analysis(1, 2099) is None, \
            "loader returned an artifact with unattested provenance"
    finally:
        target.unlink()


def test_unverified_tiers_are_excluded_from_dashboard_statistics():
    """A rejected artifact must contribute ZERO high-confidence games.

    The tiers are downstream of the market claims, so counting them would smuggle the
    rejected artifact into a headline accuracy number.
    """
    import pandas as pd

    import dashboard_data

    target = _HERE / "betting" / "agent_analysis_2099_week1.json"
    payload = {
        "game_analysis": {"AAA_BBB": "Opened 3.5, now 2.5; pros on the dog"},
        "game_confidence": {"AAA_BBB": "HIGH"},
    }
    target.write_text(json.dumps(payload), encoding="utf-8")
    df = pd.DataFrame([{"season": 2099, "week": 1, "home_team": "AAA",
                        "away_team": "BBB", "ens_model_correct": 1.0}])
    try:
        dashboard_data._compute_hc_stats.clear()
        hc_correct, hc_total = dashboard_data._compute_hc_stats("ens_model_correct", df)
        assert (hc_correct, hc_total) == (0, 0), (
            f"rejected artifact leaked {hc_correct}/{hc_total} into the HC statistic")
    finally:
        target.unlink()
        dashboard_data._compute_hc_stats.clear()


# ---------------------------------------------------------------------------
# Generation and publication stay disabled
# ---------------------------------------------------------------------------
def test_the_weekly_workflow_cannot_regenerate_or_commit_the_artifact():
    wf = (_HERE / ".github" / "workflows" / "weekly_predictions.yml").read_text(
        encoding="utf-8")
    live = "\n".join(ln for ln in wf.splitlines()
                     if ln.strip() and not ln.strip().startswith("#"))
    assert "sports_betting_agent.ipynb" not in live, \
        "the agent notebook is executed by an active workflow step"
    assert "agent_analysis_" not in live, \
        "the workflow still stages agent_analysis_*.json for commit"


def test_help_page_no_longer_claims_market_inputs():
    src = (_HERE / "site_pages" / "page_help.py").read_text(encoding="utf-8")
    banned = ["sharp money likes that team", "sharp money is going the other way",
              "line movement data,", "Maybe sharp money is split",
              "the agent will flag it in the matchup analysis"]
    hits = [b for b in banned if b in src]
    assert hits == [], f"help page still claims market inputs: {hits}"
    assert "don't have sharp-money" in src, "the explicit disclaimer is missing"


def test_no_keyword_scrubber_was_reintroduced():
    """Enumerating market phrases is the defeated design; it must not come back."""
    src = (_HERE / "dashboard_utils.py").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    for banned in ("_MARKET_CLAIM_MARKERS", "_strip_market_lines", "_MOCK_SOURCE_TOKENS"):
        assert banned not in code, (
            f"{banned} is back — free text cannot be policed by enumeration; "
            "reject the artifact instead")
