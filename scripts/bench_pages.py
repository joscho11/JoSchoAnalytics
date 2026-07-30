"""Fresh-process benchmark harness for the live Streamlit site.

Measures, per page, in a FRESH interpreter (so nothing is warmed by a previous page):
CPU time (user+sys, whole process), wall time, peak RSS, module-import count and the
heavy third-party packages actually pulled in, Streamlit cache cardinality + retained
bytes, and every outbound network connection attempted.

Why fresh processes: Streamlit Community Cloud runs ONE process per app; a cold container
start pays every import and every cache miss at once, and that burst is what a CPU-quota
accounting window sees. Warm reruns (a click, a widget change, a browser reconnect) are a
completely different cost, so both are measured separately.

Usage (from the repo root, with the parity venv):
    .venv-test/Scripts/python.exe scripts/bench_pages.py                 # all pages, cold+warm
    .venv-test/Scripts/python.exe scripts/bench_pages.py --pages app,page_help
    .venv-test/Scripts/python.exe scripts/bench_pages.py --walk          # one process, 9 pages
    .venv-test/Scripts/python.exe scripts/bench_pages.py --json out.json

Hermetic by default (APP_OFFLINE=1). `--online` lifts the guard so real egress can be
counted; connections are always COUNTED either way, never silently allowed.

This file is a diagnostic. It imports nothing from the app at module scope and is not
imported by the app.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
_SITE_PAGES = _HERE / "site_pages"

# Targets: "app" is the real entrypoint (cold container landing = Weekly Predictions
# through st.navigation); the rest are the page modules a nav click lazily imports.
PAGE_MODULES = (
    "page_weekly_predictions",
    "page_track_record",
    "page_draft_board",
    "page_rookie_board",
    "page_weekly_fantasy",
    "page_dfs",
    "page_film_room",
    "page_league_history",
    "page_help",
)
TARGETS = ("app",) + PAGE_MODULES

# Third-party packages whose presence dominates cold-start CPU and RSS. Reported as a
# set so a regression ("plotly is back on the cold path") is visible, not inferred.
HEAVY = ("pandas", "numpy", "polars", "pyarrow", "nflreadpy", "plotly", "streamlit",
         "requests", "sklearn", "joblib", "xgboost", "lightgbm", "scipy", "catboost",
         "matplotlib", "altair")


# ─────────────────────────────── child-side probes ───────────────────────────────

class NetProbe:
    """Counts every outbound TCP connect attempt, by (host, port)."""

    def __init__(self, block: bool):
        self.block = block
        self.calls: list[str] = []
        self._connect = socket.socket.connect
        self._create = socket.create_connection

    def install(self):
        probe = self

        def connect(sock, address, *a, **kw):
            probe._record(address)
            if probe.block:
                raise OSError("bench_pages: network blocked (APP_OFFLINE)")
            return probe._connect(sock, address, *a, **kw)

        def create_connection(address, *a, **kw):
            probe._record(address)
            if probe.block:
                raise OSError("bench_pages: network blocked (APP_OFFLINE)")
            return probe._create(address, *a, **kw)

        socket.socket.connect = connect
        socket.create_connection = create_connection

    def _record(self, address):
        try:
            host, port = address[0], address[1]
        except Exception:
            host, port = str(address), ""
        # Loopback is Streamlit's own machinery, not app egress.
        if str(host) in ("127.0.0.1", "::1", "localhost"):
            return
        self.calls.append(f"{host}:{port}")


def _proc_metrics(proc):
    ct = proc.cpu_times()
    mi = proc.memory_info()
    peak = getattr(mi, "peak_wset", None)          # Windows
    if peak is None:                                # POSIX
        try:
            import resource
            ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            peak = ru * (1 if sys.platform == "darwin" else 1024)
        except Exception:
            peak = mi.rss
    return (ct.user + ct.system), mi.rss, peak


def _cache_stats():
    """Streamlit cache cardinality + retained bytes, per cached function."""
    out = {"cache_data": [], "cache_resource": [], "entries": 0, "bytes": 0}
    try:
        from streamlit.runtime.caching import cache_data_api, cache_resource_api
    except Exception:
        return out
    for label, caches in (("cache_data", cache_data_api._data_caches),
                          ("cache_resource", cache_resource_api._resource_caches)):
        rows = []
        # _function_caches is {session_or_None: {func_key: cache}}. Walking it directly
        # gives PER-ENTRY cardinality; DataCaches.get_stats() groups by function and
        # loses it, which is exactly the number an unbounded-key audit needs.
        try:
            inner = [c for group in caches._function_caches.values()
                     for c in group.values()]
        except Exception:
            inner = []
        for cache in inner:
            entries, nbytes = 0, 0
            try:
                for fam in cache.get_stats().values():
                    for s in fam:
                        entries += 1
                        nbytes += int(getattr(s, "byte_length", 0) or 0)
            except Exception:
                pass
            rows.append({"name": getattr(cache, "display_name", "?"),
                         "entries": entries, "bytes": nbytes,
                         "max_entries": getattr(cache, "max_entries", None),
                         "ttl_seconds": getattr(cache, "ttl_seconds", None)})
        rows.sort(key=lambda r: -r["bytes"])
        out[label] = rows
        out["entries"] += sum(r["entries"] for r in rows)
        out["bytes"] += sum(r["bytes"] for r in rows)
    return out


def _heavy_loaded():
    return sorted(p for p in HEAVY if p in sys.modules)


def _harness_for(target: str, tmpdir: Path) -> str:
    if target == "app":
        return str(_HERE / "app.py")
    f = tmpdir / f"bench_{target}.py"
    f.write_text(
        f"import sys; sys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        f"import {target} as page\npage.render()\n",
        encoding="utf-8",
    )
    return str(f)


def run_child(target: str, warm: int, block_net: bool) -> dict:
    import tempfile
    import psutil

    probe = NetProbe(block=block_net)
    probe.install()
    proc = psutil.Process()

    base_cpu, base_rss, _ = _proc_metrics(proc)
    base_mods = len(sys.modules)
    t0 = time.perf_counter()

    from streamlit.testing.v1 import AppTest       # counted in the import phase below

    imp_cpu, imp_rss, _ = _proc_metrics(proc)
    imp_wall = time.perf_counter() - t0

    tmpdir = Path(tempfile.mkdtemp(prefix="bench_pages_"))
    path = _harness_for(target, tmpdir)

    net_before = len(probe.calls)
    t1 = time.perf_counter()
    at = AppTest.from_file(path, default_timeout=300).run()
    cold_wall = time.perf_counter() - t1
    cold_cpu, cold_rss, cold_peak = _proc_metrics(proc)
    cold_net = probe.calls[net_before:]
    cold_cache = _cache_stats()

    warms = []
    for _ in range(warm):
        n0 = len(probe.calls)
        t2 = time.perf_counter()
        c0, _, _ = _proc_metrics(proc)
        at = at.run()
        w = time.perf_counter() - t2
        c1, rss1, peak1 = _proc_metrics(proc)
        warms.append({"wall_s": round(w, 4), "cpu_s": round(c1 - c0, 4),
                      "rss_mb": round(rss1 / 2**20, 1),
                      "net": probe.calls[n0:]})

    end_cpu, end_rss, end_peak = _proc_metrics(proc)
    return {
        "target": target,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "import_phase": {"wall_s": round(imp_wall, 4),
                         "cpu_s": round(imp_cpu - base_cpu, 4),
                         "rss_mb": round(imp_rss / 2**20, 1)},
        "cold": {"wall_s": round(cold_wall, 4),
                 "cpu_s": round(cold_cpu - imp_cpu, 4),
                 "rss_mb": round(cold_rss / 2**20, 1),
                 "net": cold_net},
        "cold_total_from_process_start": {
            "wall_s": round(imp_wall + cold_wall, 4),
            "cpu_s": round(cold_cpu - base_cpu, 4)},
        "warm": warms,
        "warm_mean": {
            "wall_s": round(sum(w["wall_s"] for w in warms) / len(warms), 4),
            "cpu_s": round(sum(w["cpu_s"] for w in warms) / len(warms), 4),
        } if warms else None,
        "modules": {"base": base_mods, "after": len(sys.modules),
                    "heavy": _heavy_loaded()},
        "cache": cold_cache,
        "cache_after_warm": _cache_stats(),
        "peak_rss_mb": round(end_peak / 2**20, 1),
        "final_rss_mb": round(end_rss / 2**20, 1),
        "exceptions": [str(e.value) for e in at.exception],
        "errors": [str(e.value) for e in at.error],
        "net_total": probe.calls,
    }


def run_walk(warm: int, block_net: bool) -> dict:
    """One process, all nine pages in sequence — the real single-container reality.

    Shows what a container's RSS and cache set look like after a visitor (or a crawler)
    has touched every page, which no per-page cold number can show.
    """
    import tempfile
    import psutil

    probe = NetProbe(block=block_net)
    probe.install()
    proc = psutil.Process()
    base_cpu, base_rss, _ = _proc_metrics(proc)

    from streamlit.testing.v1 import AppTest
    tmpdir = Path(tempfile.mkdtemp(prefix="bench_walk_"))
    steps = []
    prev_cpu, _, _ = _proc_metrics(proc)
    for target in TARGETS:
        path = _harness_for(target, tmpdir)
        t = time.perf_counter()
        at = AppTest.from_file(path, default_timeout=300).run()
        wall = time.perf_counter() - t
        cpu, rss, peak = _proc_metrics(proc)
        cs = _cache_stats()
        steps.append({"target": target, "wall_s": round(wall, 4),
                      "cpu_s": round(cpu - prev_cpu, 4),
                      "rss_mb": round(rss / 2**20, 1),
                      "peak_rss_mb": round(peak / 2**20, 1),
                      "cache_entries": cs["entries"],
                      "cache_mb": round(cs["bytes"] / 2**20, 2),
                      "modules": len(sys.modules),
                      "exceptions": [str(e.value) for e in at.exception],
                      "errors": [str(e.value) for e in at.error]})
        prev_cpu = cpu
    end_cpu, end_rss, end_peak = _proc_metrics(proc)
    return {"mode": "walk", "steps": steps,
            "total_cpu_s": round(end_cpu - base_cpu, 4),
            "peak_rss_mb": round(end_peak / 2**20, 1),
            "final_rss_mb": round(end_rss / 2**20, 1),
            "cache": _cache_stats(),
            "heavy": _heavy_loaded(),
            "net_total": probe.calls}


# ─────────────────────────────── parent orchestration ───────────────────────────────

def spawn(target: str, warm: int, online: bool) -> dict:
    env = dict(os.environ)
    env["APP_OFFLINE"] = "0" if online else "1"
    env["PYTHONUTF8"] = "1"
    cmd = [sys.executable, str(Path(__file__).resolve()), "--child", target,
           "--warm", str(warm)]
    if online:
        cmd.append("--online")
    r = subprocess.run(cmd, cwd=str(_HERE), env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=1800)
    tag = "@@BENCH@@"
    for line in r.stdout.splitlines():
        if line.startswith(tag):
            return json.loads(line[len(tag):])
    return {"target": target, "fatal": True, "returncode": r.returncode,
            "stdout": r.stdout[-4000:], "stderr": r.stderr[-4000:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--child", default=None)
    ap.add_argument("--pages", default=None, help="comma list; default = every target")
    ap.add_argument("--warm", type=int, default=3)
    ap.add_argument("--walk", action="store_true", help="one process, all pages in order")
    ap.add_argument("--online", action="store_true", help="allow real egress (still counted)")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    if args.child:
        block = not args.online
        res = run_walk(args.warm, block) if args.child == "__walk__" \
            else run_child(args.child, args.warm, block)
        print("@@BENCH@@" + json.dumps(res))
        return

    if args.walk:
        env = dict(os.environ)
        env["APP_OFFLINE"] = "0" if args.online else "1"
        cmd = [sys.executable, str(Path(__file__).resolve()), "--child", "__walk__"]
        if args.online:
            cmd.append("--online")
        r = subprocess.run(cmd, cwd=str(_HERE), env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=1800)
        out = None
        for line in r.stdout.splitlines():
            if line.startswith("@@BENCH@@"):
                out = json.loads(line[len("@@BENCH@@"):])
        if out is None:
            print(r.stdout[-4000:]); print(r.stderr[-4000:]); sys.exit(1)
        print(f"{'page':26s} {'wall':>7s} {'cpu':>7s} {'rss':>8s} {'cache':>9s} {'mods':>6s}")
        for s in out["steps"]:
            print(f"{s['target']:26s} {s['wall_s']:7.3f} {s['cpu_s']:7.3f} "
                  f"{s['rss_mb']:7.1f}M {s['cache_entries']:4d}/{s['cache_mb']:5.2f}M "
                  f"{s['modules']:6d}")
        print(f"\ntotal cpu {out['total_cpu_s']:.3f}s  peak rss {out['peak_rss_mb']:.1f}M  "
              f"final rss {out['final_rss_mb']:.1f}M")
        print("net:", sorted(set(out["net_total"])) or "none")
        if args.json:
            Path(args.json).write_text(json.dumps(out, indent=2), encoding="utf-8")
        return

    targets = args.pages.split(",") if args.pages else list(TARGETS)
    results = []
    print(f"{'page':26s} {'imp_cpu':>8s} {'cold_cpu':>9s} {'cold_wall':>10s} "
          f"{'warm_cpu':>9s} {'peakRSS':>8s} {'cacheMB':>8s} {'net':>4s}")
    for t in targets:
        res = spawn(t, args.warm, args.online)
        results.append(res)
        if res.get("fatal"):
            print(f"{t:26s}  FATAL rc={res['returncode']}")
            print(res["stderr"][-2000:])
            continue
        wm = res["warm_mean"]["cpu_s"] if res["warm_mean"] else float("nan")
        print(f"{t:26s} {res['import_phase']['cpu_s']:8.3f} {res['cold']['cpu_s']:9.3f} "
              f"{res['cold']['wall_s']:10.3f} {wm:9.3f} {res['peak_rss_mb']:7.1f}M "
              f"{res['cache']['bytes']/2**20:7.2f}M {len(res['net_total']):4d}")
        if res["exceptions"] or res["errors"]:
            print(f"    !! exceptions={res['exceptions']} errors={res['errors']}")

    payload = {"generated_wall_clock": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "python": sys.version.split()[0], "results": results}
    if args.json:
        Path(args.json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
