"""Idempotent grading that never mutates a published prediction snapshot."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .contract import PublicationError, sha256_file, utc_now_iso
from .manifest import active_release, load_manifest, write_manifest
from .paths import releases_root, relative_to_site, resolve_site_path
from .validators import read_table
from .td_releases import canonical_td_releases, read_td_release


def _active_build_for_week(product: str, season: int, week: int, *, root=None) -> dict:
    manifest = load_manifest(root, strict=True)
    state = manifest["products"][product]
    active = state.get("active_build")
    candidates = list(state.get("builds", {}).values())
    matches = [
        build for build in candidates
        if int(build.get("season", -1)) == int(season) and int(build.get("week", -1)) == int(week)
    ]
    if not matches:
        raise PublicationError(f"no published {product} build for {season} Week {week}")
    if active:
        for build in matches:
            if build.get("build_id") == active:
                return dict(build)
    return dict(sorted(matches, key=lambda item: str(item.get("published_at", "")))[-1])


def _schedule_week(schedule: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
    out = schedule.copy()
    if "season" in out:
        out = out[pd.to_numeric(out["season"], errors="coerce").eq(int(season))]
    if "week" in out:
        out = out[pd.to_numeric(out["week"], errors="coerce").eq(int(week))]
    return out


def _write_result(
    product: str,
    build: dict,
    result: pd.DataFrame,
    summary: dict,
    *,
    root=None,
) -> dict:
    season, week = int(build["season"]), int(build["week"])
    build_id = str(build["build_id"])
    dest = releases_root(root) / "results" / product / str(season) / f"week{week:02d}"
    dest.mkdir(parents=True, exist_ok=True)
    artifact = dest / f"{build_id}-graded.csv"
    metadata = dest / f"{build_id}-graded.json"
    encoded = result.to_csv(index=False, lineterminator="\n").encode("utf-8")
    manifest = load_manifest(root, strict=True)
    stored = manifest["products"][product]["builds"][build_id]
    if artifact.is_file() and metadata.is_file() and artifact.read_bytes() == encoded:
        existing = json.loads(metadata.read_text(encoding="utf-8"))
        grading = stored.get("grading") or {}
        if (
            existing.get("source_build") == build_id
            and grading.get("artifact_sha256") == existing.get("artifact_sha256")
        ):
            return existing
    artifact.write_bytes(encoded)
    payload = dict(summary)
    payload.update(
        {
            "schema_version": 1,
            "product": product,
            "season": season,
            "week": week,
            "source_build": build_id,
            "graded_at": utc_now_iso(),
            "artifact_sha256": sha256_file(artifact),
            "artifact": relative_to_site(artifact, root),
        }
    )
    metadata.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    stored["grading"] = {
        **payload,
        "metadata": relative_to_site(metadata, root),
    }
    grading_state = manifest["grading"]["products"].setdefault(product, {})
    grading_state["latest"] = {
        "season": season,
        "week": week,
        "build_id": build_id,
        "final_games": int(payload.get("final_games", 0)),
        "graded_rows": int(payload.get("graded_rows", 0)),
        "graded_at": payload["graded_at"],
    }
    write_manifest(manifest, root)
    return payload


def grade_predictions(
    season: int,
    week: int,
    schedule: str | Path | pd.DataFrame,
    *,
    root=None,
) -> dict:
    build = _active_build_for_week("predictions", season, week, root=root)
    released = read_table(resolve_site_path(build["artifact"], root))
    schedules = schedule.copy() if isinstance(schedule, pd.DataFrame) else read_table(schedule)
    final = _schedule_week(schedules, season, week)
    needed = {"game_id", "home_score", "away_score"}
    missing = sorted(needed - set(final))
    if missing:
        raise PublicationError(f"schedule is missing grading columns: {', '.join(missing)}")
    if final["game_id"].duplicated().any():
        raise PublicationError("schedule contains duplicate game_id values")
    final = final[["game_id", "home_score", "away_score"]].copy()
    final["home_score"] = pd.to_numeric(final["home_score"], errors="coerce")
    final["away_score"] = pd.to_numeric(final["away_score"], errors="coerce")
    final["is_final"] = final["home_score"].notna() & final["away_score"].notna()
    merged = released.drop(columns=[
        col for col in ("home_score", "away_score", "actual_margin", "home_covered",
                        "model_correct", "ens_model_correct") if col in released
    ]).merge(final, on="game_id", how="left", validate="one_to_one")
    merged["actual_margin"] = np.where(
        merged["is_final"], merged["home_score"] - merged["away_score"], np.nan
    )
    if "tuesday_spread_line" in merged:
        line = pd.to_numeric(merged["tuesday_spread_line"], errors="coerce")
        if "spread_line" in merged:
            line = line.where(line.notna(), pd.to_numeric(merged["spread_line"], errors="coerce"))
    else:
        line = pd.to_numeric(merged["spread_line"], errors="coerce")
    cover_margin = merged["actual_margin"] - line
    final_mask = merged["is_final"].fillna(False)
    push = final_mask & np.isclose(cover_margin.fillna(np.inf), 0.0, atol=1e-9)
    merged["home_covered"] = pd.Series(pd.NA, index=merged.index, dtype="boolean")
    merged.loc[final_mask & ~push, "home_covered"] = cover_margin.loc[final_mask & ~push] > 0

    edge = pd.to_numeric(merged.get("ens_model_edge", merged["model_edge"]), errors="coerce")
    if "ens_model_edge" in merged:
        edge = edge.where(edge.notna(), pd.to_numeric(merged["model_edge"], errors="coerce"))
    graded = final_mask & ~push & edge.ne(0) & edge.notna()
    correct = ((edge > 0) & (cover_margin > 0)) | ((edge < 0) & (cover_margin < 0))
    merged["ens_model_correct"] = pd.Series(pd.NA, index=merged.index, dtype="Float64")
    merged.loc[graded, "ens_model_correct"] = correct.loc[graded].astype(float)
    merged["model_correct"] = merged["ens_model_correct"]
    merged = merged.drop(columns=["is_final"])
    summary = {
        "final_games": int(final_mask.sum()),
        "graded_rows": int(graded.sum()),
        "pushes": int(push.sum()),
        "complete": bool(int(final_mask.sum()) == len(released)),
    }
    return _write_result("predictions", build, merged, summary, root=root)


def _half_ppr(actuals: pd.DataFrame) -> pd.Series:
    if "actual_half_ppr" in actuals:
        return pd.to_numeric(actuals["actual_half_ppr"], errors="coerce")
    if "half_ppr" in actuals:
        return pd.to_numeric(actuals["half_ppr"], errors="coerce")
    def number(name):
        return pd.to_numeric(actuals.get(name, 0), errors="coerce").fillna(0)
    required = {
        "passing_yards", "passing_tds", "passing_interceptions", "rushing_yards",
        "rushing_tds", "receptions", "receiving_yards", "receiving_tds",
    }
    if not required <= set(actuals):
        raise PublicationError("actual stats lack half_ppr and the component scoring columns")
    return (
        number("passing_yards") * 0.04
        + number("passing_tds") * 4
        - number("passing_interceptions") * 2
        + number("rushing_yards") * 0.1
        + number("rushing_tds") * 6
        + number("receptions") * 0.5
        + number("receiving_yards") * 0.1
        + number("receiving_tds") * 6
        - number("rushing_fumbles_lost") * 2
        - number("receiving_fumbles_lost") * 2
    )


def grade_fantasy(
    season: int,
    week: int,
    actuals: str | Path | pd.DataFrame,
    *,
    schedule: str | Path | pd.DataFrame | None = None,
    root=None,
) -> dict:
    build = _active_build_for_week("fantasy", season, week, root=root)
    released = read_table(resolve_site_path(build["artifact"], root))
    stats = actuals.copy() if isinstance(actuals, pd.DataFrame) else read_table(actuals)
    if "season" in stats:
        stats = stats[pd.to_numeric(stats["season"], errors="coerce").eq(int(season))]
    if "week" in stats:
        stats = stats[pd.to_numeric(stats["week"], errors="coerce").eq(int(week))]
    if "season_type" in stats:
        stats = stats[stats["season_type"].astype(str).eq("REG")]
    stats = stats.copy()
    if "player_id" not in stats:
        for alias in ("gsis_id", "sleeper_id"):
            if alias in stats:
                stats["player_id"] = stats[alias]
                break
    if "player_id" not in stats:
        raise PublicationError("actual stats are missing player_id/gsis_id/sleeper_id")
    for col in ("player_id", "gsis_id", "sleeper_id"):
        if col in stats:
            stats[col] = stats[col].astype("string").str.strip()
    stats["player_id"] = stats["player_id"].astype("string").str.strip()
    stats = stats[stats["player_id"].notna() & stats["player_id"].str.strip().ne("")].copy()
    released = released.copy()
    for col in ("player_id", "gsis_id", "sleeper_id"):
        if col in released:
            released[col] = released[col].astype("string").str.strip()
    if stats["player_id"].duplicated().any():
        raise PublicationError("actual stats contain duplicate player_id values")
    stats["actual_half_ppr"] = _half_ppr(stats)
    if "team" not in stats and "recent_team" in stats:
        stats["team"] = stats["recent_team"]
    keep = ["player_id", "actual_half_ppr"] + (["team"] if "team" in stats else [])
    actual_by_alias = {}
    for row in stats.to_dict(orient="records"):
        value = {"actual_half_ppr": row["actual_half_ppr"]}
        for col in ("player_id", "gsis_id", "sleeper_id"):
            alias = row.get(col)
            if alias is not None and str(alias).strip():
                key = str(alias).strip()
                if key in actual_by_alias and actual_by_alias[key]["actual_half_ppr"] != value["actual_half_ppr"]:
                    raise PublicationError(f"actual stats aliases collide for {key}")
                actual_by_alias[key] = value
    def lookup(row):
        for col in ("player_id", "gsis_id", "sleeper_id"):
            value = row.get(col)
            if value is not None and str(value).strip() in actual_by_alias:
                return actual_by_alias[str(value).strip()]
        return {"actual_half_ppr": float("nan")}
    actual = pd.DataFrame([lookup(row) for row in released.to_dict(orient="records")], index=released.index)
    merged = pd.concat([released, actual], axis=1)

    complete_feed = False
    final_games = 0
    if schedule is not None:
        sched = schedule.copy() if isinstance(schedule, pd.DataFrame) else read_table(schedule)
        sched = _schedule_week(sched, season, week)
        if {"home_score", "away_score", "home_team", "away_team"} <= set(sched):
            finals = sched["home_score"].notna() & sched["away_score"].notna()
            final_games = int(finals.sum())
            if bool(finals.all()) and "team" in stats:
                scheduled_teams = set(sched["home_team"].astype(str)) | set(sched["away_team"].astype(str))
                stat_teams = set(stats["team"].dropna().astype(str))
                complete_feed = scheduled_teams <= stat_teams
    if complete_feed:
        merged["actual_half_ppr"] = merged["actual_half_ppr"].fillna(0.0)
    merged["projection_error"] = merged["actual_half_ppr"] - pd.to_numeric(
        merged["projected_pts"], errors="coerce"
    )
    merged["absolute_error"] = merged["projection_error"].abs()
    graded_mask = merged["actual_half_ppr"].notna()
    summary = {
        "final_games": int(final_games),
        "graded_rows": int(graded_mask.sum()),
        "missing_actuals": int((~graded_mask).sum()),
        "complete": bool(complete_feed and graded_mask.all()),
        "zero_filled_after_complete_feed": bool(complete_feed),
    }
    return _write_result("fantasy", build, merged, summary, root=root)


def fetch_nfl_schedule(season: int) -> pd.DataFrame:
    import nflreadpy as nfl
    frame = nfl.load_schedules([int(season)])
    return frame.to_pandas() if hasattr(frame, "to_pandas") else frame


def fetch_player_stats(season: int) -> pd.DataFrame:
    import nflreadpy as nfl
    frame = nfl.load_player_stats([int(season)])
    return frame.to_pandas() if hasattr(frame, "to_pandas") else frame


def fetch_snap_counts(season: int) -> pd.DataFrame:
    """Fetch offensive participation used to resolve DNP/void outcomes."""
    import nflreadpy as nfl
    frame = nfl.load_snap_counts([int(season)])
    return frame.to_pandas() if hasattr(frame, "to_pandas") else frame


_ANYTIME_TD_RELEASE_RE = re.compile(
    r"^anytime_td_(?P<season>\d{4})_week(?P<week>\d{1,2})(?:_[^.]*)?\.csv$"
)


def _normal_identifier(value) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip().upper()
    return text or None


def _normal_team(value) -> str | None:
    return _normal_identifier(value)


def _normal_name(value) -> str | None:
    if pd.isna(value):
        return None
    text = re.sub(r"[^a-z0-9]+", "", str(value).strip().casefold())
    return text or None


def load_reviewed_td_settlements(root=None) -> dict[tuple[int, int, str, str, str], dict]:
    """Load immutable, evidence-backed historical TD settlement decisions."""
    site_root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    path = site_root / "betting" / "anytime_td" / "reviewed_settlements_v2.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicationError(f"reviewed TD settlement registry is unreadable: {path}: {exc}") from exc
    if payload.get("schema_version") != 2 or not isinstance(payload.get("settlements"), list):
        raise PublicationError(f"reviewed TD settlement registry has an invalid schema: {path}")
    result = {}
    for row in payload["settlements"]:
        try:
            key = (
                int(row["season"]), int(row["week"]),
                _normal_identifier(row["game_id"]),
                _normal_identifier(row["player_id"]), str(row["market"]).strip().lower(),
            )
            status = str(row["status"]).strip().lower()
            evidence = row["evidence"]
        except (KeyError, TypeError, ValueError) as exc:
            raise PublicationError(f"reviewed TD settlement registry contains an invalid row: {row}") from exc
        if not key[2] or not key[3] or key[4] not in {"anytime", "two_plus", "first"}:
            raise PublicationError(f"reviewed TD settlement registry contains an invalid key: {row}")
        if status != "void" or not isinstance(evidence, dict) or not evidence:
            raise PublicationError(f"reviewed TD settlement must be an evidence-backed void: {row}")
        if key in result:
            raise PublicationError(f"reviewed TD settlement registry contains a duplicate key: {key}")
        result[key] = {"status": status, "evidence": evidence}
    return result


def _prepare_participation(participation: pd.DataFrame | None, season: int, week: int) -> dict:
    """Build player participation lookups used to distinguish loss from void.

    nflverse snap-count feeds use ``offense_snaps``/``offense_pct``.  A stats
    feed without either field is intentionally treated as unable to resolve a
    quoted player who is absent from the box-score rows.
    """
    if participation is None or participation.empty:
        return {"available": False, "snaps_by_alias": {}, "snaps_by_name_team": {}}
    stats = participation.copy()
    if "season" in stats:
        stats = stats[pd.to_numeric(stats["season"], errors="coerce").eq(int(season))]
    if "week" in stats:
        stats = stats[pd.to_numeric(stats["week"], errors="coerce").eq(int(week))]
    if "season_type" in stats:
        stats = stats[stats["season_type"].astype(str).str.upper().eq("REG")]
    snap_columns = [
        column for column in ("offense_snaps", "defense_snaps", "st_snaps")
        if column in stats
    ]
    if not snap_columns:
        snap_column = next(
            (column for column in ("offensive_snaps", "snap_counts", "snaps") if column in stats),
            None,
        )
        if snap_column:
            snap_columns = [snap_column]
    pct_columns = [
        column for column in ("offense_pct", "defense_pct", "st_pct")
        if column in stats
    ]
    if not snap_columns and not pct_columns:
        return {"available": False, "snaps_by_alias": {}, "snaps_by_name_team": {}}
    aliases = [column for column in ("player_id", "gsis_id", "sleeper_id", "pfr_player_id") if column in stats]
    if not aliases:
        return {"available": False, "snaps_by_alias": {}, "snaps_by_name_team": {}}
    for column in aliases:
        stats[column] = stats[column].map(_normal_identifier)
    team_column = "team" if "team" in stats else "recent_team" if "recent_team" in stats else None
    name_column = (
        "player_display_name" if "player_display_name" in stats
        else "player_name" if "player_name" in stats else "player" if "player" in stats else None
    )
    if snap_columns:
        # Touchdown scorer markets require participation on any unit, not only
        # offense. A special-teams-only player has action under the book rule.
        snaps = sum(
            pd.to_numeric(stats[column], errors="coerce").fillna(0.0)
            for column in snap_columns
        )
        snaps = snaps.where(stats[snap_columns].notna().any(axis=1))
    else:
        snaps = sum(
            pd.to_numeric(stats[column], errors="coerce").fillna(0.0)
            for column in pct_columns
        )
        snaps = snaps.where(stats[pct_columns].notna().any(axis=1))
    stats = stats.assign(_participation_value=snaps)
    by_alias: dict[str, float] = {}
    by_name_team: dict[tuple[str, str], float] = {}
    for row in stats.to_dict(orient="records"):
        value = row.get("_participation_value")
        if pd.isna(value):
            continue
        value = float(value)
        for column in aliases:
            key = row.get(column)
            if key is not None:
                by_alias[key] = max(by_alias.get(key, float("-inf")), value)
        if team_column and name_column:
            team = _normal_team(row.get(team_column))
            name = _normal_name(row.get(name_column))
            if team and name:
                key = (team, name)
                by_name_team[key] = max(by_name_team.get(key, float("-inf")), value)
    return {
        "available": bool(by_alias or by_name_team),
        "snaps_by_alias": by_alias,
        "snaps_by_name_team": by_name_team,
    }


def _prepare_anytime_stats(
    actuals: pd.DataFrame,
    season: int,
    week: int,
    participation: pd.DataFrame | None = None,
) -> dict:
    stats = actuals.copy()
    if "season" in stats:
        stats = stats[pd.to_numeric(stats["season"], errors="coerce").eq(int(season))]
    if "week" in stats:
        stats = stats[pd.to_numeric(stats["week"], errors="coerce").eq(int(week))]
    if "season_type" in stats:
        stats = stats[stats["season_type"].astype(str).str.upper().eq("REG")]

    if "player_id" not in stats:
        for alias in ("gsis_id", "sleeper_id"):
            if alias in stats:
                stats["player_id"] = stats[alias]
                break
    if "player_id" not in stats:
        raise PublicationError("actual stats are missing player_id/gsis_id/sleeper_id")
    if not ({"rushing_tds", "receiving_tds", "special_teams_tds"} & set(stats.columns)):
        raise PublicationError("actual stats are missing rushing_tds/receiving_tds")

    aliases = [col for col in ("player_id", "gsis_id", "sleeper_id") if col in stats]
    for col in aliases:
        stats[col] = stats[col].map(_normal_identifier)
    stats = stats[stats["player_id"].notna()].copy()
    # DraftKings defines a touchdown scorer as the player possessing the ball
    # in the end zone. Passing TDs stay excluded; offensive and special-teams
    # return TDs count for player scorer markets.
    td_columns = [
        col for col in ("rushing_tds", "receiving_tds", "special_teams_tds")
        if col in stats
    ]
    touchdowns = sum(
        pd.to_numeric(stats[col], errors="coerce").fillna(0)
        for col in td_columns
    )
    stats["_anytime_tds"] = touchdowns

    td_by_alias: dict[str, float] = {}
    td_by_name_team: dict[tuple[str, str], float] = {}
    team_column = "team" if "team" in stats else "recent_team" if "recent_team" in stats else None
    name_column = (
        "player_display_name"
        if "player_display_name" in stats
        else "player_name"
        if "player_name" in stats
        else None
    )
    for row in stats.to_dict(orient="records"):
        touchdowns = float(row["_anytime_tds"])
        for col in aliases:
            key = row.get(col)
            if key is not None:
                td_by_alias[key] = max(td_by_alias.get(key, 0.0), touchdowns)
        if team_column and name_column:
            team = _normal_team(row.get(team_column))
            name = _normal_name(row.get(name_column))
            if team and name:
                key = (team, name)
                td_by_name_team[key] = max(td_by_name_team.get(key, 0.0), touchdowns)

    teams = set()
    if team_column:
        teams = {
            team for team in stats[team_column].map(_normal_team).dropna().tolist()
        }
    game_ids = set()
    if "game_id" in stats:
        game_ids = {
            game_id for game_id in stats["game_id"].map(_normal_identifier).dropna().tolist()
        }
    participation_info = _prepare_participation(
        participation if participation is not None else actuals, season, week
    )
    return {
        "td_by_alias": td_by_alias,
        "td_by_name_team": td_by_name_team,
        "teams": teams,
        "game_ids": game_ids,
        "has_team": team_column is not None,
        "participation": participation_info,
    }


def grade_anytime_td_file(
    path: str | Path,
    schedule: pd.DataFrame,
    actuals: pd.DataFrame,
    *,
    season: int,
    week: int,
    participation: pd.DataFrame | None = None,
    reviewed_settlements: dict | None = None,
) -> dict:
    """Attach final rushing/receiving TD outcomes to one live board.

    A final game is left pending unless the player feed is complete enough to
    distinguish a zero from a missing stat row. The source CSV is updated in
    place; the publisher's frozen prediction and price columns are untouched.
    """
    source = Path(path)
    if not source.is_file():
        raise PublicationError(f"Anytime TD release is missing: {source}")
    original_board = read_table(source).copy()
    board = original_board.copy()
    required = {"game_id", "player_id", "scored_anytime"}
    missing = sorted(required - set(board.columns))
    if missing:
        raise PublicationError(
            f"Anytime TD release is missing grading columns: {', '.join(missing)}"
        )
    board["_game_id"] = board["game_id"].map(_normal_identifier)
    board["_player_id"] = board["player_id"].map(_normal_identifier)

    sched = _schedule_week(schedule.copy(), season, week)
    needed = {"game_id", "home_team", "away_team", "home_score", "away_score"}
    missing = sorted(needed - set(sched.columns))
    if missing:
        raise PublicationError(
            f"schedule is missing Anytime TD grading columns: {', '.join(missing)}"
        )
    if sched["game_id"].duplicated().any():
        raise PublicationError("schedule contains duplicate game_id values")
    sched = sched.copy()
    sched["_game_id"] = sched["game_id"].map(_normal_identifier)
    sched["home_score"] = pd.to_numeric(sched["home_score"], errors="coerce")
    sched["away_score"] = pd.to_numeric(sched["away_score"], errors="coerce")
    sched["_is_final"] = sched["home_score"].notna() & sched["away_score"].notna()

    stat_info = _prepare_anytime_stats(actuals, season, week, participation)
    reviewed_settlements = reviewed_settlements or {}
    board_game_ids = set(board["_game_id"].dropna().tolist())
    final_schedule = sched[sched["_is_final"]].copy()
    final_game_ids = set(final_schedule["_game_id"].dropna().tolist())
    pending_games = []
    updated_games = []
    updated_rows = 0

    for game_id in sorted(board_game_ids):
        game_rows = board[board["_game_id"].eq(game_id)]
        final_row = final_schedule[final_schedule["_game_id"].eq(game_id)]
        if final_row.empty:
            pending_games.append(game_id)
            continue
        schedule_row = final_row.iloc[0]
        teams = {
            team for team in (
                _normal_team(schedule_row["home_team"]),
                _normal_team(schedule_row["away_team"]),
            ) if team is not None
        }
        player_ids = set(game_rows["_player_id"].dropna().tolist())
        if not player_ids or game_rows["_player_id"].isna().any():
            pending_games.append(game_id)
            continue

        complete_feed = bool(teams and teams <= stat_info["teams"])
        if not complete_feed and player_ids <= set(stat_info["td_by_alias"]):
            complete_feed = True
        if not complete_feed:
            pending_games.append(game_id)
            continue

        participation_info = stat_info["participation"]

        def player_outcome(row):
            player_id = row["_player_id"]
            touchdowns = stat_info["td_by_alias"].get(row["_player_id"])
            matched_stats = touchdowns is not None
            if touchdowns is None and "player_display_name" in row and "team" in row:
                key = (_normal_team(row["team"]), _normal_name(row["player_display_name"]))
                touchdowns = stat_info["td_by_name_team"].get(key)
                matched_stats = touchdowns is not None
            if matched_stats:
                touchdowns = float(touchdowns or 0.0)
            snaps = None
            if stat_info["participation"]["available"]:
                snaps = stat_info["participation"]["snaps_by_alias"].get(player_id)
                if snaps is None and "player_display_name" in row and "team" in row:
                    key = (_normal_team(row["team"]), _normal_name(row["player_display_name"]))
                    snaps = stat_info["participation"]["snaps_by_name_team"].get(key)
            reviewed_void = all(
                (int(season), int(week), row["_game_id"], player_id, market) in reviewed_settlements
                for market in ("anytime", "two_plus")
            )
            if reviewed_void:
                if (matched_stats and touchdowns > 0) or (snaps is not None and float(snaps) > 0):
                    raise PublicationError(
                        f"reviewed TD void conflicts with scoring/participation evidence: "
                        f"{row['_game_id']}/{player_id}"
                    )
                return ("void", float("nan"))
            if matched_stats:
                return ("loss" if touchdowns <= 0 else "win", touchdowns)
            if snaps is not None:
                return ("loss", 0.0) if float(snaps) > 0 else ("void", float("nan"))
            return ("pending", float("nan"))

        outcomes = game_rows.apply(player_outcome, axis=1)
        states = outcomes.map(lambda value: value[0])
        touchdown_values = outcomes.map(lambda value: value[1])
        pending_mask = states.eq("pending")
        if pending_mask.all():
            pending_games.append(game_id)
            continue
        if pending_mask.any():
            # A quoted player with no stat row and no snap row cannot be told
            # apart from a not-yet-ingested zero, so that row stays blank. It
            # must not hold back the rest of the game: every other row grades
            # now, together with First TD, instead of waiting on one long shot.
            pending_games.append(game_id)
        if "status" not in board:
            board["status"] = "pregame"
        win_mask = states.eq("win")
        loss_mask = states.eq("loss")
        void_mask = states.eq("void")
        pending_rows = states.eq("pending")
        for market in ("anytime", "two_plus"):
            status_col = f"settlement_status_{market}"
            if status_col not in board:
                board[status_col] = "open"
            board.loc[game_rows.index[win_mask | loss_mask], status_col] = "settled"
            board.loc[game_rows.index[void_mask], status_col] = "void"
            board.loc[game_rows.index[pending_rows], status_col] = "awaiting_evidence"
        played_mask = win_mask | loss_mask
        board.loc[game_rows.index[win_mask], "scored_anytime"] = 1
        board.loc[game_rows.index[loss_mask], "scored_anytime"] = 0
        board.loc[game_rows.index[void_mask], "scored_anytime"] = pd.NA
        if "scored_two_plus" not in board:
            board["scored_two_plus"] = pd.Series(
                pd.NA, index=board.index, dtype="Float64"
            )
        board.loc[game_rows.index[played_mask], "scored_two_plus"] = (
            pd.to_numeric(touchdown_values[played_mask], errors="coerce").ge(2).astype(int).to_numpy()
        )
        board.loc[game_rows.index[void_mask], "scored_two_plus"] = pd.NA
        board.loc[game_rows.index[played_mask], "status"] = "final"
        board.loc[game_rows.index[void_mask], "status"] = "void"
        updated_games.append(game_id)
        updated_rows += int((~pending_mask).sum())

    board = board.drop(columns=["_game_id", "_player_id"])
    encoded = board.to_csv(index=False, lineterminator="\n").encode("utf-8")
    changed = encoded != source.read_bytes()
    if changed:
        source.write_bytes(encoded)

    graded = pd.to_numeric(board["scored_anytime"], errors="coerce").notna()
    graded_two_plus = (
        pd.to_numeric(board["scored_two_plus"], errors="coerce").notna()
        if "scored_two_plus" in board
        else pd.Series(False, index=board.index)
    )
    board_games_final = board_game_ids <= final_game_ids
    void_rows = int(board.get("status", pd.Series("", index=board.index)).astype(str).str.lower().eq("void").sum())
    resolved = graded | board.get("status", pd.Series("", index=board.index)).astype(str).str.lower().eq("void")
    return {
        "status": "graded" if updated_games else "pending",
        "file": str(source),
        "season": int(season),
        "week": int(week),
        "final_games": int(len(board_game_ids & final_game_ids)),
        "graded_rows": int(graded.sum()),
        "void_rows": void_rows,
        "pending_rows": int((~resolved).sum()),
        "awaiting_stat_rows": int(
            (board["game_id"].map(_normal_identifier).isin(final_game_ids) & ~resolved).sum()
        ),
        "graded_two_plus_rows": int(graded_two_plus.sum()),
        "updated_games": updated_games,
        "updated_rows": int(updated_rows),
        "pending_games": pending_games,
        "complete": bool(board_games_final and not pending_games and resolved.all()),
        "changed": changed,
    }


def fetch_nfl_pbp(season: int) -> pd.DataFrame:
    import nflreadpy as nfl
    frame = nfl.load_pbp([int(season)])
    return frame.to_pandas() if hasattr(frame, "to_pandas") else frame


_SKILL_POSITIONS = {"QB", "RB", "WR", "TE", "FB"}


def _first_td_position_lookup(actuals: pd.DataFrame) -> dict:
    """player_id -> position, from the same-week player-stats feed.

    Mirrors first_td/src/labels.py's _position_lookup, which reads the
    parent lambda model's training panel; the live grading path has no
    panel parquet to read, so it builds the same lookup from the weekly
    stats feed already fetched for anytime-TD grading instead.
    """
    stats = actuals.copy()
    if "player_id" not in stats:
        for alias in ("gsis_id", "sleeper_id"):
            if alias in stats:
                stats["player_id"] = stats[alias]
                break
    if "player_id" not in stats or "position" not in stats:
        return {}
    stats["player_id"] = stats["player_id"].map(_normal_identifier)
    stats = stats[stats["player_id"].notna()].drop_duplicates("player_id")
    return dict(zip(stats["player_id"], stats["position"]))


def _first_td_alias_groups(
    actuals: pd.DataFrame, *, season: int | None = None, week: int | None = None
) -> dict[str, set[str]]:
    """Map only unambiguous, week-scoped stats identifiers to aliases."""
    stats = actuals.copy()
    if season is not None and "season" in stats:
        stats = stats[pd.to_numeric(stats["season"], errors="coerce").eq(int(season))]
    if week is not None and "week" in stats:
        stats = stats[pd.to_numeric(stats["week"], errors="coerce").eq(int(week))]
    if "season_type" in stats:
        stats = stats[stats["season_type"].astype(str).str.upper().eq("REG")]
    aliases = [column for column in ("player_id", "gsis_id", "sleeper_id") if column in stats]
    if not aliases:
        return {}
    for column in aliases:
        stats[column] = stats[column].map(_normal_identifier)
    groups_by_alias: dict[str, set[frozenset[str]]] = {}
    for row in stats[aliases].to_dict(orient="records"):
        ids = {row[column] for column in aliases if row.get(column)}
        sleeper_id = row.get("sleeper_id")
        if sleeper_id:
            # Live releases may carry Sleeper identities as ``sleeper:<id>``
            # while weekly stats store the bare provider ID.
            ids.add(sleeper_id if sleeper_id.startswith("SLEEPER:") else f"SLEEPER:{sleeper_id}")
        for player_id in ids:
            groups_by_alias.setdefault(player_id, set()).add(frozenset(ids))
    # A duplicated provider ID attached to different weekly identities is not
    # safe evidence. Exact IDs remain usable only when they identify one row
    # identity (duplicate identical rows are harmless).
    return {
        alias: set(next(iter(groups)))
        for alias, groups in groups_by_alias.items()
        if len(groups) == 1
    }


def _first_td_name_team(
    actuals: pd.DataFrame, scorer_id: str, *, season: int | None = None, week: int | None = None
) -> tuple[str, str] | None:
    """Resolve a scorer by a unique exact id row, returning normalized name/team."""
    stats = actuals.copy()
    if season is not None and "season" in stats:
        stats = stats[pd.to_numeric(stats["season"], errors="coerce").eq(int(season))]
    if week is not None and "week" in stats:
        stats = stats[pd.to_numeric(stats["week"], errors="coerce").eq(int(week))]
    if "season_type" in stats:
        stats = stats[stats["season_type"].astype(str).str.upper().eq("REG")]
    id_cols = [column for column in ("player_id", "gsis_id", "sleeper_id") if column in stats]
    if not id_cols:
        return None
    mask = pd.Series(False, index=stats.index)
    for column in id_cols:
        mask |= stats[column].map(_normal_identifier).eq(scorer_id)
    matched = stats[mask]
    if len(matched) != 1:
        return None
    row = matched.iloc[0]
    name_col = "player_display_name" if "player_display_name" in row else "player_name" if "player_name" in row else None
    team_col = "team" if "team" in row else "recent_team" if "recent_team" in row else None
    if not name_col or not team_col:
        return None
    team, name = _normal_team(row[team_col]), _normal_name(row[name_col])
    return (team, name) if team and name else None


def _classify_first_td_row(row, pos_lookup: dict) -> str:
    """Same classification as first_td/src/labels.py::_classify_first_td.

    offense_skill requires td_team == posteam (ruling out defensive
    scores), return_touchdown != 1 (ruling out return scores), AND the
    scorer's position resolves to a skill position.

    The return_touchdown check MUST run before the position check, not
    just for non-skill scorers. On a kickoff/punt play, nflverse's
    posteam/td_team follow the RECEIVING team, not the kicking team -- so a
    receiving team's own returner taking it to the house has
    td_team == posteam even though the score is a special-teams return, not
    an offensive snap. Checking position first misclassifies a WR/RB who
    also returns kicks as offense_skill. Found by independent audit 2026-09
    as the same bug already fixed in first_td/src/labels.py::
    _classify_first_td -- this was a second, independent copy of the same
    logic that had not received the fix; the two must never drift again.
    """
    if row["td_team"] != row["posteam"]:
        return "defense" if row["td_team"] == row["defteam"] else "special_teams"
    if row.get("return_touchdown") == 1:
        return "special_teams"
    scorer_pos = pos_lookup.get(row["td_player_id"])
    return "offense_skill" if scorer_pos in _SKILL_POSITIONS else "defense"


def _first_td_by_game(pbp: pd.DataFrame, game_ids: set, pos_lookup: dict) -> dict:
    """game_id -> (first_td_player_id, first_td_kind) for every game with a TD."""
    work = pbp[pbp["game_id"].isin(game_ids) & pbp["touchdown"].eq(1)].copy()
    if work.empty:
        return {}
    work = work.sort_values(["game_id", "qtr", "play_id"], kind="stable")
    # Select the first row itself. groupby.first() fills nulls field by field,
    # which can combine the time from one touchdown with a later scorer ID.
    first = work.drop_duplicates("game_id", keep="first")
    result = {}
    for row in first.to_dict(orient="records"):
        scorer_id = row.get("td_player_id")
        if pd.isna(scorer_id):
            scorer_id = None
        # A null scorer on the earliest scoring row is unresolved identity,
        # not evidence that the first score was defensive or unlisted. Keep
        # the row's null intact and leave candidate settlements pending.
        kind = "unresolved" if _normal_identifier(scorer_id) is None else _classify_first_td_row(row, pos_lookup)
        result[row["game_id"]] = (scorer_id, kind)
    return result


def _no_touchdown_games(pbp: pd.DataFrame, game_ids: set, final_schedule: pd.DataFrame) -> set:
    """Final games whose complete play-by-play holds zero touchdowns.

    Nobody scored first in these, so every listed player is a real "No", not a
    pending row. Completeness is proved, not assumed: the running score on the
    game's plays must reach the schedule's final score, otherwise pbp may simply
    not have caught up and the game stays pending.
    """
    needed = {"game_id", "touchdown", "total_home_score", "total_away_score"}
    if not game_ids or not needed <= set(pbp.columns):
        return set()
    finals = final_schedule.set_index("_game_id")[["home_score", "away_score"]]
    plays = pbp[pbp["game_id"].isin(game_ids)]
    confirmed = set()
    for game_id, game in plays.groupby("game_id"):
        if game_id not in finals.index or game["touchdown"].eq(1).any():
            continue
        home, away = finals.loc[game_id, "home_score"], finals.loc[game_id, "away_score"]
        if (game["total_home_score"].max(), game["total_away_score"].max()) == (home, away):
            confirmed.add(game_id)
    return confirmed


def grade_first_td_file(
    path: str | Path,
    schedule: pd.DataFrame,
    pbp: pd.DataFrame,
    actuals: pd.DataFrame,
    *,
    season: int,
    week: int,
    participation: pd.DataFrame | None = None,
    reviewed_settlements: dict | None = None,
) -> dict:
    """Attach the game's first-TD scorer outcome to one live board.

    Unlike grade_anytime_td_file (season/weekly stat TOTALS), first-TD needs
    WHO scored first, by play order -- a fact that only exists in
    play-by-play, never in a weekly stats total. A final game is left
    pending until pbp actually contains touchdown rows for it. The source
    CSV is updated in place; frozen prediction/price columns are untouched.
    """
    source = Path(path)
    if not source.is_file():
        raise PublicationError(f"Anytime TD release is missing: {source}")
    original_board = read_table(source).copy()
    board = original_board.copy()
    required = {"game_id", "player_id"}
    missing = sorted(required - set(board.columns))
    if missing:
        raise PublicationError(
            f"Anytime TD release is missing grading columns: {', '.join(missing)}"
        )
    if "scored_first" not in board:
        board["scored_first"] = pd.Series(pd.NA, index=board.index, dtype="Float64")
    board["_game_id"] = board["game_id"].map(_normal_identifier)
    board["_player_id"] = board["player_id"].map(_normal_identifier)

    sched = _schedule_week(schedule.copy(), season, week)
    needed = {"game_id", "home_team", "away_team", "home_score", "away_score"}
    missing = sorted(needed - set(sched.columns))
    if missing:
        raise PublicationError(
            f"schedule is missing Anytime TD grading columns: {', '.join(missing)}"
        )
    if sched["game_id"].duplicated().any():
        raise PublicationError("schedule contains duplicate game_id values")
    sched = sched.copy()
    sched["_game_id"] = sched["game_id"].map(_normal_identifier)
    sched["home_score"] = pd.to_numeric(sched["home_score"], errors="coerce")
    sched["away_score"] = pd.to_numeric(sched["away_score"], errors="coerce")
    sched["_is_final"] = sched["home_score"].notna() & sched["away_score"].notna()
    final_schedule = sched[sched["_is_final"]].copy()
    final_game_ids = set(final_schedule["_game_id"].dropna().tolist())

    pbp_work = pbp.copy()
    if "game_id" in pbp_work:
        pbp_work["game_id"] = pbp_work["game_id"].map(_normal_identifier)
    scoped_actuals = actuals.copy()
    if "season" in scoped_actuals:
        scoped_actuals = scoped_actuals[pd.to_numeric(scoped_actuals["season"], errors="coerce").eq(int(season))]
    if "week" in scoped_actuals:
        scoped_actuals = scoped_actuals[pd.to_numeric(scoped_actuals["week"], errors="coerce").eq(int(week))]
    if "season_type" in scoped_actuals:
        scoped_actuals = scoped_actuals[scoped_actuals["season_type"].astype(str).str.upper().eq("REG")]
    pos_lookup = _first_td_position_lookup(scoped_actuals)
    id_aliases = _first_td_alias_groups(actuals, season=season, week=week)
    participation_info = _prepare_participation(
        participation if participation is not None else actuals, season, week
    )
    reviewed_settlements = reviewed_settlements or {}
    board_game_ids = set(board["_game_id"].dropna().tolist())
    board_final_ids = board_game_ids & final_game_ids
    first_td_by_game = _first_td_by_game(pbp_work, board_final_ids, pos_lookup)
    no_td_games = _no_touchdown_games(
        pbp_work, board_final_ids - set(first_td_by_game), final_schedule
    )

    pending_games = []
    updated_games = []
    updated_rows = 0
    for game_id in sorted(board_game_ids):
        if game_id not in final_game_ids:
            pending_games.append(game_id)
            continue
        game_rows = board[board["_game_id"].eq(game_id)]
        if game_id in first_td_by_game:
            first_scorer_id, kind = first_td_by_game[game_id]
        elif game_id in no_td_games:
            first_scorer_id, kind = None, "no_touchdown"
        else:
            # A final game whose pbp is missing or has not reached the final
            # score yet stays pending rather than guessing.
            pending_games.append(game_id)
            continue
        # A no-TD result is only a loss when the source market offered the
        # explicit no-scorer selection. Otherwise DraftKings voids the market.
        no_td_offered = None
        if kind == "no_touchdown":
            for column in ("first_no_td_offered", "no_touchdown_offered"):
                if column in game_rows:
                    values = game_rows[column].dropna().astype("string").str.lower().unique()
                    if len(values) == 1 and values[0] in {"true", "1", "yes"}:
                        no_td_offered = True
                    elif len(values) == 1 and values[0] in {"false", "0", "no"}:
                        no_td_offered = False
                    break
            if no_td_offered is None:
                if "settlement_status_first" not in board:
                    board["settlement_status_first"] = "open"
                board.loc[game_rows.index, "settlement_status_first"] = "awaiting_evidence"
                board.loc[game_rows.index, "scored_first"] = pd.NA
                pending_games.append(game_id)
                continue

        first_scorer_id_normalized = _normal_identifier(first_scorer_id)
        canonical_ids = id_aliases.get(first_scorer_id_normalized, {first_scorer_id_normalized})
        scorer_identity = (
            _first_td_name_team(scoped_actuals, first_scorer_id_normalized, season=season, week=week)
            if first_scorer_id_normalized else None
        )
        outcome = pd.Series(pd.NA, index=game_rows.index, dtype="Float64")
        settlement = pd.Series("awaiting_evidence", index=game_rows.index, dtype="string")
        for idx, row in game_rows.iterrows():
            player_id = row["_player_id"]
            reviewed = reviewed_settlements.get((
                int(season), int(week), game_id, player_id, "first",
            ))
            snaps = participation_info["snaps_by_alias"].get(player_id)
            if snaps is None and "player_display_name" in row and "team" in row:
                key = (_normal_team(row["team"]), _normal_name(row["player_display_name"]))
                snaps = participation_info["snaps_by_name_team"].get(key)
            is_scorer = bool(
                first_scorer_id_normalized
                and (player_id in canonical_ids or (
                    scorer_identity is not None
                    and "player_display_name" in row and "team" in row
                    and (_normal_team(row["team"]), _normal_name(row["player_display_name"])) == scorer_identity
                ))
            )
            if reviewed is not None and reviewed["status"] == "void":
                if is_scorer or (snaps is not None and float(snaps) > 0):
                    raise PublicationError(
                        f"reviewed First TD void conflicts with scorer/participation evidence: {game_id}/{player_id}"
                    )
                settlement.loc[idx] = "void"
                continue
            if is_scorer:
                # DraftKings settles to the player in possession, regardless
                # of whether the touchdown came on offense or a return.
                outcome.loc[idx] = 1.0
                settlement.loc[idx] = "settled"
            elif snaps is not None and float(snaps) <= 0:
                settlement.loc[idx] = "void"
            elif kind in {"offense_skill", "special_teams", "defense"} or (
                kind == "no_touchdown" and no_td_offered
            ):
                if snaps is not None and float(snaps) > 0:
                    outcome.loc[idx] = 0.0
                    settlement.loc[idx] = "settled"
            elif kind == "no_touchdown":
                # A verified no-TD game with no No Touchdown selection is void.
                settlement.loc[idx] = "void"
        if settlement.eq("awaiting_evidence").any():
            pending_games.append(game_id)
        board["scored_first"] = pd.to_numeric(board["scored_first"], errors="coerce").astype("Float64")
        board.loc[game_rows.index, "scored_first"] = outcome
        if "settlement_status_first" not in board:
            board["settlement_status_first"] = "open"
        board.loc[game_rows.index, "settlement_status_first"] = settlement
        if "status" in board:
            # Keep "void" (did not play): the Anytime grader owns that status
            # and this grader used to overwrite it with "final".
            legacy_void = original_board.loc[game_rows.index, "status"].astype("string").eq("void")
            keep_void = legacy_void | board.loc[game_rows.index, "settlement_status_first"].eq("void")
            board.loc[game_rows.index[~keep_void.to_numpy()], "status"] = "final"
        updated_games.append(game_id)
        updated_rows += int(settlement.ne("awaiting_evidence").sum())

    board = board.drop(columns=["_game_id", "_player_id"])
    encoded = board.to_csv(index=False, lineterminator="\n").encode("utf-8")
    changed = encoded != source.read_bytes()
    if changed:
        source.write_bytes(encoded)

    graded = (
        pd.to_numeric(board["scored_first"], errors="coerce").notna()
        & board.get("settlement_status_first", pd.Series("", index=board.index)).eq("settled")
    )
    board_games_final = board_game_ids <= final_game_ids
    resolved_first = board.get(
        "settlement_status_first", pd.Series("", index=board.index)
    ).isin(["settled", "void"])
    return {
        "status": "graded" if updated_games else "pending",
        "file": str(source),
        "season": int(season),
        "week": int(week),
        "final_games": int(len(board_game_ids & final_game_ids)),
        "graded_rows": int(graded.sum()),
        "updated_games": updated_games,
        "updated_rows": int(updated_rows),
        "pending_games": pending_games,
        "complete": bool(board_games_final and not pending_games and resolved_first.all()),
        "changed": changed,
    }


def grade_first_td_releases(root=None, *, participation_by_season: dict[int, pd.DataFrame | None] | None = None) -> dict:
    """Grade all published 2026 Anytime TD boards' first-TD column that have final games."""
    site_root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    directory = site_root / "betting" / "anytime_td"
    releases = []
    for (season, week), entry in sorted(canonical_td_releases(directory).items()):
        source = entry["csv_path"]
        if season >= 2026 and entry.get("prediction_mode", "live") == "live":
            releases.append((source, season, week))
    if not releases:
        return {"status": "skipped", "reason": "no published 2026 Anytime TD releases"}

    schedules = {}
    actuals_by_season = {}
    pbp_by_season = {}
    results = {}
    participation_by_season = participation_by_season if participation_by_season is not None else {}
    reviewed_settlements = load_reviewed_td_settlements(site_root)
    for source, season, week in releases:
        if season not in schedules:
            schedules[season] = fetch_nfl_schedule(season)
        schedule = schedules[season]
        slate = _schedule_week(schedule, season, week)
        if {"home_score", "away_score"} - set(slate.columns):
            raise PublicationError("schedule is missing score columns for Anytime TD grading")
        finals = slate["home_score"].notna() & slate["away_score"].notna()
        board = read_td_release(source)
        board_game_ids = {
            game_id for game_id in board["game_id"].map(_normal_identifier).dropna().tolist()
        }
        final_ids = {
            game_id for game_id in slate.loc[finals, "game_id"].map(_normal_identifier).dropna().tolist()
        }
        label = f"{season}w{week:02d}"
        if not board_game_ids & final_ids:
            results[label] = {"status": "skipped", "reason": "no final games"}
            continue
        if season not in actuals_by_season:
            actuals_by_season[season] = fetch_player_stats(season)
        if season not in pbp_by_season:
            pbp_by_season[season] = fetch_nfl_pbp(season)
        if season not in participation_by_season:
            try:
                participation_by_season[season] = fetch_snap_counts(season)
            except Exception:
                participation_by_season[season] = None
        results[label] = grade_first_td_file(
            source,
            schedule,
            pbp_by_season[season],
            actuals_by_season[season],
            participation=participation_by_season[season],
            season=season,
            week=week,
            reviewed_settlements=reviewed_settlements,
        )
    return results


