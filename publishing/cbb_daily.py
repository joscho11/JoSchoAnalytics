"""Date-keyed immutable publication contract for College Basketball daily cards."""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Mapping
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .contract import PublicationError, parse_aware_datetime, sha256_file, utc_now_iso


ET = ZoneInfo("America/New_York")
UTC = timezone.utc
SEASON = 2027
THRESHOLD = 8.5
MODEL_HASH = "f83da7ac2015f8c23dfa41d52d5a2b1325ec0a7cad3e3b03e53bc2c957d27800"
FEATURE_HASH = "c08adcfed32f497bf98dbea61b203bb2df5d5a5b0554f02b135cd7b3eb1bf89f"
BENCHMARK_HASH = "7b038b0e82196fe88d5bd4c57b5834f7c7d3f3d3df5d50a31f5c7ac4284b2930"
POLICY_HASH = "79f5b87a552e2fbfd72e0578e500a1525cd492542e39d04850cb40da1d60a66d"

CARD_COLUMNS = (
    "game_id", "season", "game_date_et", "tipoff_utc",
    "home_team_id", "home_team", "away_team_id", "away_team",
    "neutral_site", "conference_game",
    "predicted_home_score", "predicted_away_score", "predicted_margin",
    "predicted_total", "predicted_winner", "home_win_probability",
    "market_home_spread", "market_home_margin", "provider_count",
    "market_status", "model_edge", "ats_pick", "ats_status",
    "prediction_at_utc", "line_retrieved_at_utc", "decision_time_utc",
    "model_hash", "feature_hash", "policy_hash", "prediction_run_hash",
    "ats_card_run_hash",
)
RESULT_COLUMNS = (
    "game_id", "game_date_et", "home_score", "away_score",
    "actual_home_margin", "actual_cover_margin", "ats_result",
    "finalized_at_utc", "source_card_build_id",
)
FORBIDDEN_CARD_COLUMNS = {
    "provider", "bookmaker", "raw_payload", "payload", "features", "spread_open",
    "moneyline", "over_under", "odds", "api_key", "secret",
}


def _root(root: str | Path | None) -> Path:
    return Path(root or Path(__file__).resolve().parents[1]).resolve()


def cbb_release_root(root: str | Path | None = None) -> Path:
    return _root(root) / "data" / "releases" / "cbb_daily"


def _empty_manifest() -> dict:
    return {
        "schema_version": 1,
        "product": "cbb_daily_spreads",
        "updated_at": None,
        "latest_date": None,
        "dates": {},
        "policy": {
            "season": SEASON,
            "threshold": THRESHOLD,
            "model_hash": MODEL_HASH,
            "feature_hash": FEATURE_HASH,
            "benchmark_hash": BENCHMARK_HASH,
            "policy_hash": POLICY_HASH,
            "status": "exploratory_shadow_only",
        },
    }


def _normalize_manifest(payload: dict) -> dict:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1 or payload.get("product") != "cbb_daily_spreads":
        return _empty_manifest()
    payload.setdefault("dates", {})
    payload.setdefault("latest_date", None)
    payload.setdefault("policy", _empty_manifest()["policy"])
    return payload


