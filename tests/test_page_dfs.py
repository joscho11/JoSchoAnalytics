import json
import os
import sys
from pathlib import Path

import pandas as pd

os.environ["APP_OFFLINE"] = "1"

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
SITE_PAGES = ROOT / "site_pages"
FIXTURES = ROOT / "tests" / "fixtures" / "optimizer"
SALARY_FIXTURE = FIXTURES / "dk_salaries.csv"
PROJECTION_FIXTURE = FIXTURES / "direct_dk_projections.csv"
sys.path[:0] = [str(ROOT), str(SITE_PAGES)]

import dfs_runtime as runtime  # noqa: E402
from dashboard_chrome import exact_table_height  # noqa: E402


def _render_page():
    __import__("page_dfs").render()


def _run():
    at = AppTest.from_function(_render_page, default_timeout=120).run()
    assert not at.exception, at.exception
    assert not at.error, [item.value for item in at.error]
    return at


def _upload_inputs(at, *, include_projection=True):
    at.file_uploader(key="dfs_salary_upload").set_value(
        ("DKSalaries.csv", SALARY_FIXTURE.read_bytes(), "text/csv")
    )
    if include_projection:
        at.file_uploader(key="dfs_projection_upload").set_value(
            ("projections_2026_week01.csv", PROJECTION_FIXTURE.read_bytes(), "text/csv")
        )
    at = at.run()
    assert not at.exception, at.exception
    assert not at.error, [item.value for item in at.error]
    return at


def test_runtime_and_test_fixtures_solve():
    assert SALARY_FIXTURE.is_file() and PROJECTION_FIXTURE.is_file()
    pipeline = runtime.load_pipeline()
    pool, lineup, summary = pipeline.solve(SALARY_FIXTURE, PROJECTION_FIXTURE)
    assert summary["n_rows"] == 26 and summary["n_games"] == 2
    assert int(pool["optimization_eligible"].sum()) == 24
    assert lineup is not None and len(lineup) == 9
    assert int(lineup["salary"].sum()) <= 50_000
    assert exact_table_height(len(lineup)) == 353


def test_page_is_real_slate_upload_only():
    at = _run()
    assert not at.segmented_control
    assert {widget.label for widget in at.file_uploader} == {
        "DraftKings salary CSV",
        "Direct-DK projection CSV",
    }
    assert any("Upload a DraftKings NFL Classic salary CSV" in item.value for item in at.info)
    assert any(
        exp.label == "What this beta does — and does not do" for exp in at.expander
    )


def test_valid_salary_explains_missing_projection(tmp_path, monkeypatch):
    monkeypatch.setenv("DFS_OPTIMIZER_ROOT", str(tmp_path / "optimizer"))
    monkeypatch.setenv("DFS_PROJECTION_ROOT", str(tmp_path / "published"))
    monkeypatch.setattr(runtime, "active_fantasy_source", lambda root=None: (
        {"build_id": "fantasy-2026w03-test", "season": 2026, "week": 3, "sha256": "a" * 64},
        tmp_path / "fantasy.csv",
    ))
    at = _upload_inputs(_run(), include_projection=False)
    assert any("Salary slate accepted" in item.value for item in at.success)
    assert any("2026 Week 3 DFS projections are not published yet" in item.value for item in at.warning)
    assert not any(button.label == "Optimize lineup" for button in at.button)


def test_uploaded_inputs_optimize_and_expose_dk_download():
    at = _upload_inputs(_run())
    assert any(button.label == "Optimize lineup" for button in at.button)
    next(button for button in at.button if button.label == "Optimize lineup").click()
    at = at.run()
    assert not at.exception, at.exception
    assert not at.error, [item.value for item in at.error]
    assert any(sub.value == "Optimized lineup" for sub in at.subheader)
    downloads = at.get("download_button")
    assert any(button.label == "Download DraftKings lineup" for button in downloads)
    metrics = {metric.label: metric.value for metric in at.metric}
    assert metrics["Salary used"] == "$50,000"
    assert metrics["Projected DK points"] == "152.5"


def test_tournament_mode_without_ceiling_falls_back_cleanly():
    at = _upload_inputs(_run())
    objective = next(widget for widget in at.segmented_control if widget.key == "dfs_objective")
    assert objective.options == ["Cash (expected points)", "Tournament (ceiling)"]
    assert objective.value == "Tournament (ceiling)"
    assert any("no `ceiling_pts` column" in item.value for item in at.warning)
    assert any(button.label == "Optimize lineup" for button in at.button)


def test_cash_mode_is_available_and_selectable():
    at = _upload_inputs(_run())
    objective = next(widget for widget in at.segmented_control if widget.key == "dfs_objective")
    assert objective.value == "Tournament (ceiling)"
    at = objective.set_value("Cash (expected points)").run()
    assert not at.exception, at.exception
    assert not any("no `ceiling_pts` column" in item.value for item in at.warning)


def test_failed_resolve_clears_the_previous_download():
    at = _upload_inputs(_run())
    next(button for button in at.button if button.label == "Optimize lineup").click()
    at = at.run()
    assert at.get("download_button")

    locks = next(widget for widget in at.multiselect if widget.key == "dfs_locked")
    locks.set_value(["9001", "9002"])
    next(button for button in at.button if button.label == "Optimize lineup").click()
    at = at.run()
    assert any("No legal lineup" in item.value for item in at.error)
    assert not at.get("download_button")
    assert not any(sub.value == "Optimized lineup" for sub in at.subheader)


