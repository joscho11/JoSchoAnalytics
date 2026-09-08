"""Create small, hash-bound sidecars for producer output candidates."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .contract import (
    PRODUCTS,
    SCHEMA_VERSION,
    candidate_sidecar_path,
    canonical_values_hash,
    parse_aware_datetime,
    sha256_file,
    utc_now_iso,
)


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    return pd.read_csv(path, dtype={"game_id": "string", "player_id": "string"})


def build_candidate_metadata(
    product: str,
    artifact: str | Path,
    *,
    season: int,
    week: int,
    model_version: str,
    produced_at: str,
    legacy_bootstrap: bool = False,
) -> dict:
    if product not in PRODUCTS:
        raise ValueError(f"product must be one of {PRODUCTS}, got {product!r}")
    if not str(model_version).strip():
        raise ValueError("model_version is required")
    parse_aware_datetime(produced_at)
    path = Path(artifact)
    frame = _read_table(path)
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "product": product,
        "season": int(season),
        "week": int(week),
        "model_version": str(model_version).strip(),
        "produced_at": utc_now_iso(parse_aware_datetime(produced_at)),
        "artifact_name": path.name,
        "artifact_sha256": sha256_file(path),
        "expected_rows": int(len(frame)),
        "legacy_bootstrap": bool(legacy_bootstrap),
    }
    if product == "predictions":
        if "game_id" in frame:
            metadata["expected_game_ids_sha256"] = canonical_values_hash(frame["game_id"])
        teams = set()
        for col in ("home_team", "away_team"):
            if col in frame:
                teams.update(frame[col].dropna().astype(str))
        metadata["expected_teams"] = sorted(team for team in teams if team)
    else:
        if "player_id" in frame:
            metadata["expected_player_ids_sha256"] = canonical_values_hash(frame["player_id"])
        aliases = []
        for alias in ("gsis_id", "sleeper_id"):
            if alias in frame:
                aliases.append(alias)
                metadata[f"expected_{alias}_sha256"] = canonical_values_hash(frame[alias].dropna())
        if aliases:
            metadata["identity_aliases"] = aliases
        metadata["position_counts"] = {
            str(key): int(value)
            for key, value in frame.get("position", pd.Series(dtype=str)).value_counts().sort_index().items()
        }
        metadata["expected_teams"] = sorted(
            set(frame.get("team", pd.Series(dtype=str)).dropna().astype(str))
        )
        if {"team", "position"} <= set(frame):
            metadata["team_position_counts"] = {
                str(team): {str(position): int(count) for position, count in counts.items()}
                for team, counts in frame.groupby("team")["position"].value_counts().unstack(
                    fill_value=0
                ).sort_index().to_dict(orient="index").items()
            }
    return metadata


def write_candidate_sidecar(
    product: str,
    artifact: str | Path,
    *,
    season: int,
    week: int,
    model_version: str,
    produced_at: str,
    legacy_bootstrap: bool = False,
    destination: str | Path | None = None,
) -> Path:
    metadata = build_candidate_metadata(
        product,
        artifact,
        season=season,
        week=week,
        model_version=model_version,
        produced_at=produced_at,
        legacy_bootstrap=legacy_bootstrap,
    )
    out = Path(destination) if destination is not None else candidate_sidecar_path(artifact)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return out
