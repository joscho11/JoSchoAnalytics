"""Batch-1 proof for the multipage nav skeleton (app.py).

Asserts: the default landing page is Weekly Predictions (always — the seasonal
default was retired 2026-07-14), the sidebar renders EMPTY (nav is top, footer is
in page flow), the shared footer is present, and the shared modules are import-safe.
Hermetic: APP_OFFLINE=1 so no network. Run: pytest test_site_nav.py
"""
import os
import sys
from pathlib import Path

os.environ["APP_OFFLINE"] = "1"   # set before importing streamlit-touching modules

from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
ENTRY = str(_HERE / "app.py")   # the multipage entrypoint (post-3e swap)


def _run():
    at = AppTest.from_file(ENTRY, default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def _titles(at):
    return " ".join(str(t.value) for t in at.title)


def test_default_is_weekly_predictions():
    # Weekly Predictions is the fixed landing page year-round (ruling 2026-07-14);
    # the real page titles "🏈 Week N Predictions: SEASON Season" (only this page
    # carries "Predictions").
    at = _run()
    assert "Predictions" in _titles(at), \
        f"default landing page should be Weekly Predictions; titles={_titles(at)!r}"
    assert "Draft Board" not in _titles(at), \
        f"Draft Board must no longer be the default; titles={_titles(at)!r}"


def test_preseason_demo_banner_shows_then_hides():
    # pre-season: the Weekly Predictions demo banner is shown and points to the board
    os.environ["BOARD_REFRESH_SEASON_START"] = "2099-01-01"
    at = _run()
    infos = " ".join(str(i.value) for i in at.info)
    assert "demo until the 2026 season" in infos, "pre-season demo banner missing"
    assert "Draft Board is live and in production" in infos, \
        "banner must point visitors to the in-production Draft Board"
    # in-season: the banner is gone
    os.environ["BOARD_REFRESH_SEASON_START"] = "2000-01-01"
    at = _run()
    infos = " ".join(str(i.value) for i in at.info)
    assert "demo until the 2026 season" not in infos, \
        "demo banner must auto-hide once the season has started"
    os.environ.pop("BOARD_REFRESH_SEASON_START", None)


def test_sidebar_is_empty_and_footer_present():
    at = _run()
    # nav is position="top"; nothing writes to the sidebar -> empty
    assert len(list(at.sidebar.markdown)) == 0, "sidebar must carry no markdown"
    # the tip jar moved UP into the header, so it is no longer a button anywhere
    assert not any(getattr(b, "key", None) == "tip_jar_btn" for b in at.button), \
        "the footer tip-jar button must be gone (tip jar moved to the header)"
    caps = " ".join(str(c.value) for c in at.caption)
    assert "buy me a coffee" not in caps, "the coffee caption must not remain in the footer"
    # footer now carries only the centered public-repo line (an st.markdown, not a caption)
    md = " ".join(str(m.value) for m in at.markdown)
    assert "github.com/joscho11/BettingEdgeContinued" in md, "footer repo link missing"


def test_header_has_brand_and_tip_jar():
    at = _run()
    # the persistent header strip carries the brand (left) and the tip jar (right),
    # moved byte-identical from the old footer — both live in one markdown div.
    hdr = [str(m.value) for m in at.markdown
           if "JoScho Analytics" in str(m.value) and "Tip Jar — Venmo @JoScho" in str(m.value)]
    assert hdr, "header strip (brand + tip jar) must render on the page"
    assert "https://venmo.com/u/JoScho" in hdr[0], "tip jar must keep the byte-identical Venmo URL"
    assert "buy me a coffee ☕" in hdr[0], "the coffee line travels byte-identical as the tip-jar title"
    # and it must NOT be duplicated as a footer button
    assert not any(getattr(b, "key", None) == "tip_jar_btn" for b in at.button), \
        "tip jar must not remain in the footer"


def test_shared_modules_import_safe():
    # importing the shared modules must not fire network/data work at import time
    import dashboard_data
    import dashboard_chrome
    for fn in ("load_predictions", "load_totals", "load_calibration"):
        assert hasattr(dashboard_data, fn)
    for fn in ("send_ga_event", "inject_css", "render_header", "render_footer", "site_pageview_once"):
        assert hasattr(dashboard_chrome, fn)


if __name__ == "__main__":
    test_default_is_weekly_predictions()
    test_preseason_demo_banner_shows_then_hides()
    test_sidebar_is_empty_and_footer_present()
    test_header_has_brand_and_tip_jar()
    test_shared_modules_import_safe()
    print("OK  nav skeleton: WP fixed default, empty sidebar, header brand+tip jar, footer repo link")
