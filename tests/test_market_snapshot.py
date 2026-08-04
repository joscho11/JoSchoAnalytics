"""Hermetic tests for the 2026 point-in-time market archive (capture_market_snapshot.py).

NO NETWORK. Every test drives the pure functions (normalize_projections / players_subset /
health_check / write_snapshot) from synthetic fixtures, or a fake `_fetch` monkeypatched over
the network call, so the suite is deterministic and runs offline in CI.

What these guard, in the order the brief demands:
  * identical raw input -> identical normalized output AND identical file hashes
  * row order in the source response cannot change the normalized hash
  * two captures never overwrite each other
  * malformed / truncated / low-row / duplicate-id / sentinel-saturated responses are REJECTED
  * a failed attempt never enters the valid manifest
  * a snapshot is interpretable from its OWN frozen player mapping, with no newer directory
  * the existing board overlay contract is untouched
  * the private archive path stays ignored by version control
"""
import gzip
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

os.environ["APP_OFFLINE"] = "1"

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "fantasy" / "seasonal_projections"))

import capture_market_snapshot as cms  # noqa: E402


# ----------------------------------------------------------------------------- fixtures
def make_raw(n=2500, dup_ids=False, sentinel_all=False, drop_family=None):
    """A synthetic /projections response: dict keyed by sleeper_id, value = stat dict."""
    out = {}
    for i in range(n):
        pid = str(9000 + (0 if dup_ids and i == 1 else i))
        rec = {
            "adp_half_ppr": 999.0 if sentinel_all else float(i + 1),
            "adp_ppr": float(i + 1), "adp_std": float(i + 2), "adp_2qb": float(i + 3),
            "adp_dynasty": float(i + 4), "adp_rookie": float(i + 5),
            "pts_half_ppr": 300.0 - i * 0.05, "pts_ppr": 320.0 - i * 0.05,
            "pts_std": 280.0 - i * 0.05, "gp": 18.0,
            "rush_yd": 10.0 * i, "rec_yd": 5.0 * i, "pass_yd": 0.0,
        }
        if drop_family:
            for k in list(rec):
                if k.startswith(drop_family):
                    rec.pop(k)
        out[pid] = rec
    return out


def make_players(raw):
    return {pid: {"full_name": f"Player {pid}", "first_name": "Player", "last_name": pid,
                  "position": "WR", "fantasy_positions": ["WR"], "team": "SF",
                  "status": "Active", "years_exp": 3, "gsis_id": f"00-00{pid}"}
            for pid in raw}


def provenance(raw, players):
    return {"capture_id": "fixture", "season": 2026,
            "players_raw_sha256": cms.sha256_bytes(json.dumps(players, sort_keys=True).encode())}


# ----------------------------------------------------------------------------- determinism
def test_identical_input_gives_identical_normalized_output_and_hashes(tmp_path):
    raw, players = make_raw(), None
    players = make_players(raw)
    a = cms.normalize_projections(raw, players, 2026)
    b = cms.normalize_projections(json.loads(json.dumps(raw)), players, 2026)
    pd.testing.assert_frame_equal(a, b)

    dt = datetime(2026, 8, 3, 13, 0, 0, tzinfo=timezone.utc)
    p1 = cms.write_snapshot(2026, dt, b"RAW", raw, players, a, provenance(raw, players),
                            root=tmp_path / "one", store_full_players=False)
    p2 = cms.write_snapshot(2026, dt, b"RAW", raw, players, b, provenance(raw, players),
                            root=tmp_path / "two", store_full_players=False)
    for name in ("projections_raw.json.gz", "players_subset.json.gz", "normalized.csv"):
        assert cms.sha256_file(p1 / name) == cms.sha256_file(p2 / name), \
            f"{name} hash is not reproducible from identical input"


