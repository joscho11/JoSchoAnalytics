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
    snap_column = next(
        (column for column in ("offense_snaps", "offensive_snaps", "snap_counts", "snaps") if column in stats),
        None,
    )
    pct_column = next(
        (column for column in ("offense_pct", "offensive_pct", "snap_pct") if column in stats),
        None,
    )
    if snap_column is None and pct_column is None:
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
    if snap_column is not None:
        snaps = pd.to_numeric(stats[snap_column], errors="coerce")
    else:
        # A positive offensive snap percentage proves participation.  Treat a
        # reported zero as a confirmed non-participant for void handling.
        snaps = pd.to_numeric(stats[pct_column], errors="coerce")
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
    if not ({"rushing_tds", "receiving_tds"} & set(stats.columns)):
        raise PublicationError("actual stats are missing rushing_tds/receiving_tds")

    aliases = [col for col in ("player_id", "gsis_id", "sleeper_id") if col in stats]
    for col in aliases:
        stats[col] = stats[col].map(_normal_identifier)
    stats = stats[stats["player_id"].notna()].copy()
    td_columns = [col for col in ("rushing_tds", "receiving_tds") if col in stats]
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
            touchdowns = stat_info["td_by_alias"].get(row["_player_id"])
            matched_stats = touchdowns is not None
            if touchdowns is None and "player_display_name" in row and "team" in row:
                key = (_normal_team(row["team"]), _normal_name(row["player_display_name"]))
                touchdowns = stat_info["td_by_name_team"].get(key)
                matched_stats = touchdowns is not None
            if matched_stats:
                touchdowns = float(touchdowns or 0.0)
                return ("loss" if touchdowns <= 0 else "win", touchdowns)
            if participation_info["available"]:
                snaps = participation_info["snaps_by_alias"].get(row["_player_id"])
                if snaps is None and "player_display_name" in row and "team" in row:
                    key = (_normal_team(row["team"]), _normal_name(row["player_display_name"]))
                    snaps = participation_info["snaps_by_name_team"].get(key)
                if snaps is not None:
                    return ("loss", 0.0) if float(snaps) > 0 else ("void", float("nan"))
            return ("pending", float("nan"))

        outcomes = game_rows.apply(player_outcome, axis=1)
        states = outcomes.map(lambda value: value[0])
        touchdown_values = outcomes.map(lambda value: value[1])
        if states.eq("pending").any():
            pending_games.append(game_id)
            continue
        if "status" not in board:
            board["status"] = "pregame"
        win_mask = states.eq("win")
        loss_mask = states.eq("loss")
        void_mask = states.eq("void")
        board.loc[game_rows.index[win_mask], "scored_anytime"] = 1
        board.loc[game_rows.index[loss_mask], "scored_anytime"] = 0
        board.loc[game_rows.index[void_mask], "scored_anytime"] = pd.NA
        if "scored_two_plus" not in board:
            board["scored_two_plus"] = pd.Series(
                pd.NA, index=board.index, dtype="Float64"
            )
        board.loc[game_rows.index[~void_mask], "scored_two_plus"] = (
            pd.to_numeric(touchdown_values[~void_mask], errors="coerce").ge(2).astype(int).to_numpy()
        )
        board.loc[game_rows.index[void_mask], "scored_two_plus"] = pd.NA
        board.loc[game_rows.index[~void_mask], "status"] = "final"
        board.loc[game_rows.index[void_mask], "status"] = "void"
        updated_games.append(game_id)
        updated_rows += len(game_rows)

    board = board.drop(columns=["_game_id", "_player_id"])
    changed = not board.equals(original_board)
    if changed:
        encoded = board.to_csv(index=False, lineterminator="\n").encode("utf-8")
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
    work = work.sort_values(["game_id", "qtr", "play_id"])
    first = work.groupby("game_id", as_index=False).first()
    result = {}
    for row in first.to_dict(orient="records"):
        kind = _classify_first_td_row(row, pos_lookup)
        result[row["game_id"]] = (row.get("td_player_id"), kind)
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
    pos_lookup = _first_td_position_lookup(actuals)
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
        outcome = pd.Series(0.0, index=game_rows.index)
        if kind == "offense_skill" and first_scorer_id is not None:
            match = game_rows["_player_id"].eq(_normal_identifier(first_scorer_id))
            outcome.loc[match] = 1.0
        board.loc[game_rows.index, "scored_first"] = outcome.to_numpy()
        if "status" in board:
            board.loc[game_rows.index, "status"] = "final"
        updated_games.append(game_id)
        updated_rows += len(game_rows)

    board = board.drop(columns=["_game_id", "_player_id"])
    changed = not board.equals(original_board)
    if changed:
        encoded = board.to_csv(index=False, lineterminator="\n").encode("utf-8")
        source.write_bytes(encoded)

    graded = pd.to_numeric(board["scored_first"], errors="coerce").notna()
    board_games_final = board_game_ids <= final_game_ids
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
        "complete": bool(board_games_final and not pending_games and graded.all()),
        "changed": changed,
    }


def grade_first_td_releases(root=None) -> dict:
    """Grade all published 2026 Anytime TD boards' first-TD column that have final games."""
    site_root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    directory = site_root / "betting" / "anytime_td"
    releases = []
    for source in sorted(directory.glob("anytime_td_*_week*.csv")):
        match = _ANYTIME_TD_RELEASE_RE.fullmatch(source.name)
        if match is None:
            continue
        season, week = int(match.group("season")), int(match.group("week"))
        if season >= 2026:
            releases.append((source, season, week))
    if not releases:
        return {"status": "skipped", "reason": "no published 2026 Anytime TD releases"}

    schedules = {}
    actuals_by_season = {}
    pbp_by_season = {}
    results = {}
    for source, season, week in releases:
        if season not in schedules:
            schedules[season] = fetch_nfl_schedule(season)
        schedule = schedules[season]
        slate = _schedule_week(schedule, season, week)
        if {"home_score", "away_score"} - set(slate.columns):
            raise PublicationError("schedule is missing score columns for Anytime TD grading")
        finals = slate["home_score"].notna() & slate["away_score"].notna()
        board = read_table(source)
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
        results[label] = grade_first_td_file(
            source,
            schedule,
            pbp_by_season[season],
            actuals_by_season[season],
            season=season,
            week=week,
        )
    return results


def grade_anytime_td_releases(root=None) -> dict:
    """Grade all published 2026 Anytime TD boards that have final games."""
    site_root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    directory = site_root / "betting" / "anytime_td"
    releases = []
    for source in sorted(directory.glob("anytime_td_*_week*.csv")):
        match = _ANYTIME_TD_RELEASE_RE.fullmatch(source.name)
        if match is None:
            continue
        season, week = int(match.group("season")), int(match.group("week"))
        if season >= 2026:
            releases.append((source, season, week))
    if not releases:
        return {"status": "skipped", "reason": "no published 2026 Anytime TD releases"}

    schedules = {}
    actuals_by_season = {}
    participation_by_season = {}
    results = {}
    for source, season, week in releases:
        if season not in schedules:
            schedules[season] = fetch_nfl_schedule(season)
        schedule = schedules[season]
        slate = _schedule_week(schedule, season, week)
        if {"home_score", "away_score"} - set(slate.columns):
            raise PublicationError("schedule is missing score columns for Anytime TD grading")
        finals = slate["home_score"].notna() & slate["away_score"].notna()
        board = read_table(source)
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
        )
    return results
