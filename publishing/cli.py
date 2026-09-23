"""Command-line interface for candidate validation, publication, grading, and rollback."""
from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .candidate import build_candidate_metadata, write_candidate_sidecar
from .contract import PublicationError, utc_now_iso
from .grader import (
    fetch_nfl_schedule,
    fetch_player_stats,
    grade_anytime_td_releases,
    grade_fantasy,
    grade_first_td_releases,
    grade_predictions,
    write_td_grading_stamps,
)
from .manifest import load_manifest, published_builds
from .publisher import (
    _validated_correction,
    activate_release,
    publish_candidate,
    rollback_release,
    schedule_release,
)
from .validators import read_metadata, validate_candidate


def _print(value) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def _bootstrap(root: Path) -> dict:
    tracker = root / "betting" / "predictions_tracker.csv"
    fantasy_dir = root / "fantasy" / "fantasy_projections"
    if not tracker.is_file():
        raise FileNotFoundError(tracker)
    predictions = pd.read_csv(tracker)
    prediction_builds = {}
    fantasy_builds = {}
    with tempfile.TemporaryDirectory(prefix="jsa-release-bootstrap-") as temp_name:
        temp = Path(temp_name)
        for week in range(10, 18):
            selected = predictions[
                pd.to_numeric(predictions["season"], errors="coerce").eq(2025)
                & pd.to_numeric(predictions["week"], errors="coerce").eq(week)
            ].copy()
            if selected.empty:
                continue
            artifact = temp / f"predictions_2025_week{week:02d}.csv"
            selected.to_csv(artifact, index=False)
            metadata = build_candidate_metadata(
                "predictions",
                artifact,
                season=2025,
                week=week,
                model_version="legacy-2025-three-model-consensus",
                produced_at="2026-05-20T21:47:00Z",
                legacy_bootstrap=True,
            )
            entry = publish_candidate(artifact, metadata, root=root, activate=False)
            prediction_builds[week] = entry["build_id"]

        for source in sorted(fantasy_dir.glob("projections_2025_week*.csv")):
            try:
                week = int(source.stem.split("week", 1)[1])
            except (IndexError, ValueError):
                continue
            if week < 10:
                continue
            legacy = pd.read_csv(source, dtype={"player_id": "string"})
            legacy["season"] = 2025
            legacy["week"] = week
            artifact = temp / f"fantasy_2025_week{week:02d}.csv"
            legacy.to_csv(artifact, index=False)
            modified = datetime.fromtimestamp(source.stat().st_mtime, tz=timezone.utc)
            metadata = build_candidate_metadata(
                "fantasy",
                artifact,
                season=2025,
                week=week,
                model_version="legacy-2025-weekly-fantasy",
                produced_at=utc_now_iso(modified),
                legacy_bootstrap=True,
            )
            entry = publish_candidate(artifact, metadata, root=root, activate=False)
            fantasy_builds[week] = entry["build_id"]

    if 10 not in prediction_builds or 10 not in fantasy_builds:
        raise PublicationError("bootstrap requires populated 2025 Week 10 artifacts for both products")
    activate_release("predictions", prediction_builds[10], root=root)
    activate_release("fantasy", fantasy_builds[10], root=root)
    schedule_release(
        "predictions", 2026, 1, scheduled_for="2026-09-08T13:00:00Z", root=root
    )
    schedule_release("fantasy", 2026, 1, scheduled_for=None, root=root)
    return {
        "predictions": prediction_builds,
        "fantasy": fantasy_builds,
        "manifest": str(root / "data" / "releases" / "manifest.json"),
    }


def _live_candidate_schedule(metadata, supplied):
    if supplied is not None:
        return supplied
    meta = read_metadata(metadata)
    if meta.get("legacy_bootstrap"):
        return None
    return fetch_nfl_schedule(int(meta["season"]))


