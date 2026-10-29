"""Fail-closed validation for prediction and fantasy release candidates."""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .contract import (
    PRODUCTS,
    PublicationError,
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
    "tuesday_median_spread_line", "consensus_tier",
}
PREDICTION_HIGH_GAP = 3.0
BLEND_VERDICTS = {"blend_high", "blend_no_high", "blend_split_no_high"}
BLEND_SIDE_PROBABILITY = 0.25
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


def _validate_qb_blends(report: ValidationReport, frame: pd.DataFrame) -> None:
    """Verify blend evidence independently of the private candidate producer."""
    if not {"qb_scenarios", "qb_scenario_verdict"} & set(frame):
        return

    def finite_number(value: object) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        try:
            number = float(value)
        except (OverflowError, ValueError):
            return None
        return number if math.isfinite(number) else None

    for row in frame.to_dict(orient="records"):
        prefix = f"QB blend {row['game_id']}: "
        raw_verdict = row.get("qb_scenario_verdict")
        verdict = "" if pd.isna(raw_verdict) else str(raw_verdict).strip()
        is_blend = verdict.startswith("blend_")
        raw = row.get("qb_scenarios")
        try:
            scenarios = json.loads(raw) if isinstance(raw, str) and raw.strip() else None
        except (ValueError, TypeError):
            scenarios = None
        probability_payload = isinstance(scenarios, list) and any(
            isinstance(item, dict) and "probability" in item for item in scenarios
        )
        if is_blend and verdict not in BLEND_VERDICTS:
            report.errors.append(prefix + f"unsupported qb_scenario_verdict {verdict!r}")
            continue
        if not is_blend:
            if probability_payload:
                report.errors.append(prefix + "probability-bearing qb_scenarios require a supported blend verdict")
            continue
        if not isinstance(scenarios, list) or len(scenarios) < 2 or any(
            not isinstance(item, dict) for item in scenarios
        ):
            report.errors.append(prefix + "qb_scenarios must be a JSON list of at least two candidate objects")
            continue

        candidates = []
        seen_ids = set()
        teams = set()
        invalid = False
        for index, item in enumerate(scenarios, start=1):
            player = item.get("player_id")
            team = item.get("team")
            probability = finite_number(item.get("probability"))
            candidate_edge = finite_number(item.get("edge"))
            problem = None
            if not isinstance(player, str) or not player.strip() or player.strip().lower() in {"nan", "none", "null"}:
                problem = "player_id must be a nonempty string"
            elif player.strip() in seen_ids:
                problem = f"duplicate candidate player_id {player!r}"
            elif not isinstance(team, str) or team not in {row["home_team"], row["away_team"]}:
                problem = "candidate team must match home_team or away_team"
            elif probability is None or not 0 <= probability <= 1:
                problem = "probability must be a finite number in [0, 1]"
            elif candidate_edge is None:
                problem = "edge must be a finite number"
            if problem:
                report.errors.append(prefix + f"candidate {index}: {problem}")
                invalid = True
                continue
            seen_ids.add(player.strip())
            teams.add(team)
            candidates.append((probability, candidate_edge))
        if invalid:
            continue
        if len(teams) != 1:
            report.errors.append(prefix + "all candidates must belong to one team; joint blends are unsupported")
            continue
        if abs(sum(p for p, _ in candidates) - 1.0) > 1e-6:
            report.errors.append(prefix + "candidate probabilities must sum to 1 (tolerance 1e-6)")
            continue
        try:
            # Use the producer's ordered sum so the strict 3.0 threshold agrees
            # even when a three-QB blend lands one floating-point step below it.
            blended = sum(p * candidate_edge for p, candidate_edge in candidates)
        except OverflowError:
            blended = math.inf
        if not math.isfinite(blended):
            report.errors.append(prefix + "probability-weighted edge must be finite")
            continue
        for column in ("model_edge", "ens_model_edge"):
            if column not in row or (column == "ens_model_edge" and pd.isna(row[column])):
                continue
            official = pd.to_numeric(row[column], errors="coerce")
            if not math.isfinite(official) or abs(official - blended) > 1e-5:
                report.errors.append(prefix + f"{column} must equal probability-weighted edge {blended:.6g}")
        signs = {int(np.sign(candidate_edge)) for p, candidate_edge in candidates if p >= BLEND_SIDE_PROBABILITY}
        if len(signs) > 1:
            expected = "blend_split_no_high"
        elif signs and next(iter(signs)) != 0 and next(iter(signs)) == int(np.sign(blended)) and abs(blended) >= PREDICTION_HIGH_GAP:
            expected = "blend_high"
        else:
            expected = "blend_no_high"
        if verdict != expected:
            report.errors.append(prefix + f"qb_scenario_verdict {verdict!r} disagrees with candidates; expected {expected!r}")


