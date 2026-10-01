"""Shared Playwright + Streamlit process helpers for browser suites.

Used by the header geometry suite and the page-level visual suite. Fixtures live
in tests/conftest.py so both files share one Chromium and one Streamlit process.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_VISUAL_DIR = _REPO / "tests" / "visual"
LH_FIXTURE = _VISUAL_DIR / "fixtures" / "league_history.json"
FROZEN_TODAY = "2026-08-24"

ST_BREAKPOINT_SM = 576
ST_BREAKPOINT_STACK = 640
ST_BREAKPOINT_NAV = 768

VIEWPORTS = {
    "phone": {"width": 390, "height": 844, "is_mobile": True, "has_touch": True},
    "tablet": {"width": 768, "height": 1024, "is_mobile": True, "has_touch": True},
    "desktop": {"width": 1440, "height": 900, "is_mobile": False, "has_touch": False},
}

_STABILIZE_CSS = """
[data-testid="stStatusWidget"],
[data-testid="stToolbar"],
[data-testid="stDecoration"] { visibility: hidden !important; }
iframe, video, [data-testid="stIFrame"],
.js-plotly-plot .main-svg, .js-plotly-plot canvas {
  visibility: hidden !important;
}
* { caret-color: transparent !important; }
html { scrollbar-width: none !important; }
::-webkit-scrollbar { width: 0 !important; height: 0 !important; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0s !important;
    animation-delay: 0s !important;
    transition-duration: 0s !important;
  }
}
"""

_LAYOUT_PROBE = r"""() => {
  const vw = document.documentElement.clientWidth;
  const issues = [];
  const scrollW = document.documentElement.scrollWidth;
  if (scrollW > vw + 1) {
    issues.push('page scrolls horizontally (' + scrollW + ' > ' + vw + ')');
  }
  const main = document.querySelector('[data-testid="stMainBlockContainer"]');
  if (!main) {
    issues.push('stMainBlockContainer missing');
    return {vw, scrollW, issues, text: ''};
  }
  if (main.scrollWidth > vw + 1) {
    issues.push('main column overflows (' + main.scrollWidth + ' > ' + vw + ')');
  }
  const selectors = [
    '[data-testid="stDataFrame"]',
    '[data-testid="stTable"]',
    '[class*="st-key-jsa-gc"]',
    '[class*="st-key-jsa-metric"]',
    '[data-testid="stMetric"]',
    '.js-plotly-plot',
  ];
  for (const sel of selectors) {
    for (const el of document.querySelectorAll(sel)) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      let parent = el.parentElement;
      let horizontallyScrollable = false;
      while (parent && parent !== document.body) {
        const style = getComputedStyle(parent);
        if (["auto", "scroll", "overlay"].includes(style.overflowX) &&
            parent.scrollWidth > parent.clientWidth + 1) {
          const bounds = parent.getBoundingClientRect();
          if (bounds.left >= -1 && bounds.right <= vw + 1) {
            horizontallyScrollable = true;
            break;
          }
        }
        parent = parent.parentElement;
      }
      if (r.right > vw + 2 && !horizontallyScrollable) {
        issues.push(sel + ' overflows viewport (right=' + Math.round(r.right) + ')');
        break;
      }
    }
  }
  const extra = [...document.querySelectorAll(
    '[data-testid="stBadge"], [data-testid="stCaption"], [data-testid="stAlert"]'
  )].map(el => el.innerText || '').join('\n');
  const text = ((main.innerText || '') + '\n' + extra + '\n' + (document.body.innerText || '')).slice(0, 40000);
  return {vw, scrollW, issues, text};
}"""


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def chromium_kwargs() -> dict:
    """Prefer a playwright-managed browser for this OS. Ignore the other OS cache."""
    if sys.platform.startswith("linux"):
        cache = Path.home() / ".cache" / "ms-playwright"
        for exe in sorted(cache.glob("chromium-*/chrome-linux/chrome"), reverse=True):
            return {"executable_path": str(exe)}
        return {}
    cache = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    for exe in sorted(cache.glob("chromium-*/chrome-win64/chrome.exe"), reverse=True):
        return {"executable_path": str(exe)}
    return {}


def streamlit_env() -> dict:
    env = {**os.environ, "APP_OFFLINE": "1", "PYTHONIOENCODING": "utf-8"}
    env.setdefault("APP_TODAY", FROZEN_TODAY)
    env.setdefault("JSA_VISUAL_LH_FIXTURE", str(LH_FIXTURE))
    return env


def start_streamlit(port: int) -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", "app.py",
            "--server.port", str(port),
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
            "--server.fileWatcherType", "none",
        ],
        cwd=str(_REPO),
        env=streamlit_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for_port(proc: subprocess.Popen, port: int, seconds: int = 60) -> None:
    for _ in range(seconds * 2):
        if proc.poll() is not None:
            raise RuntimeError(
                f"streamlit exited during startup (rc={proc.returncode})"
            )
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"streamlit did not accept connections within {seconds}s")


def stop_process(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


def wait_for_app(page, timeout_ms: int = 60_000) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        remaining = max(1_000, int((deadline - time.monotonic()) * 1000))
        try:
            page.wait_for_selector(
                '[data-testid="stMainBlockContainer"]',
                timeout=min(remaining, 8_000),
            )
            page.wait_for_function(
                """() => {
                  const spin = document.querySelector('[data-testid="stSpinner"]');
                  if (spin && spin.offsetParent !== null) return false;
                  const main = document.querySelector('[data-testid="stMainBlockContainer"]');
                  return !!(main && (main.innerText || '').length > 20);
                }""",
                timeout=min(remaining, 15_000),
            )
            plots = page.locator(".js-plotly-plot")
            if plots.count():
                page.wait_for_function(
                    """() => {
                      const plots = document.querySelectorAll('.js-plotly-plot');
                      return [...plots].every(p =>
                        p.querySelector('.main-svg, .svg-container, canvas, .plotly')
                      );
                    }""",
                    timeout=min(remaining, 20_000),
                )
            page.wait_for_timeout(400)
            spin = page.locator('[data-testid="stSpinner"]')
            if spin.count() and spin.first.is_visible():
                continue
            return
        except Exception as exc:
            last_error = exc
            page.wait_for_timeout(500)
    if last_error is not None:
        raise last_error
    raise RuntimeError("streamlit app did not become idle")


def stabilize(page) -> None:
    page.emulate_media(reduced_motion="reduce")
    page.add_style_tag(content=_STABILIZE_CSS)


def open_route(page, app_url: str, path: str, query: str = "") -> None:
    suffix = "/" if path in ("", "/") else "/" + path.lstrip("/")
    url = app_url.rstrip("/") + suffix
    if query:
        url += ("&" if "?" in url else "?") + query.lstrip("?&")
    last_error: Exception | None = None
    for _ in range(3):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            wait_for_app(page)
            stabilize(page)
            wait_for_app(page)
            return
        except Exception as exc:
            last_error = exc
            page.wait_for_timeout(1_000)
    raise last_error


def layout_probe(page) -> dict:
    return page.evaluate(_LAYOUT_PROBE)


def wait_for_stable_layout(page, timeout_ms: int = 8_000) -> None:
    last = None
    hits = 0
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        sig = page.evaluate(
            """() => {
              const main = document.querySelector('[data-testid="stMainBlockContainer"]');
              const h = main ? main.scrollHeight : 0;
              const t = (document.body.innerText || '').length;
              return h + ':' + t;
            }"""
        )
        if sig == last:
            hits += 1
            if hits >= 3:
                return
        else:
            hits = 0
            last = sig
        page.wait_for_timeout(250)


def screenshot_png(page) -> bytes:
    """Full document, not Streamlit's inner viewport scroller."""
    page.evaluate(
        """() => {
          const nodes = [
            document.documentElement,
            document.body,
            document.querySelector('[data-testid="stApp"]'),
            document.querySelector('[data-testid="stAppViewContainer"]'),
            document.querySelector('[data-testid="stMain"]'),
            document.querySelector('section.main'),
            document.querySelector('[data-testid="stMainBlockContainer"]'),
          ];
          for (const el of nodes) {
            if (!el || !el.style) continue;
            el.style.setProperty('height', 'auto', 'important');
            el.style.setProperty('max-height', 'none', 'important');
            el.style.setProperty('overflow', 'visible', 'important');
          }
        }"""
    )
    page.wait_for_timeout(200)
    return page.screenshot(full_page=True, type="png", animations="disabled")