def test_stale_team_mismatch_excluded_by_default():
    salary = SALARY_FIXTURE.read_text(encoding="utf-8")
    projection = PROJECTION_FIXTURE.read_text(encoding="utf-8")
    # Re-team one projected player relative to the salary slate: same name,
    # wrong team. matching.py resolves this as a name-unique "team_mismatch",
    # not a hard non-match, so it stays eligible unless the page excludes it.
    stale_projection = projection.replace(
        "demo-qb-a,Demo QB Alpha,QB,BUF,KC,2026,1,24.8,direct_dk_points",
        "demo-qb-a,Demo QB Alpha,QB,DAL,NYG,2026,1,24.8,direct_dk_points",
    )
    assert stale_projection != projection

    at = _run()
    at.file_uploader(key="dfs_salary_upload").set_value(("DKSalaries.csv", salary.encode("utf-8"), "text/csv"))
    at.file_uploader(key="dfs_projection_upload").set_value(
        ("projections_2026_week01.csv", stale_projection.encode("utf-8"), "text/csv")
    )
    at = at.run()
    assert not at.exception, at.exception

    checkbox = next(w for w in at.checkbox if w.key == "dfs_exclude_stale_team")
    assert checkbox.value is True
    assert "matched on name only" in checkbox.label
    locked = next(w for w in at.multiselect if w.key == "dfs_locked")
    n_options_excluded = len(locked.options)

    at = checkbox.set_value(False).run()
    assert not at.exception, at.exception
    locked_after = next(w for w in at.multiselect if w.key == "dfs_locked")
    assert len(locked_after.options) == n_options_excluded + 1


def _write_published_projection(
    root, *, week, build_id, source_sha, games,
    revision="1" * 40, synced_at="2026-09-27T12:00:00+00:00",
):
    projection = root / f"projections_2026_week{week:02d}.csv"
    projection.parent.mkdir(parents=True, exist_ok=True)
    projection.write_bytes(PROJECTION_FIXTURE.read_bytes())
    metadata = {
        "product": "dfs_optimizer_v1",
        "scoring": "draftkings_classic",
        "projection_units": "direct_dk_points",
        "season": 2026,
        "week": week,
        "source_build_id": build_id,
        "source_artifact_sha256": source_sha,
        "producer_revision": revision,
        "synced_at_utc": synced_at,
        "games": games,
        "projection_csv_sha256": runtime.file_sha256(projection),
    }
    projection.with_suffix(".json").write_text(json.dumps(metadata), encoding="utf-8")
    return projection


def test_active_projection_is_bound_to_release_and_salary_slate(tmp_path, monkeypatch):
    published = tmp_path / "published"
    published.mkdir()
    monkeypatch.setattr(runtime, "published_projection_root", lambda: published)
    source_sha = "a" * 64
    games = [{"date": "2026-09-13", "teams": ["BUF", "KC"]}]
    _write_published_projection(
        published, week=2, build_id="fantasy-2026w02-old", source_sha="b" * 64, games=games
    )
    older_projection = _write_published_projection(
        published / "2026" / "week03" / "fantasy-2026w03-current" / ("f" * 12),
        week=3, build_id="fantasy-2026w03-current", source_sha=source_sha, games=games,
        revision="f" * 40, synced_at="2026-09-26T12:00:00+00:00",
    )
    projection = _write_published_projection(
        published / "2026" / "week03" / "fantasy-2026w03-current" / ("1" * 12),
        week=3, build_id="fantasy-2026w03-current", source_sha=source_sha, games=games,
    )
    build = {
        "build_id": "fantasy-2026w03-current",
        "sha256": source_sha,
        "season": 2026,
        "week": 3,
    }
    assert runtime.active_projection_path(build) == projection

    salary = pd.DataFrame([{"away": "BUF", "home": "KC", "slate_date": "09/13/2026"}])
    assert runtime.projection_matches_slate(projection, salary, runtime.load_pipeline().norm_team)
    mismatched_date = salary.assign(slate_date="09/20/2026")
    assert not runtime.projection_matches_slate(
        projection, mismatched_date, runtime.load_pipeline().norm_team
    )

    corrected = {**build, "build_id": "fantasy-2026w03-corrected", "sha256": "c" * 64}
    assert runtime.active_projection_path(corrected) is None

    projection.write_text("tampered\n", encoding="utf-8")
    assert runtime.active_projection_path(build) == older_projection


def test_mismatched_override_still_fails_matchup_validation():
    salary = SALARY_FIXTURE.read_text(encoding="utf-8")
    projection = PROJECTION_FIXTURE.read_text(encoding="utf-8").replace(
        "demo-qb-a,Demo QB Alpha,QB,BUF,KC,2026,1,24.8,direct_dk_points",
        "demo-qb-a,Demo QB Alpha,QB,BUF,ZZZ,2026,1,24.8,direct_dk_points",
    )
    assert projection != PROJECTION_FIXTURE.read_text(encoding="utf-8")

    at = _run()
    at.file_uploader(key="dfs_salary_upload").set_value(
        ("DKSalaries.csv", salary.encode("utf-8"), "text/csv")
    )
    at.file_uploader(key="dfs_projection_upload").set_value(
        ("stale-projections.csv", projection.encode("utf-8"), "text/csv")
    )
    at = at.run()
    assert not at.exception, at.exception
    assert any("Slate validation failed" in item.value for item in at.error)