def test_row_order_cannot_change_the_normalized_hash(tmp_path):
    raw = make_raw()
    players = make_players(raw)
    shuffled = {k: raw[k] for k in sorted(raw, reverse=True)}
    assert list(shuffled) != list(raw), "fixture failed to reorder"

    a = cms.normalize_projections(raw, players, 2026)
    b = cms.normalize_projections(shuffled, players, 2026)
    pd.testing.assert_frame_equal(a, b)

    dt = datetime(2026, 8, 3, 13, 0, 0, tzinfo=timezone.utc)
    pa = cms.write_snapshot(2026, dt, b"R", raw, players, a, provenance(raw, players),
                            root=tmp_path / "a", store_full_players=False)
    pb = cms.write_snapshot(2026, dt, b"R", shuffled, players, b, provenance(raw, players),
                            root=tmp_path / "b", store_full_players=False)
    assert cms.sha256_file(pa / "normalized.csv") == cms.sha256_file(pb / "normalized.csv")


# ----------------------------------------------------------------------------- no overwrite
def test_two_captures_never_overwrite_each_other(tmp_path):
    raw = make_raw()
    players = make_players(raw)
    df = cms.normalize_projections(raw, players, 2026)
    dt = datetime(2026, 8, 3, 13, 0, 0, tzinfo=timezone.utc)
    root = tmp_path / "arch"
    first = cms.write_snapshot(2026, dt, b"A", raw, players, df, provenance(raw, players),
                               root=root, store_full_players=False)
    with pytest.raises(FileExistsError):
        cms.write_snapshot(2026, dt, b"B", raw, players, df, provenance(raw, players),
                           root=root, store_full_players=False)
    assert gzip.decompress((first / "projections_raw.json.gz").read_bytes()) == b"A", \
        "the original capture must survive a same-second collision untouched"

    later = cms.write_snapshot(2026, dt + timedelta(seconds=1), b"B", raw, players, df,
                               provenance(raw, players), root=root, store_full_players=False)
    assert first.exists() and later.exists() and first != later
    assert len(list((root / "2026").iterdir())) == 2


def test_no_staging_directory_survives_a_failed_write(tmp_path):
    raw = make_raw(n=5)
    players = make_players(raw)
    df = cms.normalize_projections(raw, players, 2026)
    root = tmp_path / "arch"
    dt = datetime(2026, 8, 3, 13, 0, 0, tzinfo=timezone.utc)
    cms.write_snapshot(2026, dt, b"A", raw, players, df, provenance(raw, players),
                       root=root, store_full_players=False)
    with pytest.raises(FileExistsError):
        cms.write_snapshot(2026, dt, b"A", raw, players, df, provenance(raw, players),
                           root=root, store_full_players=False)
    leftovers = [p for p in (root / "2026").iterdir() if p.name.startswith(".incoming")]
    assert not leftovers, f"staging dir leaked after a failed write: {leftovers}"


# ----------------------------------------------------------------------------- health checks
@pytest.mark.parametrize("label,kwargs,status,expect", [
    ("truncated/low row count", dict(n=10), 200, "record_count"),
    ("all-sentinel ADP", dict(sentinel_all=True), 200, "real ADP"),
    ("missing scoring family", dict(drop_family="pts_"), 200, "scoring_totals"),
    ("missing games family", dict(drop_family="gp"), 200, "games"),
])
def test_unhealthy_responses_are_rejected(label, kwargs, status, expect):
    raw = make_raw(**kwargs)
    players = make_players(raw)
    df = cms.normalize_projections(raw, players, 2026)
    ok, problems = cms.health_check(raw, df, status, "application/json")
    assert not ok, f"{label} should have been rejected"
    assert any(expect in p for p in problems), f"{label}: {problems}"


def test_http_and_payload_failures_are_rejected():
    raw = make_raw()
    players = make_players(raw)
    df = cms.normalize_projections(raw, players, 2026)
    ok, problems = cms.health_check(raw, df, 503, "application/json")
    assert not ok and any("http_status=503" in p for p in problems)

    ok, problems = cms.health_check(raw, df, 200, "text/html")
    assert not ok and any("content_type" in p for p in problems)

    ok, problems = cms.health_check(["not", "a", "dict"], df, 200, "application/json")
    assert not ok and any("expected dict" in p for p in problems)


def test_duplicate_player_ids_are_rejected():
    raw = make_raw()
    players = make_players(raw)
    df = cms.normalize_projections(raw, players, 2026)
    dup = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    ok, problems = cms.health_check(raw, dup, 200, "application/json")
    assert not ok and any("duplicate sleeper_id" in p for p in problems)