def write_td_grading_stamps(anytime: dict, first_td: dict, root=None) -> list[str]:
    """Record ONE shared "results updated" time for all three TD markets.

    Anytime, 2+ TD and First TD are graded in the same pass, so a single stamp
    per week tells the page when they were last refreshed together. A stamp is
    only rewritten when a grader actually changed that week's CSV, so idle
    scheduled runs do not create commits.
    """
    site_root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    directory = site_root / "betting" / "anytime_td"
    written = []
    for label, a in anytime.items():
        if not isinstance(a, dict) or "season" not in a:
            continue
        f = first_td.get(label) if isinstance(first_td, dict) else None
        f = f if isinstance(f, dict) else {}
        if not (a.get("changed") or f.get("changed")):
            continue
        season, week = int(a["season"]), int(a["week"])
        payload = {
            "schema_version": 1,
            "season": season,
            "week": week,
            "graded_at": utc_now_iso(),
            "final_games": int(a.get("final_games", 0)),
            "anytime_graded_rows": int(a.get("graded_rows", 0)),
            "two_plus_graded_rows": int(a.get("graded_two_plus_rows", 0)),
            "first_td_graded_rows": int(f.get("graded_rows", 0)),
            "awaiting_stat_rows": int(a.get("awaiting_stat_rows", 0)),
        }
        target = directory / f"grading_{season}_week{week:02d}.json"
        target.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        written.append(str(target))
    return written


