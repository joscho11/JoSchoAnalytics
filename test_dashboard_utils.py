"""Unit tests for dashboard_utils.py (the Streamlit-free helpers extracted from app.py).

Run:  pytest test_dashboard_utils.py    (or: python test_dashboard_utils.py)
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dashboard_utils import (
    load_tracker, load_totals_tracker, _md_to_html, get_confidence, metric_card,
)


# ── _md_to_html ──────────────────────────────────────────────────────────────
def test_md_to_html_bold_and_bullets():
    out = _md_to_html("**Edge** found\n- pick A\n- pick B")
    assert "<strong>Edge</strong>" in out
    assert out.count("&bull;&nbsp;") == 2
    assert "<br>" in out


def test_md_to_html_escapes_html():
    # raw angle brackets must be escaped so agent text can't inject markup
    assert "&lt;script&gt;" in _md_to_html("<script>")


# ── get_confidence ───────────────────────────────────────────────────────────
def test_get_confidence_prefers_explicit_map():
    ga = {"KC_BUF": "🔴 fade"}
    assert get_confidence("KC", "BUF", ga, {"KC_BUF": "HIGH"}) == "HIGH"   # map wins over emoji


def test_get_confidence_emoji_fallback():
    assert get_confidence("KC", "BUF", {"KC_BUF": "🟢 strong"}) == "HIGH"
    assert get_confidence("KC", "BUF", {"KC_BUF": "🟡 lean"}) == "MEDIUM"
    assert get_confidence("KC", "BUF", {"KC_BUF": "🔴 nope"}) == "PASS"


def test_get_confidence_skip_pass_backcompat():
    # legacy cache files used "SKIP"; it maps to PASS
    assert get_confidence("KC", "BUF", {"KC_BUF": "SKIP this one"}) == "PASS"
    assert get_confidence("KC", "BUF", {"KC_BUF": "PASS"}) == "PASS"


def test_get_confidence_no_analysis():
    assert get_confidence("KC", "BUF", {}) == "NO_ANALYSIS"
    assert get_confidence("KC", "BUF", {"KC_BUF": "neutral text"}) == "NO_ANALYSIS"


# ── metric_card ──────────────────────────────────────────────────────────────
def test_metric_card_colors_and_sub():
    assert "#00c853" in metric_card("L", "V", color="green")
    assert "#ff5252" in metric_card("L", "V", color="red")
    assert "#3D95CE" in metric_card("L", "V", color="bogus")   # unknown -> default blue
    with_sub = metric_card("Label", "42", sub="detail")
    assert "Label" in with_sub and "42" in with_sub and "detail" in with_sub
    assert "margin-top:3px" not in metric_card("L", "V")        # no sub div when sub is None


# ── load_tracker / load_totals_tracker ───────────────────────────────────────
def test_load_tracker_reads_and_casts(tmp_path):
    d = tmp_path / "betting"
    d.mkdir()
    pd.DataFrame({"season": ["2025"], "week": ["10"], "x": [1]}).to_csv(d / "predictions_tracker.csv", index=False)
    df = load_tracker(tmp_path)
    assert len(df) == 1
    assert df["season"].dtype.kind == "i" and df["week"].dtype.kind == "i"


def test_load_totals_tracker_missing_returns_empty(tmp_path):
    (tmp_path / "betting").mkdir()
    out = load_totals_tracker(tmp_path)
    assert isinstance(out, pd.DataFrame) and out.empty


def test_load_totals_tracker_reads_when_present(tmp_path):
    d = tmp_path / "betting"
    d.mkdir()
    pd.DataFrame({"season": ["2025"], "week": ["12"]}).to_csv(d / "totals_tracker.csv", index=False)
    out = load_totals_tracker(tmp_path)
    assert len(out) == 1 and out["week"].iloc[0] == 12


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    # tmp_path-based tests need pytest; run only the no-fixture ones standalone
    passed = 0
    for fn in fns:
        if fn.__code__.co_argcount:
            continue
        try:
            fn(); passed += 1; print(f"  ok  {fn.__name__}")
        except Exception:
            print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{passed} no-fixture tests passed (run `pytest test_dashboard_utils.py` for all)")
