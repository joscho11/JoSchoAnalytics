"""Page-level screenshot coverage for every major route.

Extends tests/test_responsive_layout.py (header geometry + hit-testing) with
full-page screenshots at phone, tablet, and desktop widths. Catches wrapping,
table overflow, empty states, publishing badges, and Streamlit chrome drift.

Running it
----------
The catalog/compare tests need no browser. Screenshot cases need playwright
plus Chromium, and SKIP when those are missing, same contract as the header
suite::

    pip install -r requirements-test.txt
    python -m playwright install chromium
    set APP_OFFLINE=1
    pytest tests/test_visual_regression.py -v
    pytest tests/test_visual_regression.py --update-visual

CI job ``responsive`` runs this file and requires zero skips. Copy and layout
run on every OS. Pixel compare runs on Linux (CI Chromium) unless
VISUAL_PIXELS=1. Baselines live in tests/visual/baselines/. Failures write
actual/diff PNGs to tests/visual/artifacts/ (gitignored).
"""
from __future__ import annotations

import ast
import io
import os
import sys
from pathlib import Path

import pytest
from PIL import Image

from playwright_support import (
    VIEWPORTS,
    layout_probe,
    open_route,
    screenshot_png,
    stabilize,
    wait_for_stable_layout,
)
from visual.actions import ACTIONS, run_action
from visual.catalog import (
    ALL_VIEWPORTS,
    LAYERS,
    LH_TABS,
    NAV_ROUTES,
    SCENES,
    cases,
)
from visual.compare import compare_png

_REPO = Path(__file__).resolve().parents[1]
_BASELINES = _REPO / "tests" / "visual" / "baselines"
_ARTIFACTS = _REPO / "tests" / "visual" / "artifacts"
_APP = _REPO / "app.py"


_CASES = cases()
_CASE_IDS = [f"{scene.id}__{viewport}" for scene, viewport in _CASES]


def test_catalog_covers_every_nav_route():
    covered = {scene.nav_route for scene in SCENES}
    missing = set(NAV_ROUTES) - covered
    assert not missing, f"no visual scene for routes: {sorted(missing)}"


def test_catalog_matches_app_py_url_paths():
    tree = ast.parse(_APP.read_text(encoding="utf-8"))
    paths = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "Page"):
            continue
        for keyword in node.keywords:
            if keyword.arg == "url_path" and isinstance(keyword.value, ast.Constant):
                paths.append(keyword.value.value)
    assert sorted(paths) == sorted(NAV_ROUTES)


def test_catalog_covers_every_layer_and_league_tab():
    used = {scene.layer for scene in SCENES}
    assert set(LAYERS) <= used
    blob = " ".join(
        scene.id + " " + " ".join(scene.must_contain) for scene in SCENES
    )
    for tab in LH_TABS:
        assert tab in blob, f"League History tab {tab!r} is not in the visual catalog"


def test_every_nav_route_has_phone_tablet_desktop():
    covered: dict[str, set[str]] = {}
    for scene in SCENES:
        covered.setdefault(scene.nav_route, set()).update(scene.viewports)
    for route in NAV_ROUTES:
        missing = set(ALL_VIEWPORTS) - covered.get(route, set())
        assert not missing, f"route {route!r} is missing viewports {sorted(missing)}"


def test_catalog_actions_are_registered():
    for scene in SCENES:
        if scene.action:
            assert scene.action in ACTIONS, f"{scene.id} action {scene.action!r} is unknown"


def test_catalog_covers_publishing_badge_states():
    blob = " ".join(" ".join(scene.must_contain) for scene in SCENES)
    for status in ("Published", "Awaiting projections"):
        assert status in blob, f"publishing status {status!r} has no screenshot scene"


def test_snapshot_compare_detects_mismatch(tmp_path):
    def png(color, size=(12, 8)):
        buffer = io.BytesIO()
        Image.new("RGB", size, color).save(buffer, format="PNG")
        return buffer.getvalue()

    baseline = tmp_path / "base.png"
    baseline.write_bytes(png((10, 20, 30)))
    same = compare_png(png((10, 20, 30)), baseline)
    assert same.ok and same.ratio == 0.0
    different = compare_png(png((200, 0, 0)), baseline)
    assert not different.ok and different.diff_png
    sized = compare_png(png((10, 20, 30), size=(4, 4)), baseline)
    assert not sized.ok and "size" in sized.reason


def test_app_today_freeze(monkeypatch):
    import seasonal_config as cfg

    monkeypatch.delenv("APP_TODAY", raising=False)
    live = cfg.app_today()
    monkeypatch.setenv("APP_TODAY", "2026-08-24")
    assert cfg.app_today().isoformat() == "2026-08-24"
    assert live is not None


def test_visual_league_fixture_is_id_gated(monkeypatch):
    import page_league_history as page

    fixture = _REPO / "tests" / "visual" / "fixtures" / "league_history.json"
    monkeypatch.setenv("JSA_VISUAL_LH_FIXTURE", str(fixture))
    hit = page._visual_history_payload("1255197436951932928")
    miss = page._visual_history_payload("111111111111111111")
    assert hit is not None and hit["league_name"] == "Test League"
    assert miss is None


