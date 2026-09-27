import hashlib
import json
from pathlib import Path

import pytest

from publishing.contract import sha256_file
from scripts import sync_optimizer_projection as sync


def test_sync_accepts_lf_checkout_of_crlf_hashed_fantasy_release(tmp_path, monkeypatch):
    root = tmp_path / "site"
    source_path = root / "data" / "releases" / "fantasy.csv"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(
        b"season,week,team,opponent_team,kickoff,player_id,position\n"
        b"2026,3,BUF,NYJ,2026-09-27T17:00:00Z,one,QB\n"
        b"2026,3,NYJ,BUF,2026-09-27T17:00:00Z,two,QB\n"
    )
    # The release publisher hashes text artifacts in canonical CRLF form,
    # while this fixture represents the LF bytes seen on the Ubuntu runner.
    source_sha256 = sha256_file(source_path)
    build = {
        "season": 2026,
        "week": 3,
        "build_id": "fantasy-2026w03-test",
        "artifact": "data/releases/fantasy.csv",
        "sha256": source_sha256,
    }
    monkeypatch.setattr(sync.runtime, "active_fantasy_source", lambda _root: (build, source_path))

    class Pipeline:
        @staticmethod
        def norm_team(team):
            return str(team).strip().upper()

        @staticmethod
        def validate_projection_frame(frame):
            return int(frame["season"].iloc[0]), int(frame["week"].iloc[0])

    monkeypatch.setattr(sync.runtime, "load_pipeline", lambda: Pipeline())

    projection_bytes = (
        b"season,week,team,opponent_team\n"
        b"2026,3,BUF,NYJ\n"
        b"2026,3,NYJ,BUF\n"
    )
    converter = tmp_path / "dk_from_half_ppr.py"
    converter.write_text("# test converter stub\n", encoding="utf-8")

    def fake_converter(command, *, check, cwd):
        assert check is True
        assert cwd == converter.parents[1]
        output_path = Path(command[command.index("--out") + 1])
        output_path.write_bytes(projection_bytes)
        output_path.with_suffix(".json").write_text(
            json.dumps({
                # The producer hashes the exact input bytes it sees.
                "source_artifact_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
                "projection_csv_sha256": hashlib.sha256(projection_bytes).hexdigest(),
            }),
            encoding="utf-8",
        )

    monkeypatch.setattr(sync.subprocess, "run", fake_converter)
    result = sync.sync_active_release(
        root=root,
        converter=converter,
        producer_revision="19d0e1ecc8731e91910e8f85447311e383d03272",
    )

    assert result is not None
    projection_path, metadata_path = result
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["source_artifact_sha256"] == source_sha256
    assert metadata["projection_csv_sha256"] == hashlib.sha256(projection_path.read_bytes()).hexdigest()


def test_sync_still_rejects_artifact_that_does_not_match_manifest(tmp_path, monkeypatch):
    source_path = tmp_path / "fantasy.csv"
    source_path.write_bytes(b"season,week\n2026,3\n")
    build = {
        "season": 2026,
        "week": 3,
        "build_id": "fantasy-2026w03-test",
        "artifact": "fantasy.csv",
        "sha256": "0" * 64,
    }
    monkeypatch.setattr(sync.runtime, "active_fantasy_source", lambda _root: (build, source_path))
    converter = tmp_path / "dk_from_half_ppr.py"
    converter.write_text("# test converter stub\n", encoding="utf-8")

    with pytest.raises(ValueError, match="checksum does not match its manifest"):
        sync.sync_active_release(
            root=tmp_path,
            converter=converter,
            producer_revision="19d0e1ecc8731e91910e8f85447311e383d03272",
        )