def test_a_healthy_response_passes():
    raw = make_raw()
    players = make_players(raw)
    df = cms.normalize_projections(raw, players, 2026)
    ok, problems = cms.health_check(raw, df, 200, "application/json")
    assert ok, problems


# ----------------------------------------------------------------------------- failure isolation
def test_failed_attempt_never_enters_the_valid_index(tmp_path, monkeypatch):
    """A short pull must land in failures.jsonl and _failed/, never in manifest.jsonl."""
    raw = make_raw(n=10)                       # below MIN_RECORDS
    players = make_players(raw)

    class FakeResp:
        def __init__(self, payload, status=200):
            self.content = json.dumps(payload).encode()
            self.status_code = status
            self.headers = {"Content-Type": "application/json", "Date": "Mon, 03 Aug 2026 13:00:00 GMT"}

    calls = {"n": 0}

    def fake_fetch(url, timeout=90):
        calls["n"] += 1
        return FakeResp(raw) if "projections" in url else FakeResp(players)

    monkeypatch.setattr(cms, "_fetch", fake_fetch)
    root = tmp_path / "arch"
    row = cms.capture(2026, root=root, store_full_players=False)

    assert row["status"] == "failed" and "record_count" in row["diagnostic"]
    assert not (root / "manifest.jsonl").exists(), "a failed attempt must not create the manifest"
    assert (root / "failures.jsonl").exists()
    assert (root / "_failed" / row["capture_id"]).is_dir(), "rejected bytes should be quarantined"
    assert not (root / "2026").exists(), "no snapshot directory may be published for a failure"


