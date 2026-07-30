"""Guards for the two throttle-diagnosis changes (2026-07-29).

1. `runtime_telemetry` is OFF unless switched on, emits the six required fields when on,
   emits NO visitor-identifying field ever, and costs almost nothing per script run.
2. The GA pageview beacon no longer blocks a render: `send_ga_event` returns immediately
   even when the HTTP POST is slow, and the payload it sends is unchanged.

Hermetic: no real network, no real GA credentials.
"""
import json
import os
import sys
import threading
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import runtime_telemetry as tel


class _Collector:
    """Thread-safe stderr stand-in — the concurrency tests write from several threads."""

    def __init__(self):
        self._lock = threading.Lock()
        self.raw = []

    def write(self, text):
        with self._lock:
            self.raw.append(text)

    def flush(self):
        pass

    def events(self, kind=None):
        with self._lock:
            lines = list(self.raw)
        out = [json.loads(t.split(" ", 1)[1])
               for t in lines if t.startswith("JSA_TELEMETRY")]
        return [e for e in out if kind is None or e["ev"] == kind]

# Field names that would make this telemetry a privacy problem. None may ever appear.
FORBIDDEN_FIELDS = {"ip", "remote_ip", "client_ip", "user_agent", "ua", "referer",
                    "referrer", "query", "query_params", "cookie", "email", "user",
                    "session_id", "client_id", "host", "url"}
REQUIRED_RUN_FIELDS = {"run_seq", "page", "cpu_s", "wall_s", "rss_mb", "proc_uptime_s"}


def _capture(monkeypatch, enabled: bool):
    """Run one begin/end pair and return the JSON objects written to stderr."""
    sink = _Collector()
    monkeypatch.setattr(tel.sys, "stderr", sink)
    if enabled:
        monkeypatch.setenv("APP_TELEMETRY", "1")
    else:
        monkeypatch.delenv("APP_TELEMETRY", raising=False)
    monkeypatch.setattr(tel, "_booted", False)
    tel.begin()
    tel.end("weekly-predictions")
    return sink.events()


def test_off_by_default_emits_nothing(monkeypatch):
    # Deployed behavior must be unchanged until the switch is set, so "off" means silent.
    assert _capture(monkeypatch, enabled=False) == []


def test_on_emits_boot_and_run_with_required_fields(monkeypatch):
    events = _capture(monkeypatch, enabled=True)
    kinds = [e["ev"] for e in events]
    assert kinds == ["boot", "run"], kinds
    boot, run = events
    assert {"wall_start", "pid", "python"} <= set(boot)
    missing = REQUIRED_RUN_FIELDS - set(run)
    assert not missing, f"run event missing {sorted(missing)}"
    assert run["page"] == "weekly-predictions"
    assert run["run_seq"] >= 1
    assert isinstance(run["cpu_s"], float) and run["cpu_s"] >= 0
    assert isinstance(run["wall_s"], float) and run["wall_s"] >= 0


def test_no_personal_data_fields(monkeypatch):
    for event in _capture(monkeypatch, enabled=True):
        overlap = FORBIDDEN_FIELDS & set(event)
        assert not overlap, f"telemetry leaked {sorted(overlap)}"
        # and nothing that looks like an address anywhere in the values
        blob = json.dumps(event)
        assert "@" not in blob and "http" not in blob


def test_run_seq_increments_per_run(monkeypatch):
    monkeypatch.setenv("APP_TELEMETRY", "1")
    monkeypatch.setattr(tel, "_booted", True)
    before = tel.snapshot()["run_seq"]
    for _ in range(3):
        tel.begin()
        tel.end("x")
    assert tel.snapshot()["run_seq"] == before + 3


def _run_threads(targets, timeout=30):
    """Start every target, join them, and re-raise the first failure from any thread."""
    errors = []

    def wrap(fn):
        def inner():
            try:
                fn()
            except BaseException as exc:          # noqa: BLE001 - surfaced below
                errors.append(exc)
        return inner

    threads = [threading.Thread(target=wrap(t), daemon=True) for t in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout)
        assert not t.is_alive(), "telemetry thread deadlocked"
    if errors:
        raise errors[0]


