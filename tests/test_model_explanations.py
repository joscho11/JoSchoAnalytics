import ast
from pathlib import Path

import model_explanations as me


def test_all_current_production_models_are_covered():
    shap, stale = me.shap_models()
    native = me.native_models()

    assert stale == []
    assert len(shap) == 8
    assert len(native) == 14
    assert {m["group"] for m in shap + native} == {
        "Season projections · Non-rookie models",
        "Season projections · Rookie models",
        "Weekly fantasy",
        "Betting",
    }
    assert all(len(m["features"]) == 5 for m in shap + native)
    weekly = [m for m in native if m["group"] == "Weekly fantasy"]
    assert {m["subgroup"] for m in weekly} == {"QB", "RB", "WR", "TE"}
    assert [m["label"] for m in shap if m["group"].endswith("Non-rookie models")] == [
        "QB", "RB", "WR", "TE"
    ]
    assert [m["label"] for m in shap if m["group"].endswith("Rookie models")] == [
        "RB", "WR", "TE"
    ]


def test_shap_snapshots_are_bound_to_current_artifacts():
    for _, _, _, relative_path, expected_md5, _, _ in me.SHAP_SNAPSHOTS:
        artifact = me.HERE / relative_path
        assert artifact.is_file()
        assert me._md5(artifact) == expected_md5


def test_checked_snapshot_is_bound_to_every_source_artifact():
    sources = me.snapshot_sources()
    expected_weekly = {
        path.relative_to(me.HERE).as_posix()
        for path in (me.HERE / "fantasy" / "models").glob("*_model.pkl")
    }
    expected_native = expected_weekly | {
        "betting/models/totals_xgboost.pkl",
        "betting/models/totals_ridge.pkl",
    }
    expected_shap = {
        relative_path
        for _, _, _, relative_path, _, _, _ in me.SHAP_SNAPSHOTS
    }

    assert set(sources) == expected_native | expected_shap
    assert len(sources) == 22
    for relative_path, expected_md5 in sources.items():
        artifact = me.HERE / relative_path
        assert artifact.is_file()
        assert me._md5(artifact) == expected_md5


def test_runtime_module_does_not_import_training_stack():
    tree = ast.parse(Path(me.__file__).read_text(encoding="utf-8"))
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports |= {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert {"joblib", "numpy", "xgboost", "sklearn"} & imports == set()


def test_chart_html_escapes_labels_and_scales_largest_bar():
    rendered = me.chart_html({
        "label": "A <model>",
        "method": "test",
        "features": [("A & B", 20.0), ("C", 10.0)],
    })
    assert "A &lt;model&gt;" in rendered
    assert "A &amp; B" in rendered
    assert "width:100.0%" in rendered
    assert "20.0%" in rendered


def test_calibration_audit_covers_every_position_and_defines_bias_direction():
    rows = me.VETERAN_CALIBRATION_AUDIT
    assert {row["position"] for row in rows} == {"QB", "RB", "WR", "TE"}
    assert sum(row["n"] for row in rows) == 2589
    assert next(row for row in rows if row["position"] == "RB")["top_bias"] == -21.33

    rendered = me.calibration_audit_html()
    assert "Top-20% bias" in rendered
    assert "ca-under'>-21.3" in rendered
    assert "ca-over'>+4.2" in rendered


def test_native_models_point_at_real_artifacts():
    expected = {
        path.stem
        for path in (Path(me.HERE) / "fantasy" / "models").glob("*_model.pkl")
    }
    actual = {
        m["id"].removeprefix("weekly_") + "_model"
        for m in me.native_models()
        if m["group"] == "Weekly fantasy"
    }
    assert actual == expected
