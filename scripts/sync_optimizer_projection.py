"""Convert the active fantasy release into a checked DFS projection artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "site_pages")]

import dfs_runtime as runtime  # noqa: E402
from publishing.contract import sha256_file as published_artifact_sha256  # noqa: E402


def _release_games(frame: pd.DataFrame, norm_team) -> list[dict]:
    required = {"team", "opponent_team", "kickoff"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"active fantasy artifact is missing schedule columns: {missing}")

    games = set()
    for row in frame[["team", "opponent_team", "kickoff"]].drop_duplicates().itertuples(index=False):
        kickoff = pd.to_datetime(row.kickoff, utc=True, errors="coerce")
        teams = tuple(sorted((norm_team(row.team), norm_team(row.opponent_team))))
        if pd.isna(kickoff) or not all(teams):
            continue
        local_date = kickoff.tz_convert("America/New_York").strftime("%Y-%m-%d")
        games.add((local_date, teams))
    if not games:
        raise ValueError("active fantasy artifact has no usable game and kickoff metadata")
    return [
        {"date": date, "teams": list(teams)}
        for date, teams in sorted(games)
    ]


def _matchups(frame: pd.DataFrame, norm_team) -> set[tuple[str, str]]:
    return {
        tuple(sorted((norm_team(team), norm_team(opponent))))
        for team, opponent in frame[["team", "opponent_team"]].drop_duplicates().itertuples(index=False)
        if norm_team(team) and norm_team(opponent)
    }


def _replace_bytes(destination: Path, contents: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(contents)
    os.replace(temporary, destination)


def _canonical_csv_bytes(contents: bytes) -> bytes:
    """Use stable LF line endings so hashes survive Windows and Linux checkouts."""
    return contents.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def sync_active_release(
    *,
    root: Path,
    converter: Path,
    producer_revision: str,
) -> tuple[Path, Path] | None:
    if not re.fullmatch(r"[0-9a-f]{40}", producer_revision):
        raise ValueError("producer revision must be a full lowercase Git commit SHA")
    build, source_path = runtime.active_fantasy_source(root)
    if build is None or source_path is None:
        print("No checksum-verified active fantasy release; nothing to sync.")
        return None

    season, week = int(build["season"]), int(build["week"])
    build_id = str(build["build_id"])
    if not re.fullmatch(r"[A-Za-z0-9-]+", build_id):
        raise ValueError(f"unsafe active fantasy build id: {build_id!r}")
    source_sha256 = str(build["sha256"])
    if published_artifact_sha256(source_path) != source_sha256:
        raise ValueError("active fantasy artifact checksum does not match its manifest")
    # The public release contract canonicalizes text-artifact hashes so that a
    # Windows CRLF release and a Linux LF checkout have the same identity. The
    # producer sidecar hashes the exact bytes it read, so validate that against
    # this checkout's raw bytes before storing the canonical manifest hash.
    source_file_sha256 = runtime.file_sha256(source_path)

    source = pd.read_csv(source_path, dtype={"player_id": "string"})
    if not {"season", "week"}.issubset(source.columns):
        raise ValueError("active fantasy artifact is missing season/week columns")
    keys = source[["season", "week"]].apply(pd.to_numeric, errors="coerce").drop_duplicates()
    if len(keys) != 1 or (int(keys.iloc[0]["season"]), int(keys.iloc[0]["week"])) != (season, week):
        raise ValueError("active fantasy artifact rows do not match its manifest season/week")

    pipeline = runtime.load_pipeline()
    games = _release_games(source, pipeline.norm_team)
    destination_dir = (
        root / "fantasy" / "optimizer_projections" / str(season)
        / f"week{week:02d}" / build_id / producer_revision[:12]
    )
    destination = destination_dir / f"projections_{season}_week{week:02d}.csv"
    destination_metadata = destination.with_suffix(".json")

    existing = runtime.projection_metadata(destination)
    existing_is_canonical = destination.is_file() and b"\r" not in destination.read_bytes()
    if existing and existing_is_canonical and all((
        str(existing.get("source_build_id", "")) == build_id,
        str(existing.get("source_artifact_sha256", "")) == source_sha256,
        str(existing.get("producer_revision", "")) == producer_revision,
        existing.get("games") == games,
        bool(existing.get("synced_at_utc")),
    )):
        print(f"Already synced {build_id} with producer {producer_revision[:12]}.")
        return None

    converter = converter.resolve()
    if not converter.is_file():
        raise FileNotFoundError(f"DFS producer converter not found: {converter}")
    with tempfile.TemporaryDirectory(prefix="jsa-dfs-sync-") as temp_name:
        temporary_csv = Path(temp_name) / f"projections_{season}_week{week:02d}.csv"
        subprocess.run(
            [
                sys.executable, str(converter),
                "--artifact", str(source_path),
                "--season", str(season),
                "--week", str(week),
                "--source", "auto",
                "--out", str(temporary_csv),
            ],
            check=True,
            cwd=converter.parents[1],
        )
        temporary_metadata = temporary_csv.with_suffix(".json")
        if not temporary_csv.is_file() or not temporary_metadata.is_file():
            raise ValueError("DFS producer did not write both the CSV and checksum sidecar")

        projection = pd.read_csv(temporary_csv, dtype={"player_id": "string"})
        projected_season, projected_week = pipeline.validate_projection_frame(projection)
        if (projected_season, projected_week) != (season, week):
            raise ValueError("DFS conversion output does not match the active fantasy season/week")
        if "opponent_team" not in projection.columns:
            raise ValueError("DFS conversion output is missing opponent_team")
        if _matchups(projection, pipeline.norm_team) != _matchups(source, pipeline.norm_team):
            raise ValueError("DFS conversion matchups differ from the active fantasy release")

        metadata = json.loads(temporary_metadata.read_text(encoding="utf-8"))
        if metadata.get("source_artifact_sha256") != source_file_sha256:
            raise ValueError("DFS conversion sidecar is not bound to the active fantasy artifact bytes")
        projection_sha256 = runtime.file_sha256(temporary_csv)
        if metadata.get("projection_csv_sha256") != projection_sha256:
            raise ValueError("DFS conversion sidecar checksum does not match its CSV")
        projection_bytes = _canonical_csv_bytes(temporary_csv.read_bytes())
        metadata["projection_csv_sha256"] = hashlib.sha256(projection_bytes).hexdigest()
        metadata["source_build_id"] = build_id
        metadata["source_artifact"] = str(build["artifact"])
        metadata["source_artifact_sha256"] = source_sha256
        metadata["producer_revision"] = producer_revision
        metadata["games"] = games
        metadata["synced_at_utc"] = datetime.now(timezone.utc).isoformat()

        _replace_bytes(destination, projection_bytes)
        _replace_bytes(
            destination_metadata,
            (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
    print(f"Synced {build_id}: {destination.relative_to(root).as_posix()}")
    return destination, destination_metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--converter", type=Path, required=True)
    parser.add_argument("--producer-revision", required=True)
    args = parser.parse_args(argv)
    sync_active_release(
        root=args.root.resolve(),
        converter=args.converter,
        producer_revision=args.producer_revision,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
