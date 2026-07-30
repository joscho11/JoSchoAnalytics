"""Measure the REAL server process, not just a script run.

`AppTest` measures one script execution. Streamlit Community Cloud runs a long-lived
`streamlit run` process that also carries a Tornado server, the source-file watcher, the
session/websocket machinery and the media file manager. For an app with almost no traffic,
the number that decides whether a CPU quota drains is the process's IDLE CPU rate — what it
burns per hour with nobody connected — plus the one-off boot cost. Neither is visible to
AppTest.

Phases measured:
  boot     — spawn to first successful HTTP 200 on /
  idle     — N seconds with no client at all
  connect  — one HTTP GET of / (static shell; no websocket, so no script run)
  idle2    — N more seconds, to confirm idle CPU is a flat rate and not a decaying tail

Reported as CPU seconds per hour, extrapolated from the idle window, because that is the
unit a platform quota is denominated in.

Usage:
    .venv-test/Scripts/python.exe scripts/bench_server.py --idle 60
    .venv-test/Scripts/python.exe scripts/bench_server.py --idle 60 --watcher none
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]


def _tree_cpu(proc):
    """CPU of the server process plus any children it spawned."""
    import psutil
    total = 0.0
    rss = 0
    procs = [proc]
    try:
        procs += proc.children(recursive=True)
    except psutil.Error:
        pass
    for p in procs:
        try:
            ct = p.cpu_times()
            total += ct.user + ct.system
            rss += p.memory_info().rss
        except psutil.Error:
            pass
    return total, rss


def _wait_http(url: str, timeout: float):
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return time.perf_counter() - t0
        except (urllib.error.URLError, OSError):
            time.sleep(0.25)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--idle", type=float, default=60.0, help="seconds per idle window")
    ap.add_argument("--port", type=int, default=8599)
    ap.add_argument("--watcher", default=None,
                    help="server.fileWatcherType override, e.g. none / poll / watchdog")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    import psutil

    env = dict(os.environ)
    env.setdefault("APP_OFFLINE", "1")
    env["PYTHONUTF8"] = "1"
    cmd = [sys.executable, "-m", "streamlit", "run", str(_HERE / "app.py"),
           "--server.port", str(args.port), "--server.headless", "true",
           "--browser.gatherUsageStats", "false"]
    if args.watcher:
        cmd += ["--server.fileWatcherType", args.watcher]

    popen = subprocess.Popen(cmd, cwd=str(_HERE), env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    out = {"watcher": args.watcher or "default(auto)", "idle_window_s": args.idle}
    try:
        proc = psutil.Process(popen.pid)
        url = f"http://127.0.0.1:{args.port}/"
        boot = _wait_http(url, timeout=120)
        boot_cpu, boot_rss = _tree_cpu(proc)
        out["boot"] = {"wall_s": round(boot, 3) if boot else None,
                       "cpu_s": round(boot_cpu, 3),
                       "rss_mb": round(boot_rss / 2**20, 1)}
        if boot is None:
            out["fatal"] = "server never answered HTTP 200"
            return _emit(out, args)

        # idle window 1
        c0, _ = _tree_cpu(proc)
        time.sleep(args.idle)
        c1, rss1 = _tree_cpu(proc)
        out["idle"] = {"cpu_s": round(c1 - c0, 4),
                       "cpu_s_per_hour": round((c1 - c0) * 3600 / args.idle, 2),
                       "rss_mb": round(rss1 / 2**20, 1)}

        # one static GET (no websocket => no script run)
        c2, _ = _tree_cpu(proc)
        t = time.perf_counter()
        with urllib.request.urlopen(url, timeout=10) as r:
            body = r.read()
        get_wall = time.perf_counter() - t
        c3, _ = _tree_cpu(proc)
        out["static_get"] = {"wall_s": round(get_wall, 4), "cpu_s": round(c3 - c2, 4),
                             "bytes": len(body)}

        # idle window 2
        c4, _ = _tree_cpu(proc)
        time.sleep(args.idle)
        c5, rss5 = _tree_cpu(proc)
        out["idle2"] = {"cpu_s": round(c5 - c4, 4),
                        "cpu_s_per_hour": round((c5 - c4) * 3600 / args.idle, 2),
                        "rss_mb": round(rss5 / 2**20, 1)}
        out["watched_paths"] = _watched_paths()
    finally:
        popen.terminate()
        try:
            popen.wait(timeout=20)
        except subprocess.TimeoutExpired:
            popen.kill()
    return _emit(out, args)


def _watched_paths():
    """How many source files Streamlit's LocalSourcesWatcher would watch for this app.

    Counted in-process (importing the page modules the way a visitor who touches every
    page would), because the watcher's cost scales with this number under the polling
    backend and with the number of distinct DIRECTORIES under watchdog.
    """
    try:
        sys.path[:0] = [str(_HERE), str(_HERE / "site_pages")]
        before = set(sys.modules)
        for m in ("page_weekly_predictions", "page_track_record", "page_draft_board",
                  "page_rookie_board", "page_weekly_fantasy", "page_dfs",
                  "page_film_room", "page_league_history", "page_help"):
            __import__(m)
        local = []
        for name, mod in list(sys.modules.items()):
            f = getattr(mod, "__file__", None)
            if not f:
                continue
            try:
                p = Path(f).resolve()
            except OSError:
                continue
            if str(p).startswith(str(_HERE)) and ".venv" not in str(p):
                local.append(str(p.relative_to(_HERE)))
        return {"local_module_files": len(local),
                "distinct_dirs": len({str(Path(p).parent) for p in local}),
                "newly_imported": len(set(sys.modules) - before),
                "files": sorted(local)}
    except Exception as e:      # diagnostics must never be the thing that fails
        return {"error": repr(e)}


def _emit(out, args):
    print(json.dumps(out, indent=2))
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
