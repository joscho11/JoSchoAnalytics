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