def test_overlapping_runs_keep_their_own_baseline_and_sequence(monkeypatch):
    """Two interleaved script threads, choreographed with Events so the result is fixed.

        A.begin() ───────────────────────────────────────────► A.end()
                        B waits HOLD ─► B.begin() ─► B.end()

    Streamlit gives every session its own ScriptRunner thread, so this interleaving is
    the normal case on a container serving more than one visitor.

    Guaranteed to FAIL against module-global run state, twice over:
      • B.begin() overwrote the shared start/CPU baselines, so A.end() measured B's
        window (~0 s) instead of A's (>= HOLD).
      • A.end() read the shared counter, so BOTH lines carried B's run_seq — a duplicate
        sequence number attributed to the wrong run.
    """
    HOLD = 0.25
    sink = _Collector()
    monkeypatch.setattr(tel.sys, "stderr", sink)
    monkeypatch.setenv("APP_TELEMETRY", "1")
    monkeypatch.setattr(tel, "_booted", True)     # boot line already out; runs only

    a_began, b_began = threading.Event(), threading.Event()

    def long_run():
        tel.begin()
        a_began.set()
        assert b_began.wait(20), "B never started"
        tel.end("A")                              # fires immediately after B.begin()

    def short_run():
        assert a_began.wait(20), "A never started"
        time.sleep(HOLD)                          # sits INSIDE A's open window
        tel.begin()
        b_began.set()
        tel.end("B")

    _run_threads([long_run, short_run])

    runs = sink.events("run")
    assert len(runs) == 2, runs
    by_page = {e["page"]: e for e in runs}
    assert set(by_page) == {"A", "B"}, runs
    a, b = by_page["A"], by_page["B"]

    # sequence numbers: distinct, and ordered by which run STARTED first
    assert a["run_seq"] != b["run_seq"], f"duplicate run_seq {a['run_seq']}"
    assert a["run_seq"] < b["run_seq"], (a["run_seq"], b["run_seq"])

    # baselines: A measured its own window, not B's
    assert a["wall_s"] >= HOLD * 0.9, f"A.wall_s={a['wall_s']} lost its own baseline"
    assert b["wall_s"] < HOLD * 0.5, f"B.wall_s={b['wall_s']} picked up A's baseline"


def test_concurrent_begins_get_distinct_sequence_numbers(monkeypatch):
    """N threads all inside `begin()` before any calls `end()`.

    The barrier makes this deterministic: with a shared counter every `end()` would read
    the same post-increment value and emit N identical run_seq values. Each run must
    carry the number it was handed at its own begin().
    """
    N = 8
    sink = _Collector()
    monkeypatch.setattr(tel.sys, "stderr", sink)
    monkeypatch.setenv("APP_TELEMETRY", "1")
    monkeypatch.setattr(tel, "_booted", True)
    base = tel.snapshot()["run_seq"]
    barrier = threading.Barrier(N)

    def one(i):
        def inner():
            tel.begin()
            barrier.wait(20)                      # every run is open at this instant
            tel.end(f"T{i}")
        return inner

    _run_threads([one(i) for i in range(N)])

    seqs = sorted(e["run_seq"] for e in sink.events("run"))
    assert len(seqs) == N, seqs
    assert len(set(seqs)) == N, f"duplicate run_seq values: {seqs}"
    assert seqs == list(range(base + 1, base + 1 + N)), seqs
    assert tel.snapshot()["run_seq"] == base + N


def test_boot_is_emitted_once_under_concurrency(monkeypatch):
    """Only one thread may claim the boot line, however many start together."""
    N = 8
    sink = _Collector()
    monkeypatch.setattr(tel.sys, "stderr", sink)
    monkeypatch.setenv("APP_TELEMETRY", "1")
    monkeypatch.setattr(tel, "_booted", False)
    barrier = threading.Barrier(N)

    def one():
        barrier.wait(20)
        tel.begin()
        tel.end("x")

    _run_threads([one] * N)
    assert len(sink.events("boot")) == 1, sink.events("boot")


