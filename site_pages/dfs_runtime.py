"""Runtime adapter for the public DFS optimizer page.

Local development prefers the sibling producer checkout. Streamlit Cloud loads the
same reviewed engine from the vendored wheel. Solver code loads only on page render.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import pandas as pd

from publishing.manifest import active_release, load_manifest, resolve_build_artifact


class DfsRuntimeUnavailable(RuntimeError):
    pass


EXPECTED_ENGINE_VERSION = "0.2.3"
SITE_ROOT = Path(__file__).resolve().parents[1]


def optimizer_root() -> Path:
    configured = os.environ.get("DFS_OPTIMIZER_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "dfs_optimizer_v1_prod"


@lru_cache(maxsize=1)
def load_pipeline():
    root = optimizer_root()
    source = root / "src"
    sibling_source = (source / "pipeline.py").is_file()
    if sibling_source:
        source_text = str(source)
        if source_text not in sys.path:
            sys.path.insert(0, source_text)
    try:
        module = importlib.import_module("pipeline")
    except ModuleNotFoundError as exc:
        if exc.name == "pulp":
            raise DfsRuntimeUnavailable("PuLP/CBC is not installed in this Streamlit runtime") from exc
        raise DfsRuntimeUnavailable(f"DFS optimizer could not load: {exc}") from exc
    module_path = Path(module.__file__).resolve()
    if sibling_source and module_path.parent != source.resolve():
        raise DfsRuntimeUnavailable(f"a different pipeline module is already loaded: {module_path}")
    version = getattr(module, "ENGINE_VERSION", None)
    if version != EXPECTED_ENGINE_VERSION:
        raise DfsRuntimeUnavailable(
            f"DFS runtime version mismatch: expected {EXPECTED_ENGINE_VERSION}, loaded {version or 'unknown'}"
        )
    return module


def published_projection_root() -> Path:
    configured = os.environ.get("DFS_PROJECTION_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return SITE_ROOT / "fantasy" / "optimizer_projections"


def active_fantasy_source(root: Path | None = None) -> tuple[dict | None, Path | None]:
    """Return the checksum-verified active fantasy release and its CSV."""
    site_root = Path(root).resolve() if root is not None else SITE_ROOT
    try:
        manifest = load_manifest(site_root, strict=True)
        build = active_release("fantasy", manifest=manifest, root=site_root)
        artifact = resolve_build_artifact(build, root=site_root) if build else None
    except (OSError, ValueError, KeyError):
        return None, None
    if build is None or artifact is None or not build.get("sha256"):
        return None, None
    return build, artifact


def projection_metadata(path: Path) -> dict | None:
    metadata_path = path.with_suffix(".json")
    if not metadata_path.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    required = {
        "product": "dfs_optimizer_v1",
        "scoring": "draftkings_classic",
        "projection_units": "direct_dk_points",
    }
    if any(metadata.get(key) != value for key, value in required.items()):
        return None
    if metadata.get("projection_csv_sha256") != file_sha256(path):
        return None
    try:
        int(metadata["season"])
        int(metadata["week"])
    except (KeyError, TypeError, ValueError):
        return None
    return metadata


def active_projection_path(
    build: dict | None = None,
    *,
    root: Path | None = None,
) -> Path | None:
    """Find a checked DFS conversion tied to this exact fantasy release."""
    if build is None:
        build, _ = active_fantasy_source(root)
    if not build:
        return None

    source_build_id = str(build.get("build_id", ""))
    source_sha256 = str(build.get("sha256", ""))
    season, week = int(build.get("season", 0)), int(build.get("week", 0))
    if not source_build_id or not source_sha256 or not season or not week:
        return None

    projection_root = (
        Path(root).resolve() / "fantasy" / "optimizer_projections"
        if root is not None
        else published_projection_root()
    )
    if not projection_root.is_dir():
        return None

    candidates = []
    for path in projection_root.rglob(f"projections_{season}_week{week:02d}.csv"):
        metadata = projection_metadata(path)
        if not metadata:
            continue
        if (
            str(metadata.get("source_build_id", "")) != source_build_id
            or str(metadata.get("source_artifact_sha256", "")) != source_sha256
            or int(metadata.get("season", 0)) != season
            or int(metadata.get("week", 0)) != week
            or not isinstance(metadata.get("games"), list)
        ):
            continue
        generated = metadata.get("synced_at_utc") or metadata.get("generated_at_utc")
        try:
            generated_at = datetime.fromisoformat(str(generated).replace("Z", "+00:00"))
            if generated_at.tzinfo is None:
                continue
            generated_timestamp = generated_at.timestamp()
        except (TypeError, ValueError, OverflowError):
            continue
        candidates.append((generated_timestamp, str(metadata.get("producer_revision", "")), str(path), path))
    return max(candidates)[-1] if candidates else None


def projection_matches_slate(
    path: Path,
    salary_frame: pd.DataFrame,
    norm_team,
) -> bool:
    """Check salary games and local kickoff dates against conversion provenance."""
    metadata = projection_metadata(path)
    if not metadata:
        return False
    games = metadata.get("games")
    if not isinstance(games, list) or not games:
        return False

    salary_rows = salary_frame[["away", "home", "slate_date"]].drop_duplicates()
    slate_games = set()
    for row in salary_rows.itertuples(index=False):
        date = pd.to_datetime(row.slate_date, format="%m/%d/%Y", errors="coerce")
        teams = tuple(sorted((norm_team(row.away), norm_team(row.home))))
        if pd.isna(date) or not all(teams):
            continue
        slate_games.add((date.strftime("%Y-%m-%d"), teams))
    if not slate_games or len(slate_games) != len(salary_rows):
        return False

    published_games = set()
    for game in games:
        if not isinstance(game, dict):
            continue
        try:
            date = str(game["date"])
            teams = tuple(sorted(norm_team(team) for team in game["teams"]))
        except (KeyError, TypeError):
            continue
        if len(teams) == 2 and all(teams):
            published_games.add((date, teams))
    return bool(published_games) and slate_games.issubset(published_games)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_bytes(source) -> bytes:
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    if hasattr(source, "getvalue"):
        return source.getvalue()
    payload = source.read()
    return payload if isinstance(payload, bytes) else payload.encode("utf-8")


def source_digest(*payloads: bytes) -> str:
    digest = hashlib.sha256()
    for payload in payloads:
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()
