import json
import os
import sys
from pathlib import Path

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
    at = _upload_inputs(_run(), include_projection=False)
    assert any("Salary slate accepted" in item.value for item in at.success)
    assert any("projection-data gap" in item.value for item in at.warning)
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
    objective = next(widget for widget in at.radio if widget.key == "dfs_objective")
    assert objective.options == ["Cash (expected points)", "Tournament (ceiling)"]
    at = objective.set_value("Tournament (ceiling)").run()
    assert not at.exception, at.exception
    assert any("no `ceiling_pts` column" in item.value for item in at.warning)
    assert any(button.label == "Optimize lineup" for button in at.button)


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


def test_auto_discovery_requires_a_valid_candidate_sidecar(tmp_path, monkeypatch):
    published = tmp_path / "published"
    published.mkdir()
    projection = published / "projections_2026_week01.csv"
    projection.write_text("projection_units\ndirect_dk_points\n", encoding="utf-8")
    metadata = {
        "product": "dfs_optimizer_v1",
        "scoring": "draftkings_classic",
        "projection_units": "direct_dk_points",
        "season": 2026,
        "week": 1,
        "projection_csv_sha256": runtime.file_sha256(projection),
    }
    projection.with_suffix(".json").write_text(json.dumps(metadata), encoding="utf-8")
    monkeypatch.setattr(runtime, "published_projection_root", lambda: published)
    monkeypatch.setattr(runtime, "optimizer_root", lambda: tmp_path / "optimizer")
    assert runtime.latest_projection_path() == projection

    projection.write_text("tampered\n", encoding="utf-8")
    assert runtime.latest_projection_path() is None
