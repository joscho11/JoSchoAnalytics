"""Idempotent grading that never mutates a published prediction snapshot."""
from __future__ import annotations

import json
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