def _validate_predictions(
    report: ValidationReport,
    frame: pd.DataFrame,
    metadata: dict,
    schedule: pd.DataFrame | None,
    *,
    allow_post_kickoff_correction: bool = False,
) -> None:
    missing = sorted(PREDICTION_REQUIRED - set(frame.columns))
    if missing:
        report.errors.append(f"predictions missing columns: {', '.join(missing)}")
        return
    _validate_qb_blends(report, frame)
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
    if live_release and "tuesday_median_spread_line" in frame:
        model_line = pd.to_numeric(frame["tuesday_median_spread_line"], errors="coerce")
    elif "spread_line" in frame:
        model_line = pd.to_numeric(frame["spread_line"], errors="coerce")
    elif "tuesday_spread_line" in frame:
        model_line = pd.to_numeric(frame["tuesday_spread_line"], errors="coerce")
    else:
        report.errors.append("predictions need a Tuesday model line")
        model_line = pd.Series(np.nan, index=frame.index)
    if model_line.isna().any() or not np.isfinite(model_line).all():
        report.errors.append("the Tuesday model line must be finite for every game")
    mismatch = (edge - (pred - model_line)).abs()
    if mismatch.notna().any() and float(mismatch.max()) > 1e-5:
        report.errors.append(
            "model edge must be prediction minus the Tuesday US median; "
            f"max absolute mismatch {float(mismatch.max()):.6g}"
        )
    if live_release and PREDICTION_EXECUTION_REQUIRED <= set(frame.columns):
        execution_line = pd.to_numeric(frame["tuesday_spread_line"], errors="coerce")
        if execution_line.isna().any() or not np.isfinite(execution_line).all():
            report.errors.append("tuesday_spread_line must be finite for every game")
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
            if "spread_line" in frame:
                public_model_line = pd.to_numeric(frame["spread_line"], errors="coerce")
                spread_mismatch = (public_model_line - median_line).abs()
                if spread_mismatch.notna().any() and float(spread_mismatch.max()) > 1e-5:
                    report.errors.append(
                        "spread_line must equal the Tuesday US median for live predictions"
                    )
            worse_home = edge.gt(0) & execution_line.gt(median_line + 1e-9)
            worse_away = edge.lt(0) & execution_line.lt(median_line - 1e-9)
            if (worse_home | worse_away).any():
                bad = frame.loc[worse_home | worse_away, "game_id"].astype(str).tolist()
                report.errors.append(
                    "shopped line is worse than the US median for the recommended side: "
                    + ", ".join(bad[:8])
                )
            tiers = frame["consensus_tier"].fillna("").astype(str).str.strip().str.upper()
            invalid_tiers = sorted(set(tiers) - {"", "HIGH"})
            if invalid_tiers:
                report.errors.append(
                    f"live prediction tiers must be HIGH or empty, got {invalid_tiers}"
                )
            expected_high = edge.abs().ge(PREDICTION_HIGH_GAP)
            if int(metadata.get("week", 0)) == 18:
                game_type = frame.get(
                    "game_type", pd.Series("REG", index=frame.index)
                ).fillna("REG").astype(str)
                expected_high = expected_high & ~game_type.eq("REG")
            if "qb_scenario_verdict" in frame:
                verdict = frame["qb_scenario_verdict"].fillna("").astype(str).str.strip()
                is_blend = verdict.str.startswith("blend_")
                expected_high = expected_high.where(
                    ~is_blend, verdict.eq("blend_high") & expected_high
                )
            tier_mismatch = tiers.eq("HIGH").ne(expected_high)
            if tier_mismatch.any():
                bad = frame.loc[tier_mismatch, "game_id"].astype(str).tolist()
                report.errors.append(
                    "HIGH tier must use the 3.0-point Tuesday-median edge: "
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
            if allow_post_kickoff_correction:
                report.warnings.append(
                    "correction was produced after the first kickoff; correction controls verified"
                )
                report.checks["post_kickoff_correction"] = True
            else:
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
    exceptions = metadata.get("team_position_gap_exceptions") or []
    exception_keys = set()
    invalid_exceptions = []
    review = metadata.get("release_review") or {}
    reviewed_projection_sha = str(review.get("sleeper_projection_sha256") or "")
    for item in exceptions:
        if not isinstance(item, dict):
            invalid_exceptions.append(item)
            continue
        team = str(item.get("team") or "")
        position = str(item.get("position") or "")
        evidence_sha = str(item.get("source_sha256") or "")
        reason = str(item.get("reason") or "").strip()
        key = (team, position)
        if (
            team not in scheduled_teams
            or position not in POSITION_MINIMUMS
            or not reason
            or len(evidence_sha) != 64
            or evidence_sha != reviewed_projection_sha
            or key in exception_keys
        ):
            invalid_exceptions.append(item)
            continue
        exception_keys.add(key)
    stale_exceptions = sorted(exception_keys - set(missing_team_positions))
    if invalid_exceptions or stale_exceptions:
        report.errors.append(
            "team-position gap exceptions are invalid or no longer match the candidate"
        )
    unexplained_gaps = sorted(set(missing_team_positions) - exception_keys)
    if unexplained_gaps:
        report.errors.append(
            f"scheduled teams lack projected skill-position players: {unexplained_gaps[:8]}"
        )
    if exception_keys and not invalid_exceptions and not stale_exceptions:
        report.warnings.append(
            "documented team-position coverage gaps: "
            + ", ".join(f"{team} {position}" for team, position in sorted(exception_keys))
        )
    report.checks["team_position_gap_exceptions"] = int(len(exception_keys))
    report.checks["scheduled_teams"] = int(len(scheduled_teams))
    report.checks["team_position_cells"] = int(
        sum(int(count > 0) for values in actual_team_positions.values() for count in values.values())
    )
    if not metadata.get('legacy_bootstrap'):
        first = _first_kickoff(sched)
        try:
            produced = parse_aware_datetime(metadata['produced_at'])
            if first is not None and produced >= first and not metadata.get('rolling_refresh'):
                report.errors.append('post-kickoff fantasy refresh requires verified rolling baseline')
        except (KeyError, TypeError, ValueError):
            pass  # The metadata checks report invalid production timestamps.


def validate_candidate(
    artifact: str | Path,
    metadata: str | Path | dict,
    *,
    schedule: str | Path | pd.DataFrame | None = None,
    allow_post_kickoff_correction: bool = False,
    root=None,
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
        _validate_predictions(
            report,
            frame,
            meta,
            schedule_frame,
            allow_post_kickoff_correction=allow_post_kickoff_correction,
        )
    elif report.product == "fantasy":
        _validate_fantasy(report, frame, meta, schedule_frame)
        if meta.get('rolling_refresh'):
            _validate_rolling_fantasy(report, path, meta, schedule_frame, root)
    elif report.product not in PRODUCTS:
        report.errors.append(f"unknown product {report.product!r}")
    return report


def _validate_rolling_fantasy(report, artifact, metadata, schedule, root):
    """Verify locked rows against an immutable build, never a producer path."""
    from .manifest import load_manifest
    from .paths import resolve_site_path
    if schedule is None:
        report.errors.append('rolling fantasy protection requires a schedule')
        return
    try:
        rolling = metadata['rolling_refresh']
        baseline = load_manifest(root, strict=True)['products']['fantasy']['builds'][rolling['baseline_build_id']]
        if (int(baseline['season']), int(baseline['week'])) != (int(metadata['season']), int(metadata['week'])):
            raise ValueError('rolling baseline season/week mismatch')
        if baseline['model_version'] != metadata['model_version']:
            raise ValueError('rolling refresh must retain the frozen model')
        baseline_path = resolve_site_path(baseline['artifact'], root)
        if sha256_file(baseline_path) != baseline['sha256'] or baseline['sha256'] != rolling['baseline_artifact_sha256']:
            raise ValueError('rolling baseline artifact hash mismatch')
        if sha256_file(resolve_site_path(baseline['metadata'], root)) != rolling['baseline_metadata_sha256']:
            raise ValueError('rolling baseline metadata hash mismatch')
        produced = parse_aware_datetime(metadata['produced_at'])
        as_of = parse_aware_datetime(rolling['as_of_utc'])
        requested = parse_aware_datetime(rolling['source_requested_utc'])
        if requested > as_of or as_of > produced:
            raise ValueError('rolling capture/build timestamp order is invalid')
        slate = _schedule_week(schedule, int(metadata['season']), int(metadata['week']))
        locked = set()
        for game in slate.to_dict(orient='records'):
            if not isinstance(game.get('gametime'), str) or not game['gametime'].strip():
                raise ValueError('rolling refresh requires explicit actual kickoff times')
            kickoff = _first_kickoff(pd.DataFrame([game]))
            if kickoff is None:
                raise ValueError('rolling refresh requires valid kickoff times')
            if kickoff <= produced:
                locked.add(str(game['game_id']))
            elif requested >= kickoff:
                raise ValueError('fresh capture is not before refreshed game kickoff')
        if locked != set(map(str, rolling['locked_game_ids'])):
            raise ValueError('rolling locked games disagree with production time')
        old = pd.read_csv(baseline_path, dtype=str, keep_default_na=False)
        new = pd.read_csv(artifact, dtype=str, keep_default_na=False)
        if set(old.columns) != set(new.columns):
            raise ValueError('rolling published columns changed')
        columns = sorted(old.columns)
        before = old.loc[old.game_id.isin(locked), columns].sort_values(['game_id','player_id']).reset_index(drop=True)
        after = new.loc[new.game_id.isin(locked), columns].sort_values(['game_id','player_id']).reset_index(drop=True)
        if not before.equals(after):
            raise ValueError('started-game published rows changed, disappeared, or were added')
        report.checks['locked_fantasy_rows'] = len(before)
    except (KeyError, TypeError, ValueError, OSError, PublicationError) as exc:
        report.errors.append(f'rolling fantasy protection failed: {exc}')
