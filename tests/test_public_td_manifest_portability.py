from pathlib import Path

from publishing.td_releases import canonical_td_releases


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_TD_DIR = ROOT / "betting" / "anytime_td"


def test_checked_in_td_manifest_and_hashed_artifacts_are_portable():
    releases = canonical_td_releases(PUBLIC_TD_DIR)
    assert {(2026, week) for week in range(1, 6)} <= set(releases)

    for entry in releases.values():
        if "metadata_path" not in entry:
            continue
        paths = [entry["csv_path"]]
        paths.append(entry["metadata_path"])
        for path in paths:
            data = path.read_bytes()
            assert b"\r\n" not in data
