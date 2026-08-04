"""Dated point-in-time capture of Sleeper's 2026 ADP + projections — RESEARCH EVIDENCE ONLY.

WHY THIS EXISTS
---------------
The ADP-consensus study (fantasy/projections/research/adp_consensus_agreement_2026-08-02)
can only be certified `LIMITED CONFIDENCE` because Sleeper's historical endpoint carries NO
observation timestamp: the stored projection is a week-1-eve value while ADP is an
untimestamped summer aggregate, so the two sides of every 2021-2025 comparison have unknown
and probably different information cutoffs. That cannot be fixed retrospectively. It CAN be
fixed prospectively, by archiving the endpoint every day of the 2026 preseason so that a
future study can compare projection, market and model at genuinely matched cutoffs.

WHAT IT CAPTURES
----------------
Both halves of one retrieval event, so ADP and projections always share a timestamp:
  * the EXACT raw response bytes of /projections/nfl/regular/<season>, gzipped, unparsed;
  * the contemporaneous /players/nfl metadata for every player id in that response, so an old
    snapshot is interpretable WITHOUT consulting a newer, mutable player directory;
  * a normalized CSV carrying EVERY field the source supplied (the union of all keys across
    all records) — not the hand-picked subset fetch_adp.py keeps for the season dataset;
  * a provenance record: UTC + America/New_York timestamps, endpoint, HTTP status,
    content-type, Date/ETag/Last-Modified headers, SHA-256 of the raw bytes and of every
    normalized output, row/unique-id/field counts, and the SHA-256 of THIS module.

FENCE (mirrors adp_logs/, see .gitignore)
-----------------------------------------
market_snapshots/ is PRIVATE and gitignored. This archive is research evidence. It is NOT an
input to the live Draft Board, to player recommendations, or to video selection, and nothing
in the shipped surface reads it. It does not touch board_adp_live_2026.csv, the season
dataset, the ADP cache, or any frozen artifact.

HONEST LIMIT: capture began 2026-08-03. August 1-2 2026 have NO archived snapshot and must
never be backfilled from current data under a historical label — a value fetched later is not
a point-in-time observation of an earlier date.

Run:  python fantasy/seasonal_projections/capture_market_snapshot.py [--season 2026] [--dry-run]
"""
import argparse
import gzip
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _utils import norm_name

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ----------------------------------------------------------------------------- configuration
BASE = "https://api.sleeper.app/v1"
PROJ_ENDPOINT = BASE + "/projections/nfl/regular/{season}"
PLAYERS_ENDPOINT = BASE + "/players/nfl"
HEADERS = {"User-Agent": "Mozilla/5.0 (JoSchoAnalytics point-in-time market archive)"}

SNAP_ROOT = HERE / "market_snapshots"          # PRIVATE — gitignored
MANIFEST = SNAP_ROOT / "manifest.jsonl"        # append-only, SUCCESSFUL captures only
FAILURES = SNAP_ROOT / "failures.jsonl"        # append-only, failed attempts (never in manifest)
FAILED_DIR = SNAP_ROOT / "_failed"
PLAYERS_STORE = SNAP_ROOT / "_players_store"   # content-addressed full player directory

DEFAULT_SEASON = 2026
CAPTURE_LOGIC_VERSION = "1.0.0"

# --- health thresholds: a response failing any of these is NOT a valid snapshot ---
MIN_RECORDS = 2000            # /projections returns ~9k records for a live season
MIN_WITH_ADP = 150            # matches refresh_board_adp.MIN_PULL_PLAYERS floor
MAX_NULL_SHARE = 0.98         # a field family that is >98% null across records is "missing"
ADP_SENTINEL = 999.0          # Sleeper's "undrafted" marker
REQUIRED_FIELD_FAMILIES = {
    "adp": ("adp_half_ppr", "adp_ppr", "adp_std", "adp_2qb", "adp_dynasty", "adp_rookie"),
    "scoring_totals": ("pts_half_ppr", "pts_ppr", "pts_std"),
    "games": ("gp",),
}


# ----------------------------------------------------------------------------- helpers (pure)
def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def logic_sha256() -> str:
    """SHA-256 of this module — pins the capture/normalization logic to each snapshot."""
    return sha256_file(Path(__file__).resolve())


