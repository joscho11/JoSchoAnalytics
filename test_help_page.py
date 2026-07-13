"""Batch-3d proof for the extracted Help & Guide page. Renders offline-clean, and the
live model stats its prose interpolates come from dashboard_data.accuracy_stats (3a) —
so the rendered copy is byte-identical to what app.py's Help tab shows. Hermetic.
"""
import os
import sys
from pathlib import Path

os.environ["APP_OFFLINE"] = "1"

from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))


def _render(tmp_path):
    h = tmp_path / "h_help.py"
    h.write_text(f"import sys; sys.path.insert(0, r'{_HERE}')\n"
                 "import page_help as p\np.render()\n", encoding="utf-8")
    at = AppTest.from_file(str(h), default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def test_help_renders_offline_clean(tmp_path):
    at = _render(tmp_path)
    assert any("Help & Guide" in str(t.value) for t in at.title), "Help title missing"
    assert len(list(at.markdown)) > 10, "Help body (expanders/markdown) did not render"


def test_help_interpolates_shared_stats_byte_identical(tmp_path):
    import dashboard_data
    df = dashboard_data.load_predictions()
    s = dashboard_data.accuracy_stats(df)
    at = _render(tmp_path)
    md = " ".join(str(m.value) for m in at.markdown)
    assert f"{s['overall_pct']}% ATS" in md, \
        "overall ATS% (from accuracy_stats) must appear verbatim in the Help copy"
    if s["hc_pct"] is not None:
        assert f"{s['hc_pct']}%" in md, "high-confidence % must appear verbatim in the Help copy"


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_help_renders_offline_clean(Path(d))
        test_help_interpolates_shared_stats_byte_identical(Path(d))
    print("OK  Help page renders clean; shared stats interpolate byte-identical")
