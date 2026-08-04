"""Pure, Streamlit-free helpers for the dashboard (app.py).

Extracted from app.py so the logic-bearing pieces are unit-testable without a
Streamlit runtime (app.py itself is integration-tested via streamlit AppTest in
test_app_draft_board.py). Everything here is a pure function — no `st.*` calls,
no module-level globals — so it can be imported and tested in isolation.

Tested by test_dashboard_utils.py (run in CI).
"""
import html as _html
import re as _re
from pathlib import Path

import pandas as pd


# ── Data loaders (parameterized by base dir so they're testable with a fixture) ──
def load_tracker(base_dir):
    """Load betting/predictions_tracker.csv under ``base_dir`` (raises if missing)."""
    path = str(Path(base_dir) / "betting" / "predictions_tracker.csv")
    df = pd.read_csv(path)
    df["season"] = df["season"].astype(int)
    df["week"] = df["week"].astype(int)
    return df


def load_totals_tracker(base_dir):
    """Load betting/totals_tracker.csv under ``base_dir``; empty DataFrame if absent."""
    path = Path(base_dir) / "betting" / "totals_tracker.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df["season"] = df["season"].astype(int)
    df["week"] = df["week"].astype(int)
    return df


# ── Presentation / parsing helpers ──────────────────────────────────────────────
def _md_to_html(text: str) -> str:
    """Convert simple agent-analysis markdown to HTML for use inside a <details> block."""
    escaped = _html.escape(text)
    escaped = _re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped)
    lines = []
    for line in escaped.split('\n'):
        stripped = line.strip()
        if stripped.startswith('- '):
            lines.append(f'&bull;&nbsp;{stripped[2:]}')
        else:
            lines.append(stripped)
    return '<br>'.join(lines)


def get_confidence(home, away, game_analysis, game_confidence=None):
    key = f"{home}_{away}"
    if game_confidence and key in game_confidence:
        return game_confidence[key]
    # fall back to emoji detection for cache files written before game_confidence was added
    text = game_analysis.get(key, '')
    if '🟢' in text:
        return 'HIGH'
    elif '🟡' in text:
        return 'MEDIUM'
    elif '🔴' in text or 'SKIP' in text.upper() or 'PASS' in text.upper():
        return 'PASS'  # tier renamed from SKIP; keep SKIP detection for old cache compat
    else:
        return 'NO_ANALYSIS'


def metric_card(label, value, sub=None, color="blue"):
    # The jsa-mcard* classes are inert on desktop; mobile.py keys on them to lay these
    # tiles out two-up instead of stacking four deep on a phone. Markup and copy are
    # otherwise unchanged.
    border = {"green": "#00c853", "red": "#ff5252", "blue": "#3D95CE"}.get(color, "#3D95CE")
    sub_html = (f"<div class='jsa-mcard-sub' style='font-size:13px;color:#aaa;margin-top:3px'>"
                f"{sub}</div>") if sub else ""
    return (
        f"<div class='jsa-mcard' style='background:#1e2a3a;border-left:4px solid {border};"
        f"border-radius:6px;padding:14px 16px;margin-bottom:4px;'>"
        f"<div class='jsa-mcard-label' style='font-size:11px;color:#666;text-transform:uppercase;"
        f"letter-spacing:1px;margin-bottom:6px'>{label}</div>"
        f"<div class='jsa-mcard-value' style='font-size:22px;font-weight:700;color:white;"
        f"line-height:1.1'>{value}</div>"
        f"{sub_html}</div>"
    )


# ---------------------------------------------------------------------------
# Break-even comparison copy
# ---------------------------------------------------------------------------
# BREAKEVEN_PCT is the SAME number the surrounding page copy prints as the
# break-even threshold. It is expressed in percent (not a 0-1 rate) because the
# rates it is compared against (`accuracy_stats`' overall_pct / hc_pct) are
# percentages rounded to one decimal.
#
# Why this function exists: the Help page used to select its verdict sentence on
# `_hc_pct is not None` — i.e. on whether the high-confidence statistic EXISTED,
# never on whether either rate cleared the bar. With a real 56.4% overall beside
# a 33.3% high-confidence rate it rendered "Both are above break even, which is
# encouraging." Every branch below is chosen by an ACTUAL comparison, and no
# branch asserts a rate clears the bar without having compared it.
BREAKEVEN_PCT = 52.4


def _side(pct, breakeven):
    """'above' / 'below' / 'exactly at' for one rate. None is not comparable."""
    if pct is None:
        return None
    pct = float(pct)
    if pct > breakeven:
        return "above"
    if pct < breakeven:
        return "below"
    return "exactly at"