def _ny_timestamp(dt: datetime) -> str:
    """America/New_York wall time. zoneinfo on Windows needs tzdata; fall back to a fixed
    EDT/EST offset by month rather than silently mislabelling the field."""
    try:
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo("America/New_York")).isoformat(timespec="seconds")
    except Exception:
        from datetime import timedelta
        # DST in the US runs 2nd Sun Mar - 1st Sun Nov; month-level approximation is enough
        # for a provenance label and is explicitly marked approximate in the metadata.
        offset = -4 if 3 <= dt.month <= 10 else -5
        return (dt + timedelta(hours=offset)).replace(tzinfo=None).isoformat(timespec="seconds") \
            + f"{offset:+03d}:00~"


def normalize_projections(raw_obj: dict, players_obj: dict, season: int) -> pd.DataFrame:
    """Every record, every field — no position filter, no ADP filter, no field selection.

    Deliberately unlike fetch_adp.fetch_season, which drops undrafted players, non-skill
    positions and all but 15 hand-picked fields. An archive that pre-selects cannot answer a
    question nobody has asked yet, so the union of all keys across all records is kept and the
    frame is sorted by sleeper_id so row order can never change the content hash.
    """
    keys = set()
    for rec in raw_obj.values():
        if isinstance(rec, dict):
            keys.update(rec.keys())
    stat_cols = sorted(keys)

    rows = []
    for pid, rec in raw_obj.items():
        if not isinstance(rec, dict):
            continue
        meta = (players_obj or {}).get(str(pid)) or {}
        full = meta.get("full_name") or " ".join(
            x for x in (meta.get("first_name"), meta.get("last_name")) if x).strip()
        fp = meta.get("fantasy_positions") or []
        row = {
            "season": season,
            "sleeper_id": str(pid),
            "player": full or None,
            "norm_name": norm_name(full) if full else None,
            "position": meta.get("position") or (fp[0] if fp else None),
            "fantasy_positions": ",".join(fp) if fp else None,
            "team": meta.get("team"),
            "status": meta.get("status"),
            "years_exp": meta.get("years_exp"),
            "gsis_id": meta.get("gsis_id"),
            "meta_present": bool(meta),
        }
        for c in stat_cols:
            row[c] = rec.get(c)
        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("sleeper_id", kind="mergesort").reset_index(drop=True)


def players_subset(raw_obj: dict, players_obj: dict) -> dict:
    """Contemporaneous metadata for exactly the ids in this projections response.

    This is what makes an old snapshot self-interpreting: the join keys and names are frozen
    beside the values they describe, so no future mutable /players/nfl directory is needed.
    """
    out = {}
    for pid in raw_obj:
        meta = (players_obj or {}).get(str(pid))
        if meta is not None:
            out[str(pid)] = meta
    return out


def health_check(raw_obj, df: pd.DataFrame, http_status: int, content_type: str) -> tuple:
    """Return (ok, problems). A snapshot failing ANY check is recorded as a failure and is
    never written into the valid index — a short or malformed pull must not look like a
    legitimate observation of a quiet market day."""
    problems = []
    if http_status != 200:
        problems.append(f"http_status={http_status}")
    if content_type and "json" not in content_type.lower():
        problems.append(f"content_type={content_type!r}")
    if not isinstance(raw_obj, dict):
        problems.append(f"payload is {type(raw_obj).__name__}, expected dict")
        return False, problems
    if len(raw_obj) < MIN_RECORDS:
        problems.append(f"record_count={len(raw_obj)} < floor {MIN_RECORDS}")
    if df is None or df.empty:
        problems.append("normalized frame is empty")
        return False, problems
    if df["sleeper_id"].duplicated().any():
        problems.append(f"duplicate sleeper_id x{int(df.sleeper_id.duplicated().sum())}")

    for family, cols in REQUIRED_FIELD_FAMILIES.items():
        present = [c for c in cols if c in df.columns]
        if not present:
            problems.append(f"missing field family {family!r} (none of {cols})")
            continue
        if all(df[c].isna().mean() > MAX_NULL_SHARE for c in present):
            problems.append(f"field family {family!r} is >{MAX_NULL_SHARE:.0%} null")

    if "adp_half_ppr" in df.columns:
        real = df["adp_half_ppr"].astype("float64")
        n_real = int(((real.notna()) & (real < ADP_SENTINEL)).sum())
        if n_real < MIN_WITH_ADP:
            problems.append(f"players with real ADP={n_real} < floor {MIN_WITH_ADP}")
    else:
        problems.append("adp_half_ppr column absent")

    return (not problems), problems


