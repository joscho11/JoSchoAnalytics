"""Batch-3c proof for the extracted Weekly Fantasy + League History pages. Each renders
offline-clean and owns its own controls (filter independence); League History lands on an
EMPTY league-ID box with the resting prompt (the earlier fix survives extraction).
Hermetic (APP_OFFLINE=1).
"""
import os
import sys
from pathlib import Path

os.environ["APP_OFFLINE"] = "1"

from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))


def _render_page(tmp_path, module):
    h = tmp_path / f"h_{module}.py"
    h.write_text(f"import sys; sys.path.insert(0, r'{_HERE}')\n"
                 f"import {module} as p\np.render()\n", encoding="utf-8")
    at = AppTest.from_file(str(h), default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def _control_keys(at):
    return {getattr(w, "key", None) for w in list(at.selectbox) + list(at.slider)}


def test_weekly_fantasy_renders_and_owns_controls(tmp_path):
    at = _render_page(tmp_path, "page_weekly_fantasy")
    keys = _control_keys(at)
    assert {"wf_season", "wf_week"} <= keys, f"Weekly Fantasy must own Season+Week; got {keys}"
    assert not any(str(k).startswith(("wp_", "tr_")) for k in keys), \
        "Weekly Fantasy must not carry another page's controls"


def test_league_history_renders_and_lands_empty(tmp_path):
    at = _render_page(tmp_path, "page_league_history")
    ti = [t for t in at.text_input if getattr(t, "key", None) == "lh_league_id"]
    assert ti, "League History must render its league-ID input"
    assert ti[0].value == "", "League History must land on an EMPTY league-ID box"
    info = " ".join(str(i.value) for i in at.info)
    assert "Enter your Sleeper league ID" in info, "resting-state prompt must be shown"


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        test_weekly_fantasy_renders_and_owns_controls(p)
        test_league_history_renders_and_lands_empty(p)
    print("OK  WF owns wf_* controls; LH lands empty with the resting prompt")