def test_end_without_begin_emits_nothing(monkeypatch):
    """A stray `end()` on a thread with no run in flight must stay silent — and a second
    `end()` must not re-emit the first run under a stale sequence number."""
    sink = _Collector()
    monkeypatch.setattr(tel.sys, "stderr", sink)
    monkeypatch.setenv("APP_TELEMETRY", "1")
    monkeypatch.setattr(tel, "_booted", True)

    def stray():
        tel.end("never-began")                    # fresh thread: no thread-local state
        assert sink.events("run") == []
        tel.begin()
        tel.end("real")
        tel.end("duplicate")                      # baseline was cleared by the first end

    _run_threads([stray])
    runs = sink.events("run")
    assert [e["page"] for e in runs] == ["real"], runs


def test_overhead_is_negligible(monkeypatch):
    """A telemetry call per script run must be far below the ~60 ms warm render itself.
    The counter lock is uncontended in the common case, so it must not change this."""
    monkeypatch.setenv("APP_TELEMETRY", "1")
    monkeypatch.setattr(tel.sys, "stderr", _Collector())
    n = 200
    t0 = time.perf_counter()
    for _ in range(n):
        tel.begin()
        tel.end("x")
    per_call_ms = (time.perf_counter() - t0) / n * 1000
    assert per_call_ms < 2.0, f"{per_call_ms:.3f} ms per run is too much for telemetry"


def test_ga_beacon_does_not_block_the_render(tmp_path):
    """A 2 s GA POST must not add 2 s to the render. Driven through a real script run so
    st.session_state / st.secrets behave exactly as they do in the app."""
    from streamlit.testing.v1 import AppTest

    harness = tmp_path / "ga_harness.py"
    harness.write_text(
        "import sys, time, json\n"
        f"sys.path[:0] = [r'{_ROOT}']\n"
        "import streamlit as st\n"
        "import dashboard_chrome as chrome\n"
        "chrome._OFFLINE = False\n"
        "chrome._ga_creds = lambda: ('G-TEST', 'SECRET')\n"
        "sent = {}\n"
        "class _Req:\n"
        "    @staticmethod\n"
        "    def post(url, params=None, json=None, timeout=None):\n"
        "        time.sleep(2.0)\n"
        "        sent.update(url=url, params=params, body=json, timeout=timeout)\n"
        "chrome.req = _Req\n"
        "t0 = time.perf_counter()\n"
        "chrome.send_ga_event('page_view')\n"
        "st.text(f'elapsed={time.perf_counter() - t0:.4f}')\n"
        "time.sleep(2.6)\n"
        "st.text('sent=' + json.dumps(sorted(sent)))\n"
        "st.text('event=' + str((sent.get('body') or {}).get('events', [{}])[0].get('name')))\n"
        "st.text('timeout=' + str(sent.get('timeout')))\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(harness), default_timeout=120).run()
    assert not at.exception, at.exception
    texts = [str(t.value) for t in at.text]
    elapsed = float(next(t for t in texts if t.startswith("elapsed=")).split("=")[1])
    assert elapsed < 0.3, f"send_ga_event blocked the render for {elapsed:.3f}s"
    # ...and the beacon still actually goes out, with the same endpoint contract
    assert "event=page_view" in texts, texts
    assert "timeout=3" in texts, texts
    assert '"body"' in next(t for t in texts if t.startswith("sent=")), texts


def test_app_renders_clean_with_telemetry_enabled(monkeypatch, tmp_path):
    """The wired-in begin/end pair must not disturb any page."""
    from streamlit.testing.v1 import AppTest

    os.environ["APP_OFFLINE"] = "1"
    os.environ["APP_TELEMETRY"] = "1"
    try:
        at = AppTest.from_file(str(_ROOT / "app.py"), default_timeout=300).run()
        assert not at.exception, at.exception
        assert not at.error, [e.value for e in at.error]
    finally:
        os.environ.pop("APP_TELEMETRY", None)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
