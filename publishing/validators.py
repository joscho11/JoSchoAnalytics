"""Fail-closed validation for prediction and fantasy release candidates."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .contract import (
    PRODUCTS,
    SCHEMA_VERSION,
    ValidationReport,
    canonical_values_hash,
    parse_aware_datetime,
    sha256_file,
)

PREDICTION_REQUIRED = {
    "game_id", "home_team", "away_team", "season", "week",
    "predicted_margin", "model_edge", "recommendation", "logged_at",
}
PREDICTION_EXECUTION_REQUIRED = {
    "tuesday_spread_line", "tuesday_spread_book", "tuesday_spread_price",
    "tuesday_median_spread_line",
}
FANTASY_REQUIRED = {
    "player_id", "player_display_name", "position", "team", "opponent_team",
    "season", "week", "projected_pts",
}
POSITION_MINIMUMS = {"QB": 24, "RB": 60, "WR": 72, "TE": 24}


def read_table(path: str | Path) -> pd.DataFrame:
    source = Path(path)
    if source.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(source)
    return pd.read_csv(source, dtype={"game_id": "string", "player_id": "string"})


def read_metadata(value: str | Path | dict) -> dict:
    if isinstance(value, dict):
        return dict(value)
    return json.loads(Path(value).read_text(encoding="utf-8"))


def _metadata_checks(
    report: ValidationReport,
    artifact: Path,
    metadata: dict,
    frame: pd.DataFrame,
) -> None:
    required = {
        "schema_version", "product", "season", "week", "model_version",
        "produced_at", "artifact_sha256", "expected_rows",
    }
    missing = sorted(required - set(metadata))
    if missing:
        report.errors.append(f"metadata missing fields: {', '.join(missing)}")
        return
    if metadata.get("schema_version") != SCHEMA_VERSION:
        report.errors.append(
            f"unsupported schema_version {metadata.get('schema_version')!r}; want {SCHEMA_VERSION}"
        )
    if metadata.get("product") not in PRODUCTS:
        report.errors.append(f"invalid product {metadata.get('product')!r}")
    if not str(metadata.get("model_version") or "").strip():
        report.errors.append("model_version is empty")
    try:
        produced = parse_aware_datetime(metadata.get("produced_at"))
        report.checks["produced_at_utc"] = produced.isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError) as exc:
        report.errors.append(f"invalid produced_at: {exc}")
    digest = sha256_file(artifact)
    report.checks["artifact_sha256"] = digest
    if str(metadata.get("artifact_sha256")) != digest:
        report.errors.append("artifact SHA-256 does not match sidecar")
    try:
        expected_rows = int(metadata.get("expected_rows"))
    except (TypeError, ValueError):
        report.errors.append("expected_rows must be an integer")
    else:
        if expected_rows != len(frame):
            report.errors.append(f"row count {len(frame)} != expected_rows {expected_rows}")


def _constant_int_column(
    report: ValidationReport,
    frame: pd.DataFrame,
    name: str,
    expected: object,
) -> None:
    if name not in frame:
        return
    values = pd.to_numeric(frame[name], errors="coerce")
    if values.isna().any():
        report.errors.append(f"{name} contains nonnumeric or missing values")
        return
    unique = sorted(set(values.astype(int)))
    try:
        wanted = int(expected)
    except (TypeError, ValueError):
        report.errors.append(f"metadata {name} must be an integer")
        return
    if unique != [wanted]:
        report.errors.append(f"artifact {name} values {unique} do not equal metadata {wanted}")


def _schedule_week(schedule: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
    out = schedule.copy()
    if "season" in out:
        out = out[pd.to_numeric(out["season"], errors="coerce").eq(int(season))]
    if "week" in out:
        out = out[pd.to_numeric(out["week"], errors="coerce").eq(int(week))]
    if "game_type" in out and out["game_type"].notna().any():
        out = out[out["game_type"].fillna("REG").astype(str).eq("REG")]
    return out


def _first_kickoff(schedule: pd.DataFrame) -> datetime | None:
    if schedule.empty or "gameday" not in schedule:
        return None
    eastern = ZoneInfo("America/New_York")
    values = []
    for row in schedule.to_dict(orient="records"):
        day = str(row.get("gameday") or "")[:10]
        clock = str(row.get("gametime") or "13:00")[:5]
        try:
            values.append(datetime.fromisoformat(f"{day}T{clock}:00").replace(tzinfo=eastern))
        except ValueError:
            continue
    return min(values) if values else None


def _validate_predictions(
    report: ValidationReport,
    frame: pd.DataFrame,
    metadata: dict,
    schedule: pd.DataFrame | None,
) -> None:
    missing = sorted(PREDICTION_REQUIRED - set(frame.columns))
    if missing:
        report.errors.append(f"predictions missing columns: {', '.join(missing)}")
        return
    if "mode" in frame.columns:
        gameday = frame["mode"].astype("string").str.lower().eq("gameday")
        if gameday.any() and int(metadata.get("season", 0)) >= 2026:
            report.errors.append("gameday spread rows are not a public prediction product")
    live_release = int(metadata.get("season", 0)) >= 2026 and not metadata.get("legacy_bootstrap")
    if live_release:
        missing_execution = sorted(PREDICTION_EXECUTION_REQUIRED - set(frame.columns))
        if missing_execution:
            report.errors.append(
                "live predictions missing shopped-line fields: "
                + ", ".join(missing_execution)
            )
    for col in ("game_id", "home_team", "away_team", "recommendation"):
        if frame[col].isna().any() or frame[col].astype(str).str.strip().eq("").any():
            report.errors.append(f"{col} contains missing or empty values")
    if frame["game_id"].duplicated().any():
        dupes = sorted(frame.loc[frame["game_id"].duplicated(False), "game_id"].astype(str).unique())
        report.errors.append(f"duplicate game_id values: {', '.join(dupes[:8])}")
    for col in ("predicted_margin", "model_edge"):
        numeric = pd.to_numeric(frame[col], errors="coerce")
        if numeric.isna().any() or not np.isfinite(numeric).all():
            report.errors.append(f"{col} must be finite for every game")

    pred = pd.to_numeric(
        frame.get("ens_predicted_margin", frame["predicted_margin"]), errors="coerce"
    )
    if "ens_predicted_margin" in frame:
        pred = pred.where(pred.notna(), pd.to_numeric(frame["predicted_margin"], errors="coerce"))
    edge = pd.to_numeric(frame.get("ens_model_edge", frame["model_edge"]), errors="coerce")
    if "ens_model_edge" in frame:
        edge = edge.where(edge.notna(), pd.to_numeric(frame["model_edge"], errors="coerce"))
    if "tuesday_spread_line" in frame:
        line = pd.to_numeric(frame["tuesday_spread_line"], errors="coerce")
        if "spread_line" in frame:
            line = line.where(line.notna(), pd.to_numeric(frame["spread_line"], errors="coerce"))
    elif "spread_line" in frame:
        line = pd.to_numeric(frame["spread_line"], errors="coerce")
    else:
        report.errors.append("predictions need tuesday_spread_line or spread_line")
        line = pd.Series(np.nan, index=frame.index)
    if line.isna().any() or not np.isfinite(line).all():
        report.errors.append("the frozen spread line must be finite for every game")
    mismatch = (edge - (pred - line)).abs()
    if mismatch.notna().any() and float(mismatch.max()) > 1e-5:
        report.errors.append(f"model edge identity fails; max absolute mismatch {float(mismatch.max()):.6g}")
    if live_release and PREDICTION_EXECUTION_REQUIRED <= set(frame.columns):
        books = frame["tuesday_spread_book"].astype("string")
        if books.isna().any() or books.str.strip().eq("").any():
            report.errors.append("tuesday_spread_book must identify a sportsbook for every game")
        prices = pd.to_numeric(frame["tuesday_spread_price"], errors="coerce")
        if prices.isna().any() or not np.isfinite(prices).all():
            report.errors.append("tuesday_spread_price must be finite for every game")
        median_line = pd.to_numeric(frame["tuesday_median_spread_line"], errors="coerce")
        if median_line.isna().any() or not np.isfinite(median_line).all():
            report.errors.append("tuesday_median_spread_line must be finite for every game")
        else:
            worse_home = edge.gt(0) & line.gt(median_line + 1e-9)
            worse_away = edge.lt(0) & line.lt(median_line - 1e-9)
            if (worse_home | worse_away).any():
                bad = frame.loc[worse_home | worse_away, "game_id"].astype(str).tolist()
                report.errors.append(
                    "shopped line is worse than the US median for the recommended side: "
                    + ", ".join(bad[:8])
                )

    expected_hash = metadata.get("expected_game_ids_sha256")
    actual_hash = canonical_values_hash(frame["game_id"])
    if not expected_hash and not metadata.get("legacy_bootstrap"):
        report.errors.append("expected_game_ids_sha256 is required for live predictions")
    elif expected_hash and str(expected_hash) != actual_hash:
        report.errors.append("prediction game-ID coverage hash does not match sidecar")
    expected_teams = set(map(str, metadata.get("expected_teams") or []))
    actual_teams = set(frame["home_team"].astype(str)) | set(frame["away_team"].astype(str))
    if expected_teams and expected_teams != actual_teams:
        report.errors.append(
            f"prediction team coverage differs from sidecar; missing={sorted(expected_teams-actual_teams)} "
            f"extra={sorted(actual_teams-expected_teams)}"
        )
    if not metadata.get("legacy_bootstrap"):
        try:
            produced = parse_aware_datetime(metadata["produced_at"])
        except (KeyError, TypeError, ValueError):
            produced = None
        bad_logged_at = []
        for value in frame["logged_at"].drop_duplicates():
            try:
                logged = parse_aware_datetime(value)
                if produced is not None and logged > produced:
                    bad_logged_at.append(str(value))
            except (TypeError, ValueError):
                bad_logged_at.append(str(value))
        if bad_logged_at:
            report.errors.append(
                "logged_at must be timezone-aware and no later than produced_at; "
                f"invalid={bad_logged_at[:4]}"
            )

    if schedule is None:
        if not metadata.get("legacy_bootstrap"):
            report.errors.append("a schedule is required for live prediction validation")
        return
    season, week = int(metadata["season"]), int(metadata["week"])
    sched = _schedule_week(schedule, season, week)
    if sched.empty:
        report.errors.append(f"schedule has no rows for {season} Week {week}")
        return
    required_sched = {"game_id", "home_team", "away_team"}
    if not required_sched <= set(sched):
        report.errors.append("schedule is missing game_id/home_team/away_team")
        return
    artifact_ids = set(frame["game_id"].astype(str))
    schedule_ids = set(sched["game_id"].astype(str))
    if artifact_ids != schedule_ids:
        missing_ids = sorted(schedule_ids - artifact_ids)
        extra_ids = sorted(artifact_ids - schedule_ids)
        report.errors.append(
            f"schedule coverage mismatch; missing={missing_ids[:8]} extra={extra_ids[:8]}"
        )
    pairs = {
        str(row.game_id): (str(row.home_team), str(row.away_team))
        for row in frame.itertuples()
    }
    sched_pairs = {
        str(row.game_id): (str(row.home_team), str(row.away_team))
        for row in sched.itertuples()
    }
    if any(pairs[game_id] != sched_pairs[game_id] for game_id in artifact_ids & schedule_ids):
        report.errors.append("candidate home/away teams disagree with the schedule")
    if not metadata.get("legacy_bootstrap"):
        kickoff = _first_kickoff(sched)
        try:
            produced = parse_aware_datetime(metadata["produced_at"])
        except (TypeError, ValueError):
            produced = None
        if kickoff is not None and produced is not None and produced >= kickoff:
            report.errors.append("candidate produced_at is not before the first kickoff")
    report.checks["scheduled_games"] = int(len(sched))


def _validate_fantasy(
    report: ValidationReport,
    frame: pd.DataFrame,
    metadata: dict,
    schedule: pd.DataFrame | None,
) -> None:
    missing = sorted(FANTASY_REQUIRED - set(frame.columns))
    if missing:
        report.errors.append(f"fantasy projections missing columns: {', '.join(missing)}")
        return
    for col in ("player_id", "player_display_name", "position", "team", "opponent_team"):
        if frame[col].isna().any() or frame[col].astype(str).str.strip().eq("").any():
            report.errors.append(f"{col} contains missing or empty values")
    if frame["player_id"].duplicated().any():
        dupes = sorted(frame.loc[frame["player_id"].duplicated(False), "player_id"].astype(str).unique())
        report.errors.append(f"duplicate player_id values: {', '.join(dupes[:8])}")
    for alias in ("gsis_id", "sleeper_id"):
        if alias not in frame:
            continue
        values = frame[alias].astype("string").str.strip()
        nonempty = values[values.notna() & values.ne("")]
        if nonempty.duplicated().any():
            dupes = sorted(nonempty[nonempty.duplicated(False)].astype(str).unique())
            report.errors.append(f"duplicate {alias} values: {', '.join(dupes[:8])}")
        expected_alias_hash = metadata.get(f"expected_{alias}_sha256")
        if expected_alias_hash and str(expected_alias_hash) != canonical_values_hash(nonempty):
            report.errors.append(f"fantasy {alias} coverage hash does not match sidecar")
    positions = set(frame["position"].astype(str))
    invalid_positions = sorted(positions - set(POSITION_MINIMUMS))
    if invalid_positions:
        report.errors.append(f"invalid positions: {', '.join(invalid_positions)}")
    counts = frame["position"].value_counts().to_dict()
    for position, minimum in POSITION_MINIMUMS.items():
        if int(counts.get(position, 0)) < minimum:
            report.errors.append(
                f"{position} coverage {int(counts.get(position, 0))} is below minimum {minimum}"
            )
    points = pd.to_numeric(frame["projected_pts"], errors="coerce")
    if points.isna().any() or not np.isfinite(points).all():
        report.errors.append("projected_pts must be finite for every player")
    elif (points < 0).any():
        report.warnings.append(
            f"{int((points < 0).sum())} projections are below zero; retained as a model diagnostic"
        )

    expected_hash = metadata.get("expected_player_ids_sha256")
    actual_hash = canonical_values_hash(frame["player_id"])
    if not expected_hash and not metadata.get("legacy_bootstrap"):
        report.errors.append("expected_player_ids_sha256 is required for live fantasy projections")
    elif expected_hash and str(expected_hash) != actual_hash:
        report.errors.append("fantasy player-ID coverage hash does not match sidecar")
    expected_counts = metadata.get("position_counts") or {}
    if expected_counts:
        normalized = {str(key): int(value) for key, value in expected_counts.items()}
        actual_counts = {str(key): int(value) for key, value in counts.items()}
        if normalized != actual_counts:
            report.errors.append(
                f"position coverage differs from sidecar; expected={normalized} actual={actual_counts}"
            )
    expected_teams = set(map(str, metadata.get("expected_teams") or []))
    actual_teams = set(frame["team"].astype(str))
    if expected_teams and expected_teams != actual_teams:
        report.errors.append(
            f"fantasy team coverage differs from sidecar; missing={sorted(expected_teams-actual_teams)} "
            f"extra={sorted(actual_teams-expected_teams)}"
        )
    actual_team_positions = {
        str(team): {str(position): int(count) for position, count in position_counts.items()}
        for team, position_counts in frame.groupby("team")["position"].value_counts().unstack(
            fill_value=0
        ).sort_index().to_dict(orient="index").items()
    }
    expected_team_positions = metadata.get("team_position_counts") or {}
    normalized_team_positions = {
        str(team): {str(position): int(count) for position, count in values.items()}
        for team, values in expected_team_positions.items()
    }
    if not normalized_team_positions and not metadata.get("legacy_bootstrap"):
        report.errors.append("team_position_counts is required for live fantasy projections")
    elif normalized_team_positions and normalized_team_positions != actual_team_positions:
        report.errors.append("fantasy team/position coverage differs from sidecar")

    if schedule is None:
        if not metadata.get("legacy_bootstrap"):
            report.errors.append("a schedule is required for live fantasy validation")
        return
    season, week = int(metadata["season"]), int(metadata["week"])
    sched = _schedule_week(schedule, season, week)
    if sched.empty:
        report.errors.append(f"schedule has no rows for {season} Week {week}")
        return
    scheduled_pairs = {
        (str(row.home_team), str(row.away_team)) for row in sched.itertuples()
    }
    scheduled_pairs |= {(away, home) for home, away in list(scheduled_pairs)}
    candidate_pairs = set(zip(frame["team"].astype(str), frame["opponent_team"].astype(str)))
    invalid_pairs = sorted(candidate_pairs - scheduled_pairs)
    if invalid_pairs:
        report.errors.append(f"fantasy team/opponent pairs are not scheduled: {invalid_pairs[:8]}")
    scheduled_teams = {team for pair in scheduled_pairs for team in pair}
    if actual_teams != scheduled_teams:
        report.errors.append(
            f"fantasy schedule team coverage mismatch; missing={sorted(scheduled_teams-actual_teams)} "
            f"extra={sorted(actual_teams-scheduled_teams)}"
        )
    missing_team_positions = sorted(
        (team, position)
        for team in scheduled_teams
        for position in POSITION_MINIMUMS
        if int(actual_team_positions.get(team, {}).get(position, 0)) == 0
    )
    if missing_team_positions:
        report.errors.append(
            f"scheduled teams lack projected skill-position players: {missing_team_positions[:8]}"
        )
    report.checks["scheduled_teams"] = int(len(scheduled_teams))
    report.checks["team_position_cells"] = int(
        sum(int(count > 0) for values in actual_team_positions.values() for count in values.values())
    )


def validate_candidate(
    artifact: str | Path,
    metadata: str | Path | dict,
    *,
    schedule: str | Path | pd.DataFrame | None = None,
) -> ValidationReport:
    path = Path(artifact)
    try:
        meta = read_metadata(metadata)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        report = ValidationReport(product="unknown")
        report.errors.append(f"metadata could not be read: {exc}")
        return report
    report = ValidationReport(product=str(meta.get("product") or "unknown"))
    if not path.is_file():
        report.errors.append(f"artifact does not exist: {path}")
        return report
    try:
        frame = read_table(path)
    except Exception as exc:
        report.errors.append(f"artifact could not be read: {exc}")
        return report
    report.row_count = int(len(frame))
    if frame.empty:
        report.errors.append("artifact has zero rows")
    _metadata_checks(report, path, meta, frame)
    _constant_int_column(report, frame, "season", meta.get("season"))
    _constant_int_column(report, frame, "week", meta.get("week"))

    schedule_frame = None
    if schedule is not None:
        try:
            schedule_frame = schedule.copy() if isinstance(schedule, pd.DataFrame) else read_table(schedule)
        except Exception as exc:
            report.errors.append(f"schedule could not be read: {exc}")
    if report.product == "predictions":
        _validate_predictions(report, frame, meta, schedule_frame)
    elif report.product == "fantasy":
        _validate_fantasy(report, frame, meta, schedule_frame)
    elif report.product not in PRODUCTS:
        report.errors.append(f"unknown product {report.product!r}")
    return report