def _grade_published(root: Path, product: str = "all") -> dict:
    products = ("predictions", "fantasy") if product == "all" else (
        () if product == "anytime_td" else (product,)
    )
    results = {}
    schedules = {}
    actuals_by_season = {}
    for selected in products:
        candidates = [
            build for build in published_builds(selected, root=root)
            if int(build.get("season", 0)) >= 2026
        ]
        latest_by_week = {}
        for build in candidates:
            key = (int(build["season"]), int(build["week"]))
            latest_by_week[key] = build
        if not latest_by_week:
            results[selected] = {"status": "skipped", "reason": "no published 2026 builds"}
            continue
        product_results = {}
        for (season, week), build in sorted(latest_by_week.items()):
            label = f"{season}w{week:02d}"
            if (build.get("grading") or {}).get("complete"):
                product_results[label] = {
                    "status": "complete", "build_id": build["build_id"]
                }
                continue
            if season not in schedules:
                schedules[season] = fetch_nfl_schedule(season)
            schedule = schedules[season]
            slate = schedule.copy()
            if "season" in slate:
                slate = slate[pd.to_numeric(slate["season"], errors="coerce").eq(season)]
            if "week" in slate:
                slate = slate[pd.to_numeric(slate["week"], errors="coerce").eq(week)]
            finals = 0
            if {"home_score", "away_score"} <= set(slate):
                finals = int((slate["home_score"].notna() & slate["away_score"].notna()).sum())
            if finals == 0:
                product_results[label] = {"status": "skipped", "reason": "no final games"}
                continue
            if selected == "predictions":
                product_results[label] = grade_predictions(season, week, schedule, root=root)
            else:
                if season not in actuals_by_season:
                    actuals_by_season[season] = fetch_player_stats(season)
                product_results[label] = grade_fantasy(
                    season, week, actuals_by_season[season], schedule=schedule, root=root
                )
        results[selected] = product_results
    if product in ("all", "anytime_td"):
        results["anytime_td"] = grade_anytime_td_releases(root)
        results["first_td"] = grade_first_td_releases(root)
        results["td_grading_stamps"] = write_td_grading_stamps(
            results["anytime_td"], results["first_td"], root
        )
    return results


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(description="JoScho Analytics release pipeline")
    top.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    commands = top.add_subparsers(dest="command", required=True)

    sidecar = commands.add_parser("sidecar", help="write a hash-bound candidate sidecar")
    sidecar.add_argument("--product", choices=("predictions", "fantasy"), required=True)
    sidecar.add_argument("--artifact", type=Path, required=True)
    sidecar.add_argument("--season", type=int, required=True)
    sidecar.add_argument("--week", type=int, required=True)
    sidecar.add_argument("--model-version", required=True)
    sidecar.add_argument("--produced-at", default=None)
    sidecar.add_argument("--out", type=Path, default=None)

    validate = commands.add_parser("validate", help="validate without publishing")
    validate.add_argument("--artifact", type=Path, required=True)
    validate.add_argument("--metadata", type=Path, required=True)
    validate.add_argument("--schedule", type=Path, default=None)

    publish = commands.add_parser("publish", help="validate and publish an immutable build")
    publish.add_argument("--artifact", type=Path, required=True)
    publish.add_argument("--metadata", type=Path, required=True)
    publish.add_argument("--schedule", type=Path, default=None)
    publish.add_argument("--no-activate", action="store_true")

    status = commands.add_parser("status", help="print the current manifest")
    status.set_defaults()

    rollback = commands.add_parser("rollback", help="move the active pointer to a valid build")
    rollback.add_argument("--product", choices=("predictions", "fantasy"), required=True)
    rollback.add_argument("--build-id", default=None)

    schedule = commands.add_parser("schedule", help="set the next expected weekly release")
    schedule.add_argument("--product", choices=("predictions", "fantasy"), required=True)
    schedule.add_argument("--season", type=int, required=True)
    schedule.add_argument("--week", type=int, required=True)
    schedule.add_argument("--scheduled-for", default=None)

    grade = commands.add_parser("grade", help="grade one published week without mutating it")
    grade.add_argument("--product", choices=("predictions", "fantasy"), required=True)
    grade.add_argument("--season", type=int, required=True)
    grade.add_argument("--week", type=int, required=True)
    grade.add_argument("--schedule", type=Path, default=None)
    grade.add_argument("--actuals", type=Path, default=None)

    grade_active = commands.add_parser(
        "grade-published", aliases=["grade-active"],
        help="grade published 2026 releases when final games exist"
    )
    grade_active.add_argument(
        "--product", choices=("all", "predictions", "fantasy", "anytime_td"), default="all"
    )

    commands.add_parser("bootstrap", help="register immutable 2025 demo baselines")
    return top


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "sidecar":
            produced_at = args.produced_at or utc_now_iso()
            out = write_candidate_sidecar(
                args.product,
                args.artifact,
                season=args.season,
                week=args.week,
                model_version=args.model_version,
                produced_at=produced_at,
                destination=args.out,
            )
            _print({"sidecar": str(out)})
        elif args.command == "validate":
            source = _live_candidate_schedule(args.metadata, args.schedule)
            metadata = read_metadata(args.metadata)
            correction = _validated_correction(args.artifact, metadata, root)
            report = validate_candidate(
                args.artifact,
                metadata,
                schedule=source,
                allow_post_kickoff_correction=correction is not None,
            )
            _print(report.to_dict())
            return 0 if report.ok else 1
        elif args.command == "publish":
            source = _live_candidate_schedule(args.metadata, args.schedule)
            _print(
                publish_candidate(
                    args.artifact,
                    args.metadata,
                    schedule=source,
                    root=root,
                    activate=not args.no_activate,
                )
            )
        elif args.command in ("grade-published", "grade-active"):
            _print(_grade_published(root, args.product))
        elif args.command == "status":
            _print(load_manifest(root))
        elif args.command == "rollback":
            _print(rollback_release(args.product, args.build_id, root=root))
        elif args.command == "schedule":
            _print(
                schedule_release(
                    args.product,
                    args.season,
                    args.week,
                    scheduled_for=args.scheduled_for,
                    root=root,
                )
            )
        elif args.command == "grade":
            schedule = args.schedule
            if args.product == "predictions":
                source = schedule if schedule is not None else fetch_nfl_schedule(args.season)
                _print(grade_predictions(args.season, args.week, source, root=root))
            else:
                actuals = args.actuals if args.actuals is not None else fetch_player_stats(args.season)
                schedule_source = schedule if schedule is not None else fetch_nfl_schedule(args.season)
                _print(
                    grade_fantasy(
                        args.season,
                        args.week,
                        actuals,
                        schedule=schedule_source,
                        root=root,
                    )
                )
        elif args.command == "bootstrap":
            _print(_bootstrap(root))
        return 0
    except (PublicationError, FileNotFoundError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
