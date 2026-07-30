"""Removable production telemetry for the deployed Streamlit app.

Why this exists: local benchmarking proved the app's own CPU is negligible (the whole
nine-page site costs ~2.5 CPU-seconds and ~220 MB in one process), yet Community Cloud
throttling recurred. The one thing local measurement cannot see is HOW MANY script runs
the live container actually executes — Streamlit Cloud's public analytics count viewers,
not script runs, so crawlers, health probes, websocket reconnects and container restarts
are all invisible. This module makes the live process report that itself.

Design constraints, all deliberate:
  • OFF by default. With the switch unset this module does nothing but define functions,
    so deployed behavior is byte-identical until it is turned on.
  • ZERO new dependencies. CPU comes from `resource`/`os.times`, RSS from
    /proc/self/statm — nothing that would grow requirements.txt past its eight packages.
  • No personal data. No IP, no user agent, no referrer, no query string, no cookie, no
    stable visitor identifier. The only session marker is a per-process counter that is
    reset every restart and cannot be correlated across processes or with a person.
  • The sink is stderr, because a Community Cloud container's filesystem is ephemeral but
    its stderr is the app log you can read under "Manage app".

Turn on: set `APP_TELEMETRY = "1"` in the app's Secrets (or the env var of the same name),
then read the log lines prefixed `JSA_TELEMETRY`. Each line is one JSON object.

Removal is two lines in app.py (`import runtime_telemetry` / the `begin`/`end` pair) plus
this file. Nothing else references it.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time

_PREFIX = "JSA_TELEMETRY"

# ── Concurrency model ────────────────────────────────────────────────────────────────
# Streamlit runs each session's script on its own ScriptRunner thread, and a container
# serves many sessions at once, so `begin()`/`end()` pairs INTERLEAVE. Two kinds of state
# live here and they must be kept apart:
#
#   per-RUN state (start wall clock, CPU baseline, the run's own sequence number) is
#   thread-local — one in-flight run per script thread. Holding it in module globals let
#   a second session's `begin()` overwrite the first session's baselines, so the first
#   session's `end()` reported the *other* run's elapsed time and re-emitted the *other*
#   run's `run_seq`: a duplicate sequence number and a misattributed measurement.
#
#   process-wide counters (run total, session ordinal, the once-only boot flag) are shared
#   by definition and are mutated only under `_counter_lock`, so no two threads can be
#   handed the same ordinal or both emit the boot line.
_PROC_START_WALL = time.time()
_PROC_START_MONO = time.perf_counter()
_counter_lock = threading.Lock()
_local = threading.local()
_run_seq = 0          # guarded by _counter_lock
_session_seq = 0      # guarded by _counter_lock
_booted = False       # guarded by _counter_lock

_switch_lock = threading.Lock()
_secret_switch: bool | None = None   # resolved once per process


def _enabled() -> bool:
    """Env var first (a dict lookup), then st.secrets — Community Cloud's only injection
    point for a deployed app.

    The secrets answer is memoized because it cannot change without a restart, so a
    per-run render never pays for it twice. Any failure reading secrets means OFF —
    telemetry must never be the reason a page breaks.

    Its own lock, not `_counter_lock`: `begin()` calls this and then takes the counter
    lock, so sharing one lock would put a nested acquire one refactor away.
    """
    global _secret_switch
    if os.environ.get("APP_TELEMETRY") == "1":
        return True
    if _secret_switch is None:
        with _switch_lock:
            if _secret_switch is None:
                try:
                    import streamlit as st
                    _secret_switch = str(st.secrets.get("APP_TELEMETRY", "")) == "1"
                except Exception:
                    _secret_switch = False
    return _secret_switch


# Platform capabilities are resolved ONCE, at import, and never probed again. Probing per
# call meant every metric read on a non-Linux box raised and swallowed an exception, and
# exception machinery — not the measurement — dominated the cost (~0.9 ms/run). Resolving
# up front makes a telemetry call a few microseconds on every platform.
try:                                            # Linux (what Community Cloud runs) + macOS
    import resource as _resource
except Exception:
    _resource = None

_HAVE_STATM = os.path.exists("/proc/self/statm")
try:
    _PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")
except Exception:
    _PAGE_SIZE = 4096
# ru_maxrss is kilobytes on Linux and bytes on macOS.
_MAXRSS_DIV = 1024 if sys.platform != "darwin" else 1024 * 1024


def _cpu_seconds() -> float:
    """Process CPU (user+system) in seconds, dependency-free."""
    if _resource is not None:
        ru = _resource.getrusage(_resource.RUSAGE_SELF)
        return ru.ru_utime + ru.ru_stime
    t = os.times()                              # Windows: user/system of this process
    return t[0] + t[1]


def _rss_mb() -> float | None:
    """Resident set size in MiB from /proc, or None where /proc does not exist."""
    if not _HAVE_STATM:
        return None
    try:
        with open("/proc/self/statm", "rb") as fh:
            pages = int(fh.read().split()[1])
        return round(pages * _PAGE_SIZE / 2**20, 1)
    except Exception:
        return None


def _peak_rss_mb() -> float | None:
    if _resource is None:
        return None
    kb = _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss
    return round(kb / _MAXRSS_DIV, 1) if kb else None


def _emit(event: str, **fields) -> None:
    try:
        payload = {"ev": event, "t": round(time.time(), 3), **fields}
        sys.stderr.write(f"{_PREFIX} {json.dumps(payload, separators=(',', ':'))}\n")
        sys.stderr.flush()
    except Exception:
        pass


def _has_script_ctx() -> bool:
    """True only inside a real script run.

    Checked before touching st.session_state: outside a run, Streamlit logs a
    'missing ScriptRunContext' warning whose traceback formatting costs orders of
    magnitude more than everything else this module does. Guarding here keeps telemetry
    genuinely free and keeps the logs clean.
    """
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        # suppress_warning: outside a run Streamlit would otherwise log a warning here.
        try:
            return get_script_run_ctx(suppress_warning=True) is not None
        except TypeError:                       # older signature without the kwarg
            return get_script_run_ctx() is not None
    except Exception:
        return False


def _session_index() -> int | None:
    """A per-process ordinal for this browser session — NOT an identifier.

    Its only purpose is to distinguish 'one visitor caused 40 script runs' from
    '40 separate connections each caused one', which is the difference between an app
    problem and a traffic problem. It is an integer in session_state, so it dies with
    the session and with the process.
    """
    global _session_seq
    if not _has_script_ctx():
        return None
    try:
        import streamlit as st
        if "_tel_session_idx" not in st.session_state:
            # session_state is per-session, but the ordinal it stores comes from a
            # process-wide counter — so the increment is the shared part and is locked.
            with _counter_lock:
                _session_seq += 1
                assigned = _session_seq
            st.session_state["_tel_session_idx"] = assigned
        return st.session_state["_tel_session_idx"]
    except Exception:
        return None


def begin() -> None:
    """Call at the very top of app.py. Cheap: two clock reads plus one getrusage.

    Safe to call from concurrent script threads: this run's sequence number is claimed
    under the lock and then parked in thread-local storage together with its own
    baselines, so a concurrent `begin()` cannot disturb it.
    """
    global _run_seq, _booted
    if not _enabled():
        return
    with _counter_lock:
        first = not _booted
        _booted = True
        _run_seq += 1
        assigned = _run_seq
        if first:
            # Emitted while holding the lock so the boot line cannot appear after a run
            # line. It happens exactly once per process, so the contention is irrelevant.
            _emit("boot", wall_start=round(_PROC_START_WALL, 3), pid=os.getpid(),
                  python=sys.version.split()[0], rss_mb=_rss_mb(),
                  cpu_s=round(_cpu_seconds(), 4))
    _local.run_seq = assigned
    _local.t0 = time.perf_counter()
    _local.cpu0 = _cpu_seconds()


def end(page: str | None = None) -> None:
    """Call at the very bottom of app.py, after the page has rendered.

    Reads only this thread's own baselines, and clears them, so a stray second `end()`
    without a matching `begin()` cannot re-emit a run line under a stale sequence number.
    """
    if not _enabled():
        return
    t0 = getattr(_local, "t0", None)
    if t0 is None:                      # no run in flight on this thread
        return
    cpu0 = _local.cpu0
    run_seq = _local.run_seq
    _local.t0 = _local.cpu0 = _local.run_seq = None
    _emit("run",
          run_seq=run_seq,
          session_idx=_session_index(),
          page=page,
          wall_s=round(time.perf_counter() - t0, 4),
          cpu_s=round(_cpu_seconds() - cpu0, 4),
          proc_cpu_s=round(_cpu_seconds(), 3),
          proc_uptime_s=round(time.perf_counter() - _PROC_START_MONO, 1),
          rss_mb=_rss_mb(),
          peak_rss_mb=_peak_rss_mb())


def snapshot() -> dict:
    """Current counters — for tests and for ad-hoc inspection, never for the log."""
    with _counter_lock:
        runs, sessions = _run_seq, _session_seq
    return {"enabled": _enabled(), "run_seq": runs, "session_seq": sessions,
            "proc_cpu_s": round(_cpu_seconds(), 3), "rss_mb": _rss_mb(),
            "proc_uptime_s": round(time.perf_counter() - _PROC_START_MONO, 1)}
