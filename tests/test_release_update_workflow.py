from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "grade_releases.yml"


def test_grader_runs_on_release_updates_and_rechecks_every_day():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "  push:\n    branches: [main]\n    paths:" in text
    assert '      - "data/releases/manifest.json"' in text
    assert '      - "data/releases/builds/**"' in text
    assert '      - "betting/anytime_td/releases_manifest.json"' in text
    assert '      - "betting/anytime_td/releases/**"' in text
    assert '      - "betting/anytime_td/anytime_td_20*_week*.csv"' in text
    assert "    - cron: '17 */6 * * *'" in text
    assert "  workflow_dispatch:" in text