def grade_anytime_td_releases(
    root=None, *, participation_by_season: dict[int, pd.DataFrame | None] | None = None
) -> dict:
    """Grade all published 2026 Anytime TD boards that have final games."""
    site_root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    directory = site_root / "betting" / "anytime_td"
    releases = []
    for (season, week), entry in sorted(canonical_td_releases(directory).items()):
        source = entry["csv_path"]
        if season >= 2026 and entry.get("prediction_mode", "live") == "live":
            releases.append((source, season, week))
    if not releases:
        return {"status": "skipped", "reason": "no published 2026 Anytime TD releases"}

    schedules = {}
    actuals_by_season = {}
    participation_by_season = participation_by_season if participation_by_season is not None else {}
    results = {}
    reviewed_settlements = load_reviewed_td_settlements(site_root)
    for source, season, week in releases:
        if season not in schedules:
            schedules[season] = fetch_nfl_schedule(season)
        schedule = schedules[season]
        slate = _schedule_week(schedule, season, week)
        if {"home_score", "away_score"} - set(slate.columns):
            raise PublicationError("schedule is missing score columns for Anytime TD grading")
        finals = slate["home_score"].notna() & slate["away_score"].notna()
        board = read_td_release(source)
        board_game_ids = {
            game_id for game_id in board["game_id"].map(_normal_identifier).dropna().tolist()
        }
        final_ids = {
            game_id for game_id in slate.loc[finals, "game_id"].map(_normal_identifier).dropna().tolist()
        }
        label = f"{season}w{week:02d}"
        if not board_game_ids & final_ids:
            results[label] = {"status": "skipped", "reason": "no final games"}
            continue
        if season not in actuals_by_season:
            actuals_by_season[season] = fetch_player_stats(season)
        if season not in participation_by_season:
            try:
                participation_by_season[season] = fetch_snap_counts(season)
            except Exception:
                # A stats-only feed can still grade rows that it contains. It
                # must not, however, zero-fill quoted players absent from that
                # feed, so a failed snap fetch safely leaves those rows pending.
                participation_by_season[season] = None
        results[label] = grade_anytime_td_file(
            source,
            schedule,
            actuals_by_season[season],
            participation=participation_by_season[season],
            season=season,
            week=week,
            reviewed_settlements=reviewed_settlements,
        )
    return results
