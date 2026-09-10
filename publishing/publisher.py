"""Immutable publication and pointer-only rollback."""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from .contract import PublicationError, sha256_file, utc_now_iso
from .manifest import load_manifest, published_builds, write_manifest
from .paths import releases_root, relative_to_site, resolve_site_path
from .validators import read_metadata, read_table, validate_candidate

CORRECTION_LINE_COLUMNS = (
    "game_id",
    "home_team",
    "away_team",
    "tuesday_median_spread_line",
)


def _build_id(metadata: dict) -> str:
    product = str(metadata["product"])
    season = int(metadata["season"])
    week = int(metadata["week"])
    digest = str(metadata["artifact_sha256"])
    return f"{product}-{season}w{week:02d}-{digest[:12]}"


def _high_game_ids(frame) -> set[str]:
    """Return the explicitly released HIGH set; blank means not HIGH."""
    if "consensus_tier" not in frame:
        return set()
    tiers = frame["consensus_tier"].fillna("").astype(str).str.strip().str.upper()
    return set(frame.loc[tiers.eq("HIGH"), "game_id"].astype(str))


def _validated_correction(source: Path, metadata: dict, root) -> dict | None:
    correction = metadata.get("correction")
    if correction is None:
        return None
    if metadata.get("product") != "predictions" or not isinstance(correction, dict):
        raise PublicationError("correction metadata is only valid for prediction releases")
    supersedes = str(correction.get("supersedes_build_id") or "").strip()
    reason = str(correction.get("reason") or "").strip()
    snapshot_hash = str(correction.get("source_snapshot_sha256") or "").strip().lower()
    if not supersedes or not reason:
        raise PublicationError("correction requires supersedes_build_id and reason")
    if not re.fullmatch(r"[0-9a-f]{64}", snapshot_hash):
        raise PublicationError("correction source_snapshot_sha256 must be a SHA-256 digest")
    try:
        snapshot_at = datetime.fromisoformat(
            str(correction.get("source_snapshot_captured_at") or "").replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise PublicationError("correction source_snapshot_captured_at must include a timezone") from exc
    if snapshot_at.tzinfo is None or snapshot_at.utcoffset() is None:
        raise PublicationError("correction source_snapshot_captured_at must include a timezone")

    manifest = load_manifest(root, strict=True)
    state = manifest["products"]["predictions"]
    active_build = state.get("active_build")
    candidate_build = _build_id(metadata)
    existing_candidate = state.get("builds", {}).get(candidate_build)
    is_idempotent_retry = (
        active_build == candidate_build
        and isinstance(existing_candidate, dict)
        and existing_candidate.get("correction", {}).get("supersedes_build_id") == supersedes
    )
    if active_build != supersedes and not is_idempotent_retry:
        raise PublicationError("correction must supersede the active prediction build")
    prior = state.get("builds", {}).get(supersedes)
    if not isinstance(prior, dict):
        raise PublicationError(f"correction references unknown build {supersedes!r}")
    if (
        int(prior.get("season", -1)) != int(metadata["season"])
        or int(prior.get("week", -1)) != int(metadata["week"])
    ):
        raise PublicationError("correction season/week differs from the superseded build")
    if str(prior.get("model_version")) != str(metadata.get("model_version")):
        raise PublicationError("correction must use the superseded build's frozen model")

    prior_frame = read_table(resolve_site_path(prior["artifact"], root))
    current_frame = read_table(source)
    missing = [
        col for col in CORRECTION_LINE_COLUMNS
        if col not in prior_frame.columns or col not in current_frame.columns
    ]
    if missing:
        raise PublicationError(f"correction comparison is missing columns: {', '.join(missing)}")
    prior_lines = prior_frame[list(CORRECTION_LINE_COLUMNS)].sort_values("game_id").reset_index(drop=True)
    current_lines = current_frame[list(CORRECTION_LINE_COLUMNS)].sort_values("game_id").reset_index(drop=True)
    if not prior_lines[["game_id", "home_team", "away_team"]].equals(
        current_lines[["game_id", "home_team", "away_team"]]
    ):
        raise PublicationError("correction schedule differs from the superseded build")
    prior_spreads = pd.to_numeric(prior_lines["tuesday_median_spread_line"], errors="coerce")
    current_spreads = pd.to_numeric(current_lines["tuesday_median_spread_line"], errors="coerce")
    if prior_spreads.isna().any() or current_spreads.isna().any() or not prior_spreads.equals(current_spreads):
        raise PublicationError("correction changed the frozen Tuesday median lines")
    return dict(correction)


def _reject_high_promotions(
    source: Path,
    product: str,
    season: int,
    week: int,
    root,
    *,
    correction: dict | None = None,
) -> None:
    """A later public build may demote an initial HIGH, never add one."""
    if product != "predictions" or season < 2026:
        return
    matching = [
        build for build in published_builds(product, root=root)
        if int(build["season"]) == season and int(build["week"]) == week
    ]
    if not matching:
        return
    if correction is not None:
        return
    initial = matching[0]
    initial_frame = read_table(resolve_site_path(initial["artifact"], root))
    allowed = _high_game_ids(initial_frame)
    candidate = _high_game_ids(read_table(source))
    promoted = sorted(candidate - allowed)
    if promoted:
        raise PublicationError(
            "later prediction releases cannot promote new HIGH games; "
            f"initial={sorted(allowed)} promoted={promoted}"
        )


def publish_candidate(
    artifact: str | Path,
    metadata: str | Path | dict,
    *,
    schedule=None,
    root=None,
    activate: bool = True,
    published_at: datetime | None = None,
) -> dict:
    source = Path(artifact)
    meta = read_metadata(metadata)
    correction = _validated_correction(source, meta, root)
    report = validate_candidate(
        source,
        meta,
        schedule=schedule,
        allow_post_kickoff_correction=correction is not None,
    )
    report.require_ok()
    build_id = _build_id(meta)
    product = str(meta["product"])
    season, week = int(meta["season"]), int(meta["week"])
    _reject_high_promotions(
        source,
        product,
        season,
        week,
        root,
        correction=correction,
    )
    build_dir = releases_root(root) / "builds" / product / str(season) / f"week{week:02d}" / build_id
    build_dir.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower()
    if suffix not in {".csv", ".parquet", ".pq"}:
        raise PublicationError(f"unsupported artifact format {suffix!r}")
    stored_artifact = build_dir / f"artifact{suffix}"
    stored_metadata = build_dir / "metadata.json"

    if stored_artifact.exists():
        if sha256_file(stored_artifact) != meta["artifact_sha256"]:
            raise PublicationError(f"immutable build collision at {build_dir}")
    else:
        shutil.copy2(source, stored_artifact)
    normalized_meta = dict(meta)
    normalized_meta["validation"] = report.to_dict()
    if stored_metadata.exists():
        existing = json.loads(stored_metadata.read_text(encoding="utf-8"))
        immutable_fields = (
            "schema_version", "product", "season", "week", "model_version",
            "produced_at", "artifact_sha256", "expected_rows",
        )
        if any(existing.get(key) != normalized_meta.get(key) for key in immutable_fields):
            raise PublicationError(f"immutable metadata collision at {stored_metadata}")
    else:
        stored_metadata.write_text(
            json.dumps(normalized_meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    manifest = load_manifest(root)
    state = manifest["products"][product]
    existing_entry = state["builds"].get(build_id, {})
    entry = {
        "build_id": build_id,
        "product": product,
        "season": season,
        "week": week,
        "model_version": str(meta["model_version"]),
        "produced_at": str(meta["produced_at"]),
        "published_at": existing_entry.get("published_at") or utc_now_iso(published_at),
        "status": "Published",
        "artifact": relative_to_site(stored_artifact, root),
        "metadata": relative_to_site(stored_metadata, root),
        "sha256": str(meta["artifact_sha256"]),
        "row_count": int(report.row_count),
        "validation": report.to_dict(),
    }
    if correction is not None:
        entry["correction"] = correction
    if existing_entry.get("grading"):
        entry["grading"] = existing_entry["grading"]
    state["builds"][build_id] = entry
    if activate:
        prior = state.get("active_build")
        if prior != build_id:
            state["previous_build"] = prior
            state["active_build"] = build_id
    write_manifest(manifest, root)
    return entry


def activate_release(product: str, build_id: str, *, root=None) -> dict:
    manifest = load_manifest(root, strict=True)
    state = manifest["products"].get(product)
    if state is None or build_id not in state.get("builds", {}):
        raise PublicationError(f"unknown {product} build {build_id!r}")
    build = state["builds"][build_id]
    artifact = resolve_site_path(build["artifact"], root)
    if not artifact.is_file() or sha256_file(artifact) != build.get("sha256"):
        raise PublicationError(f"build {build_id!r} is missing or fails its stored hash")
    prior = state.get("active_build")
    if prior != build_id:
        state["previous_build"] = prior
        state["active_build"] = build_id
    write_manifest(manifest, root)
    return dict(build)


def rollback_release(product: str, build_id: str | None = None, *, root=None) -> dict:
    manifest = load_manifest(root, strict=True)
    state = manifest["products"].get(product)
    if state is None:
        raise PublicationError(f"unknown product {product!r}")
    target = build_id or state.get("previous_build")
    if not target:
        raise PublicationError(f"{product} has no previous build to roll back to")
    return activate_release(product, str(target), root=root)


def schedule_release(
    product: str,
    season: int,
    week: int,
    *,
    scheduled_for: str | None,
    root=None,
) -> dict:
    manifest = load_manifest(root)
    state = manifest["products"].get(product)
    if state is None:
        raise PublicationError(f"unknown product {product!r}")
    state["next_release"] = {
        "season": int(season),
        "week": int(week),
        "scheduled_for": scheduled_for,
        "status": "Scheduled" if scheduled_for else "Awaiting projections",
    }
    write_manifest(manifest, root)
    return dict(state["next_release"])
