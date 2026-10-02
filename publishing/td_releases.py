"""Canonical public TD artifacts and their prediction provenance.

Legacy exact weekly filenames remain readable. A versioned manifest binds a
replacement CSV to its metadata; suffixed release and backup files never win
by filename order. This module reads public CSV/JSON only.
"""
from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path

import pandas as pd

from .contract import PublicationError

MANIFEST_NAME = "releases_manifest.json"
_LEGACY = re.compile(r"anytime_td_(\d{4})_week(\d{2})\.csv")
MODES = {"live", "retrospective"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(directory: Path, value: str, suffix: str) -> Path:
    raw = Path(value)
    path = (directory / raw).resolve()
    if raw.is_absolute() or not path.is_relative_to(directory.resolve()) or path.suffix != suffix:
        raise PublicationError("TD manifest artifact must be a contained relative path")
    if not path.is_file():
        raise PublicationError(f"TD manifest artifact is missing: {value}")
    return path


def canonical_td_releases(directory: str | Path) -> dict[tuple[int, int], dict]:
    directory = Path(directory)
    found = {}
    if not directory.is_dir():
        return found
    for path in sorted(directory.glob("anytime_td_*_week*.csv")):
        match = _LEGACY.fullmatch(path.name)
        if match:
            season, week = map(int, match.groups())
            found[(season, week)] = {"season": season, "week": week, "csv_path": path,
                                      "prediction_mode": "live", "model_version": "legacy"}
    manifest_path = directory / MANIFEST_NAME
    if not manifest_path.exists():
        return found
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["schema_version"] != 1 or not isinstance(manifest["releases"], list):
            raise ValueError("unsupported schema")
        seen = set()
        seen_csv = set()
        for raw in manifest["releases"]:
            key = (int(raw["season"]), int(raw["week"]))
            if key in seen or not 1 <= key[1] <= 18:
                raise ValueError("duplicate or invalid week")
            seen.add(key)
            mode = raw["prediction_mode"]
            if mode not in MODES or not str(raw["model_version"]).strip():
                raise ValueError("invalid prediction provenance")
            csv_path = _artifact(directory, raw["csv"], ".csv")
            if csv_path in seen_csv:
                raise ValueError("CSV is bound to more than one week")
            seen_csv.add(csv_path)
            metadata_path = _artifact(directory, raw["metadata"], ".json")
            for field, path in (("csv_sha256", csv_path), ("metadata_sha256", metadata_path)):
                expected_hash = raw.get(field)
                if expected_hash is not None:
                    if not re.fullmatch(r"[0-9a-f]{64}", str(expected_hash)):
                        raise ValueError(f"invalid {field}")
                    if _sha256(path) != expected_hash:
                        raise ValueError(f"{field} mismatch for {path.name}")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            for field, expected in (("season", key[0]), ("week", key[1]),
                                    ("prediction_mode", mode), ("model_version", raw["model_version"])):
                if metadata.get(field) != expected:
                    raise ValueError(f"metadata disagrees on {field}")
            found[key] = {**raw, "csv_path": csv_path, "metadata_path": metadata_path}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise PublicationError(f"Invalid TD release manifest: {exc}") from exc
    return found


def release_for_path(path: str | Path) -> dict:
    path = Path(path)
    # Versioned artifacts may live beneath the public TD directory.
    directory = next((p for p in (path.parent, *path.parents) if (p / MANIFEST_NAME).is_file()), path.parent)
    return next((entry for entry in canonical_td_releases(directory).values()
                 if entry["csv_path"].resolve() == path.resolve()), {})


def read_td_release(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    entry = release_for_path(path)
    if "metadata_path" in entry:
        for column in ("season", "week"):
            if column not in frame or not pd.to_numeric(frame[column], errors="coerce").eq(entry[column]).all():
                raise PublicationError(f"TD release rows disagree on {column}")
    for column, default in (("prediction_mode", "live"), ("model_version", "legacy")):
        value = entry.get(column, default)
        if column not in frame:
            frame[column] = value
        elif frame[column].isna().any() or frame[column].astype(str).str.strip().eq("").any():
            raise PublicationError(f"TD release has missing {column}")
    if not set(frame["prediction_mode"]) <= MODES:
        raise PublicationError("TD release has unknown prediction_mode")
    # A reconstructed weekly release cannot relabel selected rows as live.
    if entry.get("prediction_mode") == "retrospective" and not frame["prediction_mode"].eq("retrospective").all():
        raise PublicationError("Retrospective TD release contains live rows")
    if entry.get("prediction_mode") == "retrospective" and not frame["model_version"].eq(entry["model_version"]).all():
        raise PublicationError("Retrospective TD release contains another model version")
    return frame