def test_visual_fixture_load_renders_intelligence_tabs(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    fixture = _REPO / "tests" / "visual" / "fixtures" / "league_history.json"
    monkeypatch.setenv("APP_OFFLINE", "1")
    monkeypatch.setenv("JSA_VISUAL_LH_FIXTURE", str(fixture))
    harness = tmp_path / "visual_lh.py"
    harness.write_text(
        "import os\n"
        "os.environ['APP_OFFLINE'] = '1'\n"
        f"os.environ['JSA_VISUAL_LH_FIXTURE'] = r'{fixture}'\n"
        f"import sys; sys.path[:0] = [r'{_REPO}', r'{_REPO / 'site_pages'}']\n"
        "import page_league_history as p\n"
        "p._OFFLINE = True\n"
        "p.render()\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(harness), default_timeout=180).run()
    next(w for w in at.text_input if w.key == "lh_league_id").set_value(
        "1255197436951932928"
    )
    next(b for b in at.button if b.label == "Load league history").click()
    at.run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    assert any(t.value == "Test League" for t in at.header)
    labels = [tab.label for tab in at.tabs]
    for tab in LH_TABS:
        assert any(tab in label for label in labels), labels


def test_linux_has_every_baseline_png(update_visual):
    if update_visual or not sys.platform.startswith("linux"):
        return
    expected = {f"{case_id}.png" for case_id in _CASE_IDS}
    found = {path.name for path in _BASELINES.glob("*.png")}
    missing = sorted(expected - found)
    assert not missing, (
        f"{len(missing)} visual baselines missing. "
        "On ubuntu-latest Chromium: pytest tests/test_visual_regression.py --update-visual"
    )


def test_long_pages_capture_below_the_fold(update_visual):
    """Streamlit scrolls inside stApp. A viewport-tall PNG misses wrapping."""
    if update_visual:
        return
    mins = {
        "wp_published_2025w10__phone.png": 3500,
        "wp_graded_2025w17__phone.png": 3500,
        "track_record_2025__phone.png": 3500,
        "draft_board__desktop.png": 1500,
        "home__phone.png": 1200,
    }
    missing = [name for name in mins if not (_BASELINES / name).exists()]
    if missing:
        if not sys.platform.startswith("linux"):
            return
        pytest.fail(f"missing full-page baselines: {missing}")
    for name, min_h in mins.items():
        height = Image.open(_BASELINES / name).size[1]
        assert height >= min_h, (
            f"{name} is {height}px tall, need >= {min_h}. "
            "screenshot_png must expand Streamlit scroll containers before capture."
        )


def _pixel_compare_enabled() -> bool:
    if os.environ.get("VISUAL_PIXELS") == "1":
        return True
    return sys.platform.startswith("linux")


@pytest.mark.visual
@pytest.mark.parametrize("scene,viewport", _CASES, ids=_CASE_IDS)
def test_page_screenshot(browser, app_url, update_visual, scene, viewport):
    spec = VIEWPORTS[viewport]
    ctx = browser.new_context(
        viewport={"width": spec["width"], "height": spec["height"]},
        is_mobile=spec["is_mobile"],
        has_touch=spec["has_touch"],
        color_scheme="dark",
        device_scale_factor=1,
        reduced_motion="reduce",
    )
    try:
        page = ctx.new_page()
        open_route(page, app_url, scene.path, scene.query)
        run_action(page, scene.action)
        stabilize(page)
        for needle in scene.must_contain:
            page.wait_for_function(
                """(needle) => {
                  const main = document.querySelector('[data-testid="stMainBlockContainer"]');
                  const extra = [...document.querySelectorAll(
                    '[data-testid="stBadge"], [data-testid="stCaption"], [data-testid="stAlert"]'
                  )].map(el => el.innerText || '').join('\\n');
                  const text = ((main && main.innerText) || '') + '\\n' + extra
                    + '\\n' + (document.body.innerText || '');
                  return text.includes(needle);
                }""",
                arg=needle,
                timeout=20_000,
            )
        stabilize(page)

        wait_for_stable_layout(page)
        probe = layout_probe(page)
        text = probe.get("text") or ""
        missing = [needle for needle in scene.must_contain if needle not in text]
        leaked = [needle for needle in scene.must_not_contain if needle in text]
        layout_issues = list(probe.get("issues") or [])
        assert not missing, f"{scene.id} missing copy {missing} at {viewport}"
        assert not leaked, f"{scene.id} leaked copy {leaked} at {viewport}"
        assert not layout_issues, f"{scene.id} @{viewport}: " + "; ".join(layout_issues)

        png = screenshot_png(page)
        with Image.open(io.BytesIO(png)) as captured:
            width, height = captured.size
        assert width == spec["width"], (
            f"{scene.id} @{viewport}: screenshot width {width} != {spec['width']}"
        )
        assert height >= spec["height"], (
            f"{scene.id} @{viewport}: screenshot height {height} < viewport {spec['height']}"
        )
        name = f"{scene.id}__{viewport}.png"
        baseline = _BASELINES / name
        _ARTIFACTS.mkdir(parents=True, exist_ok=True)
        if update_visual:
            _BASELINES.mkdir(parents=True, exist_ok=True)
            baseline.write_bytes(png)
            return
        if not _pixel_compare_enabled():
            return
        if not baseline.exists():
            return
        result = compare_png(png, baseline)
        if result.ok:
            return
        actual_path = _ARTIFACTS / name
        actual_path.write_bytes(png)
        if result.diff_png:
            (_ARTIFACTS / f"{scene.id}__{viewport}.diff.png").write_bytes(result.diff_png)
        pytest.fail(
            f"{scene.id} @{viewport}: {result.reason}. "
            f"actual={actual_path.relative_to(_REPO)}"
        )
    finally:
        ctx.close()
