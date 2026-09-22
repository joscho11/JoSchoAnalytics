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
    ids = {m["id"] for m in shap + native}
    missing = set(me.DISPLAYED_HELP_IDS) - ids
    assert not missing, f"Help cards missing from snapshot: {missing}"
    assert len(me.weekly_point_cards()) == 4
    assert len(me.rookie_projection_cards()) == 3
    assert me.card_by_id("spread_xgb") is not None


def test_live_eval_numbers_match_published_books():
    import json
    import sys

    sys.path.insert(0, str(me.HERE / "betting"))
    from live_2026 import LIVE_HIGH_N, LIVE_HIGH_WILSON_LOWER, LIVE_HIGH_WINS

    wins = sum(row["wins"] for row in me.SPREAD_HIGH_BY_SEASON)
    n = sum(row["n"] for row in me.SPREAD_HIGH_BY_SEASON)
    assert wins == LIVE_HIGH_WINS
    assert n == LIVE_HIGH_N

    audit = json.loads(me._HIGH_AUDIT_PATH.read_text(encoding="utf-8"))
    benchmark = audit["baseline"]["historical_high"]
    assert benchmark["gap"] == 3.0
    assert benchmark["pick_rows"] == 446
    assert benchmark["wins"] == 253
    assert benchmark["n"] == 436
    assert benchmark["wilson_lower"] == LIVE_HIGH_WILSON_LOWER
    assert [(r["season"], r["wins"], r["n"]) for r in me.SPREAD_HIGH_BY_SEASON] == [
        (2021, 85, 136),
        (2022, 53, 94),
        (2023, 52, 96),
        (2024, 25, 45),
        (2025, 38, 65),
    ]

    evidence = json.loads(
        (me.HERE / "futures" / "published" / "evidence.json").read_text(encoding="utf-8")
    )
    assert abs(evidence["mae_model"] - 2.2578033419991446) < 1e-9
    assert abs(evidence["mae_market"] - 2.2088068181818183) < 1e-9
    assert me.SEASON_TOTALS_COEF["Posted win total"] > 1.0
    shares = me.season_totals_importance()
    assert shares[0][0] == "Posted win total"
    assert shares[0][1] == max(s[1] for s in shares)


def test_checked_snapshot_is_static_help_copy():
    sources = me.snapshot_sources()
    assert sources.get("kind") == "static-help-cards"
    assert me.SNAPSHOT_PATH.is_file()
    shap, stale = me.shap_models()
    native = me.native_models()
    assert stale == []
    ids = {m["id"] for m in shap + native}
    assert set(me.DISPLAYED_HELP_IDS) <= ids


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
    banned = {"sk" + "learn", "xg" + "boost", "job" + "lib"}
    assert banned & imports == set()


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