def breakeven_verdict(overall_pct, hc_pct, breakeven=BREAKEVEN_PCT):
    """A truthful sentence comparing the displayed rate(s) to break-even.

    `overall_pct` and `hc_pct` are percentages (56.4 means 56.4%), or None when
    the statistic is unavailable. Returns '' when nothing is comparable, so the
    caller renders no claim at all rather than a default one.

    The sentence never editorialises ("which is encouraging") unless every rate
    it covers is actually above the bar — an encouraging gloss on a losing
    number is the exact defect this replaces.
    """
    o = _side(overall_pct, breakeven)
    h = _side(hc_pct, breakeven)
    bar = f"{breakeven}%"

    if o is None and h is None:
        return ""
    if o is None:
        return f"The high-confidence rate is {h} the {bar} break-even threshold."
    if h is None:
        if o == "above":
            return f"That is above the {bar} break-even threshold, which is encouraging."
        if o == "below":
            return f"That is below the {bar} break-even threshold."
        return f"That is exactly at the {bar} break-even threshold."

    if o == h == "above":
        return f"Both are above the {bar} break-even threshold, which is encouraging."
    if o == h == "below":
        return f"Both are below the {bar} break-even threshold."
    if o == h == "exactly at":
        return f"Both are exactly at the {bar} break-even threshold."
    # Mixed: state each side explicitly. Never collapse to "both".
    return (f"The overall rate is {o} the {bar} break-even threshold and the "
            f"high-confidence rate is {h} it.")


# ---------------------------------------------------------------------------
# Agent artifact gate — STRUCTURAL, fail-closed
# ---------------------------------------------------------------------------
# betting/agent_analysis_2025_week10.json shipped 14 "Sharp Money" and 14 "Line Movement"
# assertions ("45% sharp vs 60% public", "opened 3.5 now 2.5") generated entirely from the
# hardcoded WEEK_10_LINES dict in betting/sports_betting_agent.ipynb, and the Weekly
# Predictions page rendered them as analysis.
#
# The first fix was a KEYWORD FILTER over the free-form text. That was wrong, and it was
# demonstrated wrong: the payload
#     "Market opened -3.5 and is now -2.5; 45% professionals back the dog"
# contains no banned phrase and survived untouched. Free text cannot be policed by
# enumeration -- any list of markers is a list of the paraphrases someone already thought
# of. A longer list is not a fix.
#
# THE RULE NOW: an agent artifact is rendered ONLY if it carries provenance naming a source
# adapter on the APPROVED allowlist. Anything else is REJECTED WHOLE -- the loader returns
# None and nothing from that file reaches the page, including its confidence tiers. There is
# no partial acceptance, no scrubbing, and no inference of permission from free text.
#
# APPROVED_MARKET_ADAPTERS IS DELIBERATELY EMPTY. No real market-data adapter exists in this
# repo, so today NO agent artifact can be rendered. That is the intended state. Adding a
# name here is a deliberate act that must be accompanied by an adapter that actually fetches
# and stamps market data; a self-asserted "verified": true is NOT machine verification and
# is rejected by construction (see test_agent_market_provenance.py).
APPROVED_MARKET_ADAPTERS = frozenset()

# Every field an approved adapter must stamp. `source_adapter` is the load-bearing one --
# it is checked against the allowlist, so an artifact cannot vouch for itself.
REQUIRED_MARKET_PROVENANCE = (
    "source_adapter", "adapter_version", "source", "captured_at",
)


def market_provenance_ok(payload):
    """(ok, reason) — is this artifact's provenance attested by an APPROVED adapter?"""
    if not isinstance(payload, dict):
        return False, "payload is not a mapping"
    prov = payload.get("provenance")
    if not isinstance(prov, dict):
        return False, "no provenance block"
    market = prov.get("market_data")
    if not isinstance(market, dict):
        return False, "no provenance.market_data block"
    missing = [k for k in REQUIRED_MARKET_PROVENANCE if k not in market]
    if missing:
        return False, f"provenance.market_data missing {sorted(missing)}"
    adapter = market.get("source_adapter")
    if not isinstance(adapter, str) or not adapter.strip():
        return False, "provenance.market_data.source_adapter is empty"
    if adapter not in APPROVED_MARKET_ADAPTERS:
        return False, (f"source_adapter {adapter!r} is not on the approved allowlist "
                       f"{sorted(APPROVED_MARKET_ADAPTERS)!r} — self-declared provenance "
                       "is not machine verification")
    for field in ("source", "captured_at", "adapter_version"):
        v = market.get(field)
        if not isinstance(v, str) or not v.strip():
            return False, f"provenance.market_data.{field} is empty"
    return True, "ok"


def agent_artifact_status(payload):
    """('approved'|'rejected', reason). Rejection is whole-artifact and final."""
    ok, reason = market_provenance_ok(payload)
    return ("approved" if ok else "rejected"), reason


def sanitize_agent_analysis(payload):
    """(payload_or_None, report).

    An artifact whose provenance is not attested by an approved adapter is REJECTED
    ENTIRELY — this returns ``None``, not a scrubbed copy. Callers must treat ``None`` as
    "there is no agent analysis for this week", which is the truth: an artifact whose
    market claims cannot be verified has no verifiable content at all, and its confidence
    tiers were themselves reasoned from those claims.
    """
    status, reason = agent_artifact_status(payload)
    report = {"status": status, "provenance_ok": status == "approved", "reason": reason}
    if status != "approved":
        return None, report
    return payload, report
