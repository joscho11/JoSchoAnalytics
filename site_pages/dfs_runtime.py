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
from functools import lru_cache
from pathlib import Path


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


def latest_projection_path() -> Path | None:
    candidates = []
    roots = (published_projection_root(), optimizer_root() / "outputs")
    for root_priority, root in enumerate(roots):
        for path in root.glob("projections_*.csv"):
            metadata = projection_metadata(path)
            if metadata is not None:
                candidates.append((
                    int(metadata["season"]),
                    int(metadata["week"]),
                    root_priority,
                    path.stat().st_mtime_ns,
                    path,
                ))
    return max(candidates)[-1] if candidates else None


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