def test_successful_capture_indexes_and_hashes(tmp_path, monkeypatch):
    raw = make_raw()
    players = make_players(raw)

    class FakeResp:
        def __init__(self, payload):
            self.content = json.dumps(payload).encode()
            self.status_code = 200
            self.headers = {"Content-Type": "application/json",
                            "Date": "Mon, 03 Aug 2026 13:00:00 GMT", "ETag": "W/\"abc\""}

    monkeypatch.setattr(cms, "_fetch",
                        lambda url, timeout=90: FakeResp(raw if "projections" in url else players))
    root = tmp_path / "arch"
    row = cms.capture(2026, root=root, store_full_players=True)

    assert row["status"] == "success", row.get("diagnostic")
    assert row["record_count"] == len(raw) and row["normalized_rows"] == len(raw)
    assert row["response_etag"] == 'W/"abc"' and row["response_date_header"]
    assert row["retrieved_utc"].endswith("+00:00") and row["retrieved_america_new_york"]
    assert row["capture_logic_sha256"] == cms.logic_sha256()

    lines = (root / "manifest.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["status"] == "success"

    snap = root / row["snapshot_dir"]
    meta = json.loads((snap / "metadata.json").read_text(encoding="utf-8"))
    for name in ("projections_raw.json.gz", "players_subset.json.gz", "normalized.csv"):
        assert meta["files"][name]["sha256"] == cms.sha256_file(snap / name), \
            f"metadata hash for {name} does not match the file on disk"
    assert row["normalized_sha256"] == cms.sha256_file(snap / "normalized.csv")
    stored = list((root / "_players_store").glob("*.json.gz"))
    assert len(stored) == 1, "full player directory should be stored content-addressed"


def test_second_capture_reuses_the_content_addressed_player_directory(tmp_path, monkeypatch):
    raw, players = make_raw(), None
    players = make_players(raw)

    class FakeResp:
        def __init__(self, payload):
            self.content = json.dumps(payload).encode()
            self.status_code = 200
            self.headers = {"Content-Type": "application/json"}

    monkeypatch.setattr(cms, "_fetch",
                        lambda url, timeout=90: FakeResp(raw if "projections" in url else players))
    root = tmp_path / "arch"
    cms.capture(2026, root=root)
    import time
    time.sleep(1.05)          # distinct second -> distinct snapshot dir
    cms.capture(2026, root=root)
    assert len(list((root / "_players_store").glob("*.json.gz"))) == 1, \
        "an unchanged player directory must be stored once, not per capture"
    assert len((root / "manifest.jsonl").read_text(encoding="utf-8").strip().splitlines()) == 2


# ----------------------------------------------------------------------------- self-interpretation
def test_snapshot_is_interpretable_from_its_own_frozen_player_mapping(tmp_path):
    """The stored subset must cover every id in the response, so a FUTURE mutable
    /players/nfl directory is never needed to read an old snapshot."""
    raw = make_raw(n=300)
    players = make_players(raw)
    df = cms.normalize_projections(raw, players, 2026)
    dt = datetime(2026, 8, 3, 13, 0, 0, tzinfo=timezone.utc)
    snap = cms.write_snapshot(2026, dt, json.dumps(raw).encode(), raw, players, df,
                              provenance(raw, players), root=tmp_path / "a",
                              store_full_players=False)

    subset = json.loads(gzip.decompress((snap / "players_subset.json.gz").read_bytes()))
    assert set(subset) == set(raw), "every response id must have frozen metadata beside it"
    for meta in subset.values():
        assert meta.get("full_name") and meta.get("position"), "join keys must be frozen too"

    # re-normalize using ONLY the frozen subset (no newer directory) -> same result
    again = cms.normalize_projections(raw, subset, 2026)
    pd.testing.assert_frame_equal(df, again)

    # and a snapshot normalized WITHOUT metadata is visibly degraded, proving the subset matters
    blind = cms.normalize_projections(raw, {}, 2026)
    assert blind["player"].isna().all() and not df["player"].isna().any()


def test_normalized_keeps_every_source_field_not_a_subset():
    """fetch_adp.py keeps 15 hand-picked fields; the archive must keep them all."""
    raw = make_raw(n=50)
    players = make_players(raw)
    df = cms.normalize_projections(raw, players, 2026)
    source_fields = set().union(*(set(r) for r in raw.values()))
    missing = source_fields - set(df.columns)
    assert not missing, f"archive dropped source fields: {sorted(missing)}"
    # and it keeps players fetch_adp would have filtered out (sentinel ADP / non-skill)
    sent = make_raw(n=50, sentinel_all=True)
    assert len(cms.normalize_projections(sent, make_players(sent), 2026)) == 50, \
        "undrafted (sentinel-ADP) players must be archived, not dropped"


# ----------------------------------------------------------------------------- fences
def test_board_overlay_contract_is_unchanged():
    """The archive must not have altered the live board's output contract."""
    import refresh_board_adp as rb
    universe = pd.DataFrame({"player_id": ["a", "b"], "player": ["Player A", "Player B"],
                             "position": ["RB", "WR"], "adp_frozen": [10.0, 20.0]})
    fresh = pd.DataFrame({"player": ["Player A"], "position": ["RB"], "adp_half_ppr": [12.0]})
    overlay, matched = rb.build_overlay(universe, fresh, "2026-08-03")
    assert list(overlay.columns) == ["player_id", "adp_half_ppr", "adp_pos_rank", "refreshed_at"]
    assert len(overlay) == 2 and matched == 1


def test_private_archive_path_is_version_control_ignored():
    probe = "fantasy/seasonal_projections/market_snapshots/2026/2026-08-03T130000Z/normalized.csv"
    r = subprocess.run(["git", "-c", "safe.directory=*", "check-ignore", "-v", probe],
                       cwd=str(_ROOT), capture_output=True, text=True)
    assert r.returncode == 0 and "market_snapshots" in r.stdout, \
        f"private archive is NOT gitignored: rc={r.returncode} out={r.stdout!r} err={r.stderr!r}"


def test_capture_module_writes_nothing_to_the_shipped_surface():
    """No shipped artifact may be named in EXECUTABLE code.

    The scan deliberately parses the AST and drops every docstring first: the module docstring
    names those files precisely to say it does NOT touch them, and a naive substring scan would
    fail on its own disclaimer. Only string constants that survive as real code are checked.
    """
    import ast
    tree = ast.parse(Path(cms.__file__).read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            d = ast.get_docstring(node, clean=False)
            if d:
                docstrings.add(d)
    live = [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value not in docstrings]
    blob = chr(10).join(live)
    for forbidden in ("board_adp_live_2026.csv", "season_dataset_2014_2026.csv",
                      "sleeper_adp_2020_2026.csv", "phase4_band_2026.csv", "talent_index_2026.csv"):
        assert forbidden not in blob, f"capture module references a shipped artifact: {forbidden}"
    assert any("market_snapshots" in v for v in live), "sanity: the scan must see real code strings"