def load_cbb_manifest(root: str | Path | None = None, *, strict: bool = False) -> dict:
    path = cbb_release_root(root) / "manifest.json"
    if not path.is_file():
        if strict:
            raise FileNotFoundError(path)
        return _empty_manifest()
    try:
        return _normalize_manifest(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        if strict:
            raise PublicationError(f"invalid CBB release manifest: {path}") from exc
        return _empty_manifest()


def _write_manifest(payload: dict, root: str | Path | None = None) -> Path:
    path = cbb_release_root(root) / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = dict(payload)
    body["updated_at"] = utc_now_iso()
    with NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", prefix="cbb-manifest-", suffix=".tmp", dir=path.parent, delete=False) as handle:
        handle.write(json.dumps(body, indent=2, sort_keys=True) + "\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)
    return path


def _read_metadata(value: str | Path | dict) -> dict:
    if isinstance(value, dict):
        return dict(value)
    return json.loads(Path(value).read_text(encoding="utf-8"))


def _read_card(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"game_id": "string", "home_team_id": "string", "away_team_id": "string"})


def _timestamp(value: object, field: str) -> datetime:
    try:
        return parse_aware_datetime(value)
    except (TypeError, ValueError) as exc:
        raise PublicationError(f"{field} must be timezone-aware UTC") from exc


def _validate_timestamp_column(frame: pd.DataFrame, field: str) -> list[datetime]:
    """Parse a timestamp column eagerly so errors are reported as contract errors."""
    parsed: list[datetime] = []
    for value in frame[field].tolist():
        parsed.append(_timestamp(value, field))
    return parsed


def _date(value: object) -> str:
    try:
        return datetime.fromisoformat(str(value)).date().isoformat()
    except ValueError as exc:
        raise PublicationError("game_date_et must be YYYY-MM-DD") from exc


def validate_card_candidate(artifact: str | Path, metadata: str | Path | dict) -> dict:
    path = Path(artifact)
    meta = _read_metadata(metadata)
    required_meta = {"schema_version", "product", "season", "game_date_et", "status", "artifact_sha256", "expected_rows", "model_hash", "feature_hash", "historical_benchmark_hash", "policy_hash", "threshold", "prediction_run_hash"}
    missing = sorted(required_meta - set(meta))
    if missing:
        raise PublicationError("CBB card metadata missing: " + ", ".join(missing))
    if meta["schema_version"] != "cbb_daily_card_v1" or meta["product"] != "cbb_daily_spreads":
        raise PublicationError("unsupported CBB daily card metadata contract")
    if int(meta["season"]) != SEASON or _date(meta["game_date_et"]) != str(meta["game_date_et"]):
        raise PublicationError("CBB daily card is not bound to season 2027 and a valid ET date")
    if meta["model_hash"] != MODEL_HASH or meta["feature_hash"] != FEATURE_HASH or meta["historical_benchmark_hash"] != BENCHMARK_HASH or meta["policy_hash"] != POLICY_HASH:
        raise PublicationError("CBB daily card has an unknown frozen hash")
    if float(meta["threshold"]) != THRESHOLD:
        raise PublicationError("CBB daily card threshold must be 8.5")
    digest = sha256_file(path)
    if digest != str(meta["artifact_sha256"]):
        raise PublicationError("CBB daily card artifact hash does not match metadata")
    frame = _read_card(path)
    if int(meta["expected_rows"]) != len(frame):
        raise PublicationError("CBB daily card row count does not match metadata")
    if "expected_game_ids" in meta:
        expected_ids = sorted(str(value) for value in (meta.get("expected_game_ids") or []))
        observed_ids = sorted(str(value) for value in frame["game_id"].dropna().tolist()) if "game_id" in frame else []
        if expected_ids != observed_ids:
            raise PublicationError("CBB daily card game coverage does not match metadata")
    missing_columns = sorted(set(CARD_COLUMNS) - set(frame.columns))
    forbidden = sorted(set(frame.columns).intersection(FORBIDDEN_CARD_COLUMNS))
    if missing_columns:
        raise PublicationError("CBB daily card missing columns: " + ", ".join(missing_columns))
    if forbidden:
        raise PublicationError("CBB daily card contains private/raw columns: " + ", ".join(forbidden))
    if frame["game_id"].isna().any() or frame["game_id"].astype(str).str.strip().eq("").any() or frame["game_id"].duplicated().any():
        raise PublicationError("CBB daily card game IDs must be unique and nonempty")
    if frame["home_team_id"].isna().any() or frame["away_team_id"].isna().any() or frame["home_team"].astype(str).str.strip().eq("").any() or frame["away_team"].astype(str).str.strip().eq("").any():
        raise PublicationError("CBB daily card team identities and names are required")
    if len(frame) == 0:
        if meta["status"] != "no_games_scheduled":
            raise PublicationError("empty CBB daily card must be marked no_games_scheduled")
        return {"metadata": meta, "frame": frame, "artifact_sha256": digest}
    if meta["status"] != "published":
        raise PublicationError("nonempty CBB daily card must be marked published")
    tip = pd.to_datetime(frame["tipoff_utc"], utc=True, errors="coerce")
    if tip.isna().any() or not tip.dt.tz_convert(ET).dt.date.astype(str).eq(str(meta["game_date_et"])).all():
        raise PublicationError("CBB tipoff timestamps must be valid and match game_date_et")
    numeric = ["predicted_home_score", "predicted_away_score", "predicted_margin", "predicted_total", "home_win_probability"]
    values = frame[numeric].apply(pd.to_numeric, errors="coerce")
    if values.isna().any().any() or not np.isfinite(values.to_numpy(dtype=float)).all():
        raise PublicationError("CBB predictions must be finite")
    if (values[["predicted_home_score", "predicted_away_score"]] < 0).any().any() or not values["home_win_probability"].between(0, 1).all():
        raise PublicationError("CBB score predictions or probabilities are invalid")
    if not np.allclose(values["predicted_home_score"] - values["predicted_away_score"], values["predicted_margin"], atol=1e-6) or not np.allclose(values["predicted_home_score"] + values["predicted_away_score"], values["predicted_total"], atol=1e-6):
        raise PublicationError("CBB score, margin, and total are incoherent")
    _validate_timestamp_column(frame, "prediction_at_utc")
    available = frame["market_status"].astype(str).eq("available")
    missing_line = frame["market_status"].astype(str).eq("missing_line")
    if not (available | missing_line).all():
        raise PublicationError("unknown CBB market_status")
    if len(frame) and not available.any():
        raise PublicationError("a nonempty CBB spread card requires at least one valid official line")
    if available.any():
        spread = pd.to_numeric(frame.loc[available, "market_home_spread"], errors="coerce")
        margin = pd.to_numeric(frame.loc[available, "market_home_margin"], errors="coerce")
        edge = pd.to_numeric(frame.loc[available, "model_edge"], errors="coerce")
        if spread.isna().any() or margin.isna().any() or edge.isna().any() or not np.isfinite(spread).all() or not np.isfinite(margin).all() or not np.isfinite(edge).all():
            raise PublicationError("available CBB lines must be finite")
        if not np.allclose(margin, -spread, atol=1e-6) or not np.allclose(edge, values.loc[available, "predicted_margin"] - margin, atol=1e-6):
            raise PublicationError("CBB market sign or edge is incoherent")
        expected = np.where(edge >= THRESHOLD, "home", np.where(edge <= -THRESHOLD, "away", "no_play_below_threshold"))
        if not np.array_equal(frame.loc[available, "ats_pick"].astype(str).to_numpy(), expected):
            raise PublicationError("CBB ATS picks do not match the locked 8.5-point threshold")
        line_times = _validate_timestamp_column(frame.loc[available], "line_retrieved_at_utc")
        for retrieved, tipoff in zip(line_times, tip.loc[available]):
            local = retrieved.astimezone(ET)
            local_time = local.time().replace(tzinfo=None)
            if local.date().isoformat() != str(meta["game_date_et"]) or not (datetime.min.time().replace(hour=8, minute=45) <= local_time <= datetime.min.time().replace(hour=9, minute=0)) or retrieved >= tipoff.to_pydatetime():
                raise PublicationError("CBB line capture must be official 08:45–09:00 ET and pre-tip")
    if missing_line.any() and frame.loc[missing_line, "ats_status"].astype(str).eq("line_unavailable").eq(False).any():
        raise PublicationError("missing-line rows must be marked line_unavailable")
    return {"metadata": meta, "frame": frame, "artifact_sha256": digest}


def _build_id(meta: Mapping[str, object]) -> str:
    return f"cbb-card-{meta['game_date_et']}-{str(meta['artifact_sha256'])[:12]}"


def publish_card_candidate(artifact: str | Path, metadata: str | Path | dict, *, root: str | Path | None = None, activate: bool = True) -> dict:
    checked = validate_card_candidate(artifact, metadata)
    meta, source = checked["metadata"], Path(artifact)
    root_path = _root(root)
    release_root = cbb_release_root(root_path)
    build_id = _build_id(meta)
    build_dir = release_root / "builds" / str(meta["game_date_et"]) / build_id
    build_dir.mkdir(parents=True, exist_ok=True)
    stored_artifact = build_dir / "artifact.csv"
    stored_meta = build_dir / "metadata.json"
    if stored_artifact.exists() and sha256_file(stored_artifact) != checked["artifact_sha256"]:
        raise PublicationError("immutable CBB card build collision")
    if not stored_artifact.exists():
        shutil.copy2(source, stored_artifact)
    normalized = dict(meta)
    normalized["validation"] = {"ok": True, "artifact_sha256": checked["artifact_sha256"], "row_count": len(checked["frame"])}
    if not stored_meta.exists():
        stored_meta.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    elif _read_metadata(stored_meta).get("artifact_sha256") != normalized["artifact_sha256"]:
        raise PublicationError("immutable CBB card metadata collision")
    manifest = load_cbb_manifest(root_path)
    day = str(meta["game_date_et"])
    state = manifest["dates"].setdefault(day, {"active_build": None, "previous_build": None, "status": None, "builds": {}})
    entry = {
        "build_id": build_id, "date": day, "status": meta["status"],
        "artifact": str(stored_artifact.relative_to(root_path)).replace("\\", "/"),
        "metadata": str(stored_meta.relative_to(root_path)).replace("\\", "/"),
        "sha256": checked["artifact_sha256"], "row_count": len(checked["frame"]),
        "published_at": state.get("builds", {}).get(build_id, {}).get("published_at") or utc_now_iso(),
    }
    state.setdefault("builds", {})[build_id] = entry
    if activate:
        prior = state.get("active_build")
        if prior != build_id:
            state["previous_build"] = prior
            state["active_build"] = build_id
    state["status"] = meta["status"]
    manifest["latest_date"] = max([str(value) for value in manifest["dates"]], default=None)
    _write_manifest(manifest, root_path)
    return entry


def _active_card_entry(manifest: dict, day: str) -> dict:
    state = manifest.get("dates", {}).get(day)
    if not isinstance(state, dict) or not state.get("active_build"):
        raise FileNotFoundError(f"no CBB daily card is published for {day}")
    entry = state.get("builds", {}).get(state["active_build"])
    if not isinstance(entry, dict):
        raise PublicationError(f"active CBB card build is missing for {day}")
    return entry


def publish_result_candidate(artifact: str | Path, metadata: str | Path | dict, *, root: str | Path | None = None) -> dict:
    meta = _read_metadata(metadata)
    required = {"schema_version", "product", "game_date_et", "source_card_build_id", "source_card_sha256", "artifact_sha256", "expected_rows", "model_hash", "feature_hash", "policy_hash"}
    missing = sorted(required - set(meta))
    if missing:
        raise PublicationError("CBB result metadata missing: " + ", ".join(missing))
    if meta["schema_version"] != "cbb_daily_results_v1" or meta["product"] != "cbb_daily_spreads_results":
        raise PublicationError("unsupported CBB result contract")
    if meta["model_hash"] != MODEL_HASH or meta["feature_hash"] != FEATURE_HASH or meta["policy_hash"] != POLICY_HASH:
        raise PublicationError("CBB result hash binding is invalid")
    result = pd.read_csv(artifact, dtype={"game_id": "string"})
    if sorted(set(RESULT_COLUMNS) - set(result.columns)):
        raise PublicationError("CBB result artifact has missing columns")
    if len(result) != int(meta["expected_rows"]) or sha256_file(artifact) != meta["artifact_sha256"]:
        raise PublicationError("CBB result artifact hash or row count is invalid")
    root_path = _root(root)
    manifest = load_cbb_manifest(root_path, strict=True)
    entry = _active_card_entry(manifest, str(meta["game_date_et"]))
    if entry["build_id"] != str(meta["source_card_build_id"]):
        raise PublicationError("CBB result does not bind to the active daily card")
    card_path = root_path / entry["artifact"]
    if sha256_file(card_path) != str(meta["source_card_sha256"]):
        raise PublicationError("CBB result source card hash does not match the active build")
    if result["game_id"].isna().any() or result["game_id"].astype(str).str.strip().eq("").any() or result["game_id"].duplicated().any():
        raise PublicationError("CBB result game IDs must be unique")
    card = pd.read_csv(card_path, dtype={"game_id": "string"})
    if set(result["game_id"].astype(str)) - set(card["game_id"].astype(str)):
        raise PublicationError("CBB result contains a game not present on the source card")
    allowed_results = {"win", "loss", "push", "no_play", "ungraded"}
    if result["ats_result"].astype(str).isin(allowed_results).eq(False).any():
        raise PublicationError("CBB result contains an invalid ATS result")
    finalized = result["ats_result"].astype(str).isin({"win", "loss", "push", "no_play"})
    for value in result.loc[finalized, "finalized_at_utc"].tolist():
        _timestamp(value, "finalized_at_utc")
    scores = result[["home_score", "away_score"]].apply(pd.to_numeric, errors="coerce")
    margins = result[["actual_home_margin", "actual_cover_margin"]].apply(pd.to_numeric, errors="coerce")
    if scores.loc[finalized].isna().any().any() or margins.loc[finalized, "actual_home_margin"].isna().any() or (scores.loc[finalized] < 0).any().any():
        raise PublicationError("finalized CBB result scores and margins must be finite and nonnegative scores")
    if not np.allclose(scores.loc[finalized, "home_score"] - scores.loc[finalized, "away_score"], margins.loc[finalized, "actual_home_margin"], atol=1e-6):
        raise PublicationError("CBB result actual margin is incoherent")
    build_id = f"cbb-results-{meta['game_date_et']}-{str(meta['artifact_sha256'])[:12]}"
    build_dir = cbb_release_root(root_path) / "results" / str(meta["game_date_et"]) / build_id
    build_dir.mkdir(parents=True, exist_ok=True)
    stored_artifact = build_dir / "graded.csv"
    stored_meta = build_dir / "metadata.json"
    if stored_artifact.exists() and sha256_file(stored_artifact) != meta["artifact_sha256"]:
        raise PublicationError("immutable CBB result build collision")
    if not stored_artifact.exists():
        shutil.copy2(artifact, stored_artifact)
    normalized = dict(meta)
    normalized["validation"] = {"ok": True, "row_count": len(result), "artifact_sha256": meta["artifact_sha256"]}
    if not stored_meta.exists():
        stored_meta.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    state = manifest["dates"][str(meta["game_date_et"])]
    state["results"] = {"build_id": build_id, "artifact": str(stored_artifact.relative_to(root_path)).replace("\\", "/"), "metadata": str(stored_meta.relative_to(root_path)).replace("\\", "/"), "sha256": meta["artifact_sha256"], "published_at": utc_now_iso()}
    _write_manifest(manifest, root_path)
    return state["results"]


def load_cbb_card(day: str, *, root: str | Path | None = None) -> tuple[pd.DataFrame, dict, dict]:
    root_path = _root(root)
    manifest = load_cbb_manifest(root_path, strict=True)
    entry = _active_card_entry(manifest, day)
    artifact = root_path / entry["artifact"]
    if not artifact.is_file() or sha256_file(artifact) != entry.get("sha256"):
        raise PublicationError("active CBB card artifact is missing or hash-invalid")
    return _read_card(artifact), _read_metadata(root_path / entry["metadata"]), entry


def load_cbb_results(day: str, *, root: str | Path | None = None) -> pd.DataFrame | None:
    root_path = _root(root)
    manifest = load_cbb_manifest(root_path, strict=True)
    state = manifest.get("dates", {}).get(day, {})
    result = state.get("results") if isinstance(state, dict) else None
    if not isinstance(result, dict):
        return None
    artifact = root_path / result["artifact"]
    if not artifact.is_file() or sha256_file(artifact) != result.get("sha256"):
        raise PublicationError("CBB result artifact is missing or hash-invalid")
    return pd.read_csv(artifact, dtype={"game_id": "string"})


def cbb_status(*, root: str | Path | None = None) -> dict:
    manifest = load_cbb_manifest(root)
    return {"latest_date": manifest.get("latest_date"), "dates": sorted(manifest.get("dates", {})), "policy": manifest.get("policy")}


__all__ = [
    "CARD_COLUMNS", "RESULT_COLUMNS", "cbb_release_root", "load_cbb_manifest", "load_cbb_card", "load_cbb_results", "cbb_status",
    "validate_card_candidate", "publish_card_candidate", "publish_result_candidate",
]