def snapshot_dirname(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H%M%SZ")


# ----------------------------------------------------------------------------- io (atomic)
def _write_gz_bytes(raw: bytes, path: Path) -> None:
    """mtime=0 + an empty embedded filename make the gzip container byte-deterministic, so
    identical input always produces an identical file hash."""
    with open(path, "wb") as fh:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0) as gz:
            gz.write(raw)


def _write_gz_json(obj, path: Path) -> None:
    _write_gz_bytes(json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8"), path)


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def write_snapshot(season: int, dt: datetime, raw_bytes: bytes, raw_obj: dict,
                   players_obj: dict, df: pd.DataFrame, provenance: dict,
                   root: Path = None, store_full_players: bool = True) -> Path:
    """Write one capture ATOMICALLY: everything lands in a staging directory that is renamed
    into place only once complete, so an interrupted fetch can never masquerade as a valid
    snapshot. Never overwrites: the destination is timestamped to the second and a collision
    raises rather than clobbering a prior capture."""
    root = Path(root or SNAP_ROOT)
    season_dir = root / str(season)
    season_dir.mkdir(parents=True, exist_ok=True)
    final = season_dir / snapshot_dirname(dt)
    if final.exists():
        raise FileExistsError(f"snapshot already exists, refusing to overwrite: {final}")

    staging = Path(tempfile.mkdtemp(prefix=".incoming-", dir=str(season_dir)))
    try:
        _write_gz_bytes(raw_bytes, staging / "projections_raw.json.gz")
        _write_gz_json(players_subset(raw_obj, players_obj), staging / "players_subset.json.gz")
        df.to_csv(staging / "normalized.csv", index=False, lineterminator="\n")

        meta = dict(provenance)
        meta["files"] = {
            n: {"sha256": sha256_file(staging / n), "bytes": (staging / n).stat().st_size}
            for n in ("projections_raw.json.gz", "players_subset.json.gz", "normalized.csv")
        }
        (staging / "metadata.json").write_text(
            json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(str(staging), str(final))
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    # full player directory, content-addressed so an unchanged directory is stored once
    if store_full_players and players_obj:
        store = root / "_players_store"
        store.mkdir(parents=True, exist_ok=True)
        digest = provenance.get("players_raw_sha256") or sha256_bytes(
            json.dumps(players_obj, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        dest = store / f"{digest}.json.gz"
        if not dest.exists():
            fd, tmp = tempfile.mkstemp(dir=str(store), suffix=".tmp")
            os.close(fd)
            _write_gz_json(players_obj, Path(tmp))
            os.replace(tmp, dest)
    return final


# ----------------------------------------------------------------------------- capture (network)
def _fetch(url: str, timeout: int = 90):
    import requests
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    return r


def capture(season: int = DEFAULT_SEASON, root: Path = None,
            store_full_players: bool = True) -> dict:
    """One capture attempt. Returns the manifest/failure row. Never raises on a bad response —
    an unhealthy pull is recorded as a FAILURE, not published as a snapshot."""
    root = Path(root or SNAP_ROOT)
    dt = datetime.now(timezone.utc)
    base_row = {
        "capture_id": snapshot_dirname(dt),
        "season": season,
        "retrieved_utc": dt.isoformat(timespec="seconds"),
        "retrieved_america_new_york": _ny_timestamp(dt),
        "projections_endpoint": PROJ_ENDPOINT.format(season=season),
        "players_endpoint": PLAYERS_ENDPOINT,
        "capture_logic_version": CAPTURE_LOGIC_VERSION,
        "capture_logic_sha256": logic_sha256(),
    }
    try:
        rp = _fetch(PROJ_ENDPOINT.format(season=season))
        raw_bytes = rp.content
        rq = _fetch(PLAYERS_ENDPOINT)
        players_bytes = rq.content
    except Exception as e:
        row = {**base_row, "status": "failed",
               "diagnostic": f"fetch error: {type(e).__name__}: {e}"}
        _append_jsonl(root / "failures.jsonl", row)
        return row

    base_row.update({
        "http_status": rp.status_code,
        "content_type": rp.headers.get("Content-Type"),
        "response_date_header": rp.headers.get("Date"),
        "response_etag": rp.headers.get("ETag"),
        "response_last_modified": rp.headers.get("Last-Modified"),
        "raw_bytes": len(raw_bytes),
        "projections_raw_sha256": sha256_bytes(raw_bytes),
        "players_http_status": rq.status_code,
        "players_raw_bytes": len(players_bytes),
        "players_raw_sha256": sha256_bytes(players_bytes),
    })

    try:
        raw_obj = json.loads(raw_bytes.decode("utf-8"))
        players_obj = json.loads(players_bytes.decode("utf-8")) if rq.status_code == 200 else {}
    except Exception as e:
        row = {**base_row, "status": "failed",
               "diagnostic": f"json parse: {type(e).__name__}: {e}"}
        _append_jsonl(root / "failures.jsonl", row)
        _quarantine(root, base_row["capture_id"], raw_bytes)
        return row

    df = normalize_projections(raw_obj, players_obj, season) if isinstance(raw_obj, dict) \
        else pd.DataFrame()
    ok, problems = health_check(raw_obj, df, rp.status_code, base_row.get("content_type") or "")

    base_row.update({
        "record_count": len(raw_obj) if isinstance(raw_obj, dict) else 0,
        "normalized_rows": int(len(df)),
        "unique_sleeper_ids": int(df.sleeper_id.nunique()) if len(df) else 0,
        "normalized_columns": int(df.shape[1]) if len(df) else 0,
        "players_with_real_adp": int(((df.get("adp_half_ppr").notna()) &
                                      (df.get("adp_half_ppr") < ADP_SENTINEL)).sum())
        if len(df) and "adp_half_ppr" in df.columns else 0,
        "metadata_matched": int(df.meta_present.sum()) if len(df) else 0,
        "health_problems": problems,
    })

    if not ok:
        row = {**base_row, "status": "failed",
               "diagnostic": "unhealthy response: " + "; ".join(problems)}
        _append_jsonl(root / "failures.jsonl", row)
        _quarantine(root, base_row["capture_id"], raw_bytes)
        return row

    path = write_snapshot(season, dt, raw_bytes, raw_obj, players_obj, df, base_row,
                          root=root, store_full_players=store_full_players)
    row = {**base_row, "status": "success",
           "snapshot_dir": str(path.relative_to(root)).replace("\\", "/"),
           "normalized_sha256": sha256_file(path / "normalized.csv"),
           "players_subset_sha256": sha256_file(path / "players_subset.json.gz"),
           "diagnostic": "ok"}
    _append_jsonl(root / "manifest.jsonl", row)
    return row


def _quarantine(root: Path, capture_id: str, raw_bytes: bytes) -> None:
    """Keep the bytes of a rejected response for diagnosis, well away from the valid index."""
    d = root / "_failed" / capture_id
    d.mkdir(parents=True, exist_ok=True)
    try:
        _write_gz_bytes(raw_bytes, d / "projections_raw.json.gz")
    except Exception:
        pass


# ----------------------------------------------------------------------------- cli
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--season", type=int, default=DEFAULT_SEASON)
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch and validate but write no snapshot (prints the health report)")
    ap.add_argument("--no-full-players-store", action="store_true",
                    help="skip the content-addressed copy of the full /players/nfl directory")
    a = ap.parse_args()

    if a.dry_run:
        dt = datetime.now(timezone.utc)
        rp = _fetch(PROJ_ENDPOINT.format(season=a.season))
        rq = _fetch(PLAYERS_ENDPOINT)
        raw_obj = json.loads(rp.content.decode("utf-8"))
        players_obj = json.loads(rq.content.decode("utf-8"))
        df = normalize_projections(raw_obj, players_obj, a.season)
        ok, problems = health_check(raw_obj, df, rp.status_code, rp.headers.get("Content-Type", ""))
        print(f"DRY RUN {snapshot_dirname(dt)}  records={len(raw_obj)} rows={len(df)} "
              f"cols={df.shape[1]} healthy={ok} problems={problems or 'none'}")
        return 0 if ok else 1

    row = capture(a.season, store_full_players=not a.no_full_players_store)
    if row["status"] == "success":
        print(f"capture OK {row['capture_id']}  season={row['season']}  "
              f"records={row['record_count']}  rows={row['normalized_rows']} x "
              f"{row['normalized_columns']} cols  real-ADP={row['players_with_real_adp']}")
        print(f"  raw sha256        {row['projections_raw_sha256']}")
        print(f"  normalized sha256 {row['normalized_sha256']}")
        print(f"  -> {row['snapshot_dir']}")
        return 0
    print(f"capture FAILED {row['capture_id']}: {row['diagnostic']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
