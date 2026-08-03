"""Responsive regression check for the site header — geometry AND real hit-testing.

Why this exists
---------------
Every defect this guards against was invisible to the existing AppTest suite, because
AppTest proves a page *renders*; none of these were render failures. They were layout
failures that only exist in a browser at a given viewport width:

  * The fixed brand/tip-jar overlay (`#jsa-topbar`) sat at z-index 999992, above BOTH
    Streamlit's header (999990) and its nav drawer (999991). With the drawer open the
    overlay swallowed taps aimed at the drawer's close control — `elementFromPoint` at
    that control's centre returned the Venmo anchor.
  * The header's right inset (13rem) was narrower than the tip-jar pill (~194px), so
    Streamlit's `⋮` main menu sat *underneath* the pill at every width from 641px up.

Both are geometry, so the test is geometry: it asks the browser where things actually
are and what is actually on top, in BOTH drawer states.

Running it
----------
The nine browser cases need `playwright` plus a Chromium build and SKIP cleanly when
either is missing, so CI and a plain ``pytest tests`` stay green without them::

    pip install playwright && playwright install chromium
    pytest tests/test_responsive_layout.py -v

``test_check_exemptions_are_narrow`` takes no fixtures and always runs — it pins the
assertion logic itself, so the rules stay covered in CI where no browser is installed.
The interpreter running pytest must also have `streamlit` — `app_url` launches the real
app with ``APP_OFFLINE=1`` on a free port, and depends on `browser` so that server is
never started when the browser prerequisite is absent.

Touch, not hover
----------------
Every width below 768px is driven with ``has_touch=True`` and exercised with a real
``tap()``. Nothing here hovers. Streamlit hides the drawer's collapse control above its
own 576px ``sm`` breakpoint and reveals it on sidebar *hover*, which on a phone or tablet
means never — so from 577px to 767px the drawer could be opened and not closed from its
own control. That is fixed in ``render_header`` (forced visible while the drawer is open),
not tolerated here, and this file is what holds that fix in place.

What is deliberately NOT asserted
---------------------------------
Controls *behind* an open drawer. At 320px Streamlit's 300px drawer legitimately covers
its own `⋮` menu; occluding the background is what a modal drawer is for. The exemption
is narrow and explicit: a background control may be occluded ONLY by an element inside
the drawer. Anything else — our overlay above all — is a failure, and the drawer's own
close control is never exempt.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

# Optional import, NOT importorskip. A module-level importorskip skips the whole file
# before collection, which took the browser-free logic test down with the nine browser
# cases — so the assertion logic went untested in CI, which is the one place it is
# guaranteed to run. Import failure is recorded and turned into a skip by the `browser`
# fixture instead, so only the tests that actually need a browser are skipped.
try:                                              # pragma: no cover - env dependent
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT_IMPORT_ERROR = None
except ImportError as _exc:                       # pragma: no cover - env dependent
    sync_playwright = None
    _PLAYWRIGHT_IMPORT_ERROR = _exc

_REPO = Path(__file__).resolve().parents[1]

# Widths that matter, and why:
#   320  smallest phone still in use              640  Streamlit's column-stack breakpoint
#   390  iPhone 14/15                             641  first width above it
#   700  large phone landscape / small tablet     767  last width served by the drawer
#   768  first width with the nav inline          1440 desktop
WIDTHS = [320, 390, 640, 641, 700, 767, 768, 1440]

# Streamlit's own breakpoints, read off the shipped bundle. Kept as named constants so a
# future upgrade that moves them shows up here rather than as a mystery failure.
ST_BREAKPOINT_SM = 576       # upstream, the collapse control is hover-revealed above this;
                             # render_header overrides that while the drawer is open
ST_BREAKPOINT_NAV = 768      # nav moves out of the drawer and into the header at this


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _chromium_kwargs() -> dict:
    """Prefer a playwright-managed browser; fall back to any cached build."""
    cache = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    for exe in sorted(cache.glob("chromium-*/chrome-win64/chrome.exe"), reverse=True):
        return {"executable_path": str(exe)}
    for exe in sorted(cache.glob("chromium-*/chrome-linux/chrome"), reverse=True):
        return {"executable_path": str(exe)}
    return {}


@pytest.fixture(scope="module")
def browser():
    """The browser prerequisite. Skips — and ONLY this fixture skips — when playwright
    or a Chromium build is unavailable. Everything that needs a browser depends on it,
    directly or through `app_url`, so a missing browser never starts a server."""
    if sync_playwright is None:
        pytest.skip(f"playwright not installed ({_PLAYWRIGHT_IMPORT_ERROR})")
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(**_chromium_kwargs())
        except Exception as exc:                       # no browser binary available
            pytest.skip(f"no chromium available: {str(exc).splitlines()[0][:120]}")
        try:
            yield b
        finally:
            b.close()


@pytest.fixture(scope="module")
def app_url(browser):
    """Depends on `browser` on purpose: launching a Streamlit server takes seconds and
    is pure waste when the browser prerequisite is already missing. Requesting it here
    means the skip happens first and this body never runs."""
    port = _free_port()
    env = {**os.environ, "APP_OFFLINE": "1", "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.port", str(port), "--server.headless", "true",
         "--browser.gatherUsageStats", "false", "--server.fileWatcherType", "none"],
        cwd=str(_REPO), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        # A missing browser is an environment gap and may skip. A server that will not
        # start is the APP being broken, and must never be reported as "skipped" —
        # that is exactly how a real regression hides behind a green run.
        for _ in range(120):
            if proc.poll() is not None:
                pytest.fail(f"streamlit exited during startup (rc={proc.returncode}) — "
                            f"the app itself is broken, not the test environment")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.5)
        else:
            pytest.fail("streamlit did not accept connections within 60s — "
                        "the app itself is broken, not the test environment")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


# One evaluate() call returns everything: geometry, computed visibility, and the result
# of elementFromPoint at each control's centre. Controls that are off-canvas or
# deliberately hidden report skip=True — hit-testing them would measure nothing.
_PROBE = """() => {
  const q = s => document.querySelector(s);
  const bar = q('#jsa-topbar');
  const barHidden = bar && getComputedStyle(bar).visibility === 'hidden';
  const vw = document.documentElement.clientWidth;
  // Selected structurally, NOT by the classes this work happened to add: a selector
  // that can silently match nothing is not evidence, and `tip` missing would make the
  // whole overlap check quietly vacuous. test_probe_finds_every_control asserts these
  // are all present, so a markup change fails loudly instead of passing by absence.
  const ctrls = {
    navBtn:   q('[data-testid="stExpandSidebarButton"]'),
    mainMenu: q('[data-testid="stMainMenuButton"]'),
    tip:      q('#jsa-topbar a[href]'),
    brand:    q('#jsa-topbar span'),
    close:    q('[data-testid="stSidebarCollapseButton"]'),
  };
  const out = {
    vw, scrollW: document.documentElement.scrollWidth,
    barZ: bar ? getComputedStyle(bar).zIndex : null,
    barHidden,
    sidebarZ: q('section[data-testid="stSidebar"]')
              ? getComputedStyle(q('section[data-testid="stSidebar"]')).zIndex : null,
    aria: q('section[data-testid="stSidebar"]')
          ? q('section[data-testid="stSidebar"]').getAttribute('aria-expanded') : null,
    ctrl: {},
  };
  for (const [name, el] of Object.entries(ctrls)) {
    if (!el) { out.ctrl[name] = null; continue; }
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const box = {l: Math.round(r.left), r: Math.round(r.right),
                 t: Math.round(r.top), b: Math.round(r.bottom)};
    const off = r.width === 0 || r.right <= 0 || r.left >= vw || r.bottom <= 0;
    const hid = cs.visibility === 'hidden' || cs.display === 'none'
                || (barHidden && el.closest('#jsa-topbar'));
    if (off || hid) { out.ctrl[name] = {box, skip: off ? 'offscreen' : 'hidden'}; continue; }
    const hit = document.elementFromPoint((r.left + r.right) / 2, (r.top + r.bottom) / 2);
    out.ctrl[name] = {
      box,
      ok: !!hit && (el === hit || el.contains(hit)),
      // Who is on top matters: only the modal drawer earns an exemption.
      inTopbar: !!hit && !!hit.closest('#jsa-topbar'),
      inSidebar: !!hit && !!hit.closest('section[data-testid="stSidebar"]'),
      got: hit ? (hit.tagName.toLowerCase()
                  + (hit.getAttribute('data-testid') ? '[' + hit.getAttribute('data-testid') + ']' : '')
                  + (hit.id ? '#' + hit.id : '')) : '<null>',
    };
  }
  return out;
}"""

_OVERLAP_PAIRS = [("brand", "navBtn"), ("tip", "navBtn"), ("tip", "mainMenu"),
                  ("brand", "tip"), ("tip", "close"), ("brand", "close")]


def _x_overlap(a, b):
    if not a or not b:
        return 0
    dx = min(a["r"], b["r"]) - max(a["l"], b["l"])
    dy = min(a["b"], b["b"]) - max(a["t"], b["t"])
    return dx if dx > 0 and dy > 0 else 0


# Interactive controls that must be the topmost thing at their own centre whenever the
# drawer is CLOSED — no exemptions, whatever the blocker turns out to be.
_MUST_BE_REACHABLE_CLOSED = ("navBtn", "mainMenu", "tip")


def _check(state, width, label, drawer_open, must_exist=()):
    """Return a list of human-readable problems for one probe result.

    Closed state: every visible interactive control must be reachable, full stop.
    Open state: background controls may be occluded, but ONLY by the drawer itself;
    the drawer's own close control is never exempt.

    ``must_exist`` names controls that have to be PRESENT at this width. Without it a
    page that failed to render passes vacuously — every control absent means nothing to
    overlap and nothing to hit-test. That is not a hypothetical: it is exactly what
    happened at 768/1440 when the app was deliberately broken.
    """
    problems = []
    for name in must_exist:
        if state["ctrl"].get(name) is None:
            problems.append(f"{name} is absent from the DOM — page did not render as expected")

    live = {k: v for k, v in state["ctrl"].items() if v and not v.get("skip")}

    if state["scrollW"] > state["vw"] + 1:
        problems.append(f"page scrolls horizontally ({state['scrollW']} > {state['vw']})")

    for x, y in _OVERLAP_PAIRS:
        if x in live and y in live:
            ov = _x_overlap(live[x]["box"], live[y]["box"])
            if ov:
                problems.append(f"{x} overlaps {y} by {ov}px")

    for name, c in live.items():
        if c["ok"]:
            continue
        culprit = " (OUR OVERLAY)" if c["inTopbar"] else ""
        blocked = f"elementFromPoint at {name} centre -> {c['got']}{culprit}"

        if not drawer_open:
            if name in _MUST_BE_REACHABLE_CLOSED or name == "close":
                problems.append(blocked)
            continue

        # Drawer open.
        if name == "close":
            problems.append(blocked + " — the drawer's own close control")
        elif not c["inSidebar"]:
            problems.append(blocked + " — occluded by something that is NOT the drawer")
        # else: background control behind the modal drawer; explicitly exempt.
    return [f"[{width}px {label}] {p}" for p in problems]


def _ctrl(ok=True, in_topbar=False, in_sidebar=False, got="div", box=None):
    return {"box": box or {"l": 0, "r": 10, "t": 0, "b": 10},
            "ok": ok, "inTopbar": in_topbar, "inSidebar": in_sidebar, "got": got}


def _state(**ctrl):
    return {"vw": 390, "scrollW": 390, "ctrl": ctrl}


def test_check_exemptions_are_narrow():
    """Pin the assertion logic itself, without a browser.

    These are the rules that were previously too loose: the closed state only reported a
    blocked control when OUR overlay happened to be the blocker, so any other regression
    passed silently.
    """
    # Closed: a blocked interactive control is a failure whatever blocked it. The blocker
    # here is neither our overlay nor the drawer — previously this was reported as clean.
    for name in ("navBtn", "mainMenu", "tip"):
        problems = _check(_state(**{name: _ctrl(ok=False, got="div[somethingElse]")}),
                          390, "closed", drawer_open=False)
        assert problems, f"closed-state block of {name} must be reported"
        assert "somethingElse" in problems[0]

    # Closed: a reachable control is fine.
    assert not _check(_state(navBtn=_ctrl(ok=True)), 390, "closed", drawer_open=False)

    # Open: a BACKGROUND control occluded by the drawer is exempt — that is what a modal
    # drawer is for — but only when the drawer is genuinely the occluder.
    assert not _check(_state(mainMenu=_ctrl(ok=False, in_sidebar=True,
                                            got="div[stSidebarContent]")),
                      320, "drawer-open", drawer_open=True)
    blocked_by_us = _check(_state(mainMenu=_ctrl(ok=False, in_topbar=True, got="a")),
                           700, "drawer-open", drawer_open=True)
    assert blocked_by_us and "OUR OVERLAY" in blocked_by_us[0]
    assert "NOT the drawer" in blocked_by_us[0]

    # Open: the drawer's OWN close control is never exempt, not even by the drawer.
    close_blocked = _check(_state(close=_ctrl(ok=False, in_sidebar=True,
                                              got="div[stSidebarHeader]")),
                           700, "drawer-open", drawer_open=True)
    assert close_blocked and "close control" in close_blocked[0]

    # Horizontal overflow is reported in either state.
    over = _state(navBtn=_ctrl())
    over["scrollW"] = 500
    assert any("scrolls horizontally" in p for p in
               _check(over, 390, "closed", drawer_open=False))

    # An ABSENT control is a failure, not a free pass. Without must_exist an unrendered
    # page has nothing to overlap and nothing to hit-test, so every check passes.
    empty = {"vw": 390, "scrollW": 390, "ctrl": {"tip": None, "brand": None}}
    assert not _check(empty, 390, "closed", drawer_open=False), "sanity: no requirements, no problems"
    missing = _check(empty, 390, "closed", drawer_open=False, must_exist=("tip", "brand"))
    assert len(missing) == 2 and all("absent from the DOM" in p for p in missing)


def test_probe_finds_every_control(browser, app_url):
    """The overlap/hit assertions are only meaningful if the probe actually located the
    controls. Without this, deleting the tip jar (or renaming the overlay) would make
    every other test in this file pass by matching nothing."""
    ctx = browser.new_context(viewport={"width": 390, "height": 844},
                              is_mobile=True, has_touch=True)
    try:
        page = ctx.new_page()
        page.goto(app_url + "/", wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_selector('[data-testid="stMainBlockContainer"]', timeout=30_000)
        page.wait_for_timeout(2500)
        ctrl = page.evaluate(_PROBE)["ctrl"]
        missing = [n for n in ("navBtn", "mainMenu", "tip", "brand") if ctrl.get(n) is None]
        assert not missing, f"probe could not find: {missing} — the checks below would be vacuous"
    finally:
        ctx.close()


@pytest.mark.parametrize("width", WIDTHS)
def test_header_controls_are_reachable(browser, app_url, width):
    """No overlap, no h-scroll, and every visible control is the topmost thing at its
    own centre — in the closed state AND with the nav drawer open."""
    # Touch everywhere the drawer is the nav. No mouse, so nothing can be hover-revealed:
    # a control a finger cannot reach is unreachable, whatever a desktop pointer would do.
    touch = width < ST_BREAKPOINT_NAV
    ctx = browser.new_context(viewport={"width": width, "height": 844},
                              is_mobile=touch, has_touch=touch)
    try:
        page = ctx.new_page()
        page.goto(app_url + "/", wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_selector('[data-testid="stMainBlockContainer"]', timeout=30_000)
        page.wait_for_timeout(2500)

        # The drawer trigger only exists below the nav breakpoint; the rest are on every
        # width. Asserting presence makes each width self-proving instead of trusting a
        # single sanity test at one width.
        required = ("tip", "brand", "mainMenu") + (("navBtn",) if touch else ())
        problems = _check(page.evaluate(_PROBE), width, "closed",
                          drawer_open=False, must_exist=required)

        if touch:
            # The nav lives behind the drawer here, so the drawer is load-bearing.
            page.locator('[data-testid="stExpandSidebarButton"]').first.tap()
            page.wait_for_timeout(1200)

            state = page.evaluate(_PROBE)
            assert state["aria"] == "true", f"[{width}px] drawer did not open"
            problems += _check(state, width, "drawer-open", drawer_open=True,
                               must_exist=("close",))

            # The overlay must stand down for the drawer: hidden, or painted below it.
            if not state["barHidden"]:
                bar_z, side_z = int(state["barZ"] or 0), int(state["sidebarZ"] or 0)
                if bar_z > side_z:
                    problems.append(
                        f"[{width}px drawer-open] topbar z-index {bar_z} is above the "
                        f"drawer's {side_z}; it will swallow drawer taps")

            # Above Streamlit's own sm breakpoint the collapse control is hover-revealed
            # upstream; render_header forces it visible while the drawer is open. Assert
            # that directly, so the fix cannot silently disappear.
            close = state["ctrl"].get("close")
            if close is None:
                problems.append(f"[{width}px drawer-open] no collapse control in the DOM")
            elif close.get("skip") == "hidden":
                problems.append(
                    f"[{width}px drawer-open] collapse control is visibility:hidden with the "
                    f"drawer open — hover-only, so unreachable on touch")

            # A REAL TAP, not a click and not a dispatched event.
            try:
                page.locator('[data-testid="stSidebarCollapseButton"]').first.tap(timeout=5000)
                page.wait_for_timeout(1000)
                after = page.evaluate(
                    """() => {const s = document.querySelector('section[data-testid="stSidebar"]');
                              return s ? s.getAttribute('aria-expanded') : 'gone';}""")
                if after != "false":
                    problems.append(
                        f"[{width}px] tapping the drawer close control left "
                        f"aria-expanded={after!r}")
            except Exception as exc:
                problems.append(
                    f"[{width}px] drawer close control not tappable: "
                    f"{str(exc).splitlines()[0][:120]}")

        assert not problems, "\n".join(problems)
    finally:
        ctx.close()
