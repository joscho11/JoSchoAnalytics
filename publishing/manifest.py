"""Read, query, and atomically update the public release manifest."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from .contract import PRODUCTS, SCHEMA_VERSION, parse_aware_datetime, sha256_file, utc_now_iso
from .paths import manifest_path, resolve_site_path


def empty_manifest() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": None,
        "products": {
            product: {
                "active_build": None,
                "previous_build": None,
                "next_release": None,
                "builds": {},
            }
            for product in PRODUCTS
        },
        "grading": {"products": {}},
    }


def _normalize_manifest(payload: dict) -> dict:
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        return empty_manifest()
    if not isinstance(payload.get("products"), dict):
        payload["products"] = {}
    for product in PRODUCTS:
        if not isinstance(payload["products"].get(product), dict):
            payload["products"][product] = {}
        state = payload["products"][product]
        state.setdefault("active_build", None)
        state.setdefault("previous_build", None)
        state.setdefault("next_release", None)
        if not isinstance(state.get("builds"), dict):
            state["builds"] = {}
    if not isinstance(payload.get("grading"), dict):
        payload["grading"] = {}
    if not isinstance(payload["grading"].get("products"), dict):
        payload["grading"]["products"] = {}
    return payload


def load_manifest(root: str | Path | None = None, *, strict: bool = False) -> dict:
    path = manifest_path(root)
    if not path.is_file():
        if strict:
            raise FileNotFoundError(path)
        return empty_manifest()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        if strict:
            raise
        return empty_manifest()
    if strict and (
        not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION
    ):
        raise ValueError("unsupported or malformed release manifest")
    return _normalize_manifest(payload)


def write_manifest(payload: dict, root: str | Path | None = None) -> Path:
    path = manifest_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = dict(payload)
    body["schema_version"] = SCHEMA_VERSION
    body["updated_at"] = utc_now_iso()
    encoded = json.dumps(body, indent=2, sort_keys=True) + "\n"
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        prefix="manifest-",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    ) as handle:
        handle.write(encoded)
        temp = Path(handle.name)
    os.replace(temp, path)
    return path


def product_state(product: str, manifest: dict | None = None, root=None) -> dict:
    if product not in PRODUCTS:
        raise ValueError(f"unknown product {product!r}")
    payload = manifest if manifest is not None else load_manifest(root)
    return payload.get("products", {}).get(product, {})


def active_release(product: str, manifest: dict | None = None, root=None) -> dict | None:
    state = product_state(product, manifest, root)
    build_id = state.get("active_build")
    build = state.get("builds", {}).get(str(build_id)) if build_id else None
    if not isinstance(build, dict):
        return None
    try:
        artifact = resolve_site_path(build["artifact"], root)
    except (KeyError, ValueError):
        return None
    if not artifact.is_file():
        return None
    if build.get("sha256") and sha256_file(artifact) != build["sha256"]:
        return None
    return dict(build)


def resolve_active_artifact(
    product: str,
    *,
    manifest: dict | None = None,
    root=None,
    prefer_graded: bool = False,
) -> Path | None:
    build = active_release(product, manifest, root)
    if not build:
        return None
    return resolve_build_artifact(build, root=root, prefer_graded=prefer_graded)


def resolve_build_artifact(
    build: dict,
    *,
    root=None,
    prefer_graded: bool = False,
) -> Path | None:
    """Resolve one build; a bad graded result falls back to its frozen source."""
    def checked(relative, expected_hash):
        try:
            path = resolve_site_path(relative, root)
        except (TypeError, ValueError):
            return None
        if not path.is_file():
            return None
        if expected_hash and sha256_file(path) != expected_hash:
            return None
        return path

    source = checked(build.get("artifact"), build.get("sha256"))
    if source is None:
        return None
    if prefer_graded:
        grading = build.get("grading") or {}
        graded = checked(grading.get("artifact"), grading.get("artifact_sha256"))
        if graded is not None:
            return graded
    return source


def published_builds(product: str, manifest: dict | None = None, root=None) -> list[dict]:
    state = product_state(product, manifest, root)
    builds = []
    for build in state.get("builds", {}).values():
        if not isinstance(build, dict):
            continue
        try:
            int(build["season"])
            int(build["week"])
        except (KeyError, TypeError, ValueError):
            continue
        try:
            artifact = resolve_site_path(build["artifact"], root)
        except (KeyError, ValueError):
            continue
        if not artifact.is_file():
            continue
        if build.get("sha256") and sha256_file(artifact) != build["sha256"]:
            continue
        builds.append(dict(build))
    return sorted(
        builds,
        key=lambda item: (
            int(item.get("season", 0)), int(item.get("week", 0)), str(item.get("published_at", ""))
        ),
    )


def default_selection(
    product: str,
    fallback: tuple[int, int],
    *,
    manifest: dict | None = None,
    root=None,
) -> tuple[int, int]:
    build = active_release(product, manifest, root)
    if not build:
        return int(fallback[0]), int(fallback[1])
    try:
        return int(build["season"]), int(build["week"])
    except (KeyError, TypeError, ValueError):
        return int(fallback[0]), int(fallback[1])


def release_status(
    product: str,
    season: int,
    week: int,
    *,
    manifest: dict | None = None,
    root=None,
    now: datetime | None = None,
) -> dict:
    state = product_state(product, manifest, root)
    matching = [
        build for build in published_builds(product, manifest, root)
        if int(build.get("season", -1)) == int(season) and int(build.get("week", -1)) == int(week)
    ]
    if matching:
        active_id = state.get("active_build")
        build = next(
            (item for item in matching if item.get("build_id") == active_id),
            matching[-1],
        )
        return {
            "status": str(build.get("status") or "Published"),
            "color": "green",
            "icon": ":material/check_circle:",
            "detail": f"Validated {build.get('published_at', 'publication time unavailable')}",
            "build_id": build.get("build_id"),
        }
    next_release = state.get("next_release") or {}
    try:
        is_next = (
            int(next_release.get("season", -1)) == int(season)
            and int(next_release.get("week", -1)) == int(week)
        )
    except (TypeError, ValueError):
        is_next = False
    scheduled_for = next_release.get("scheduled_for") if is_next else None
    if scheduled_for:
        try:
            scheduled = parse_aware_datetime(scheduled_for)
            current = now or datetime.now(timezone.utc)
            if current.tzinfo is None or current.utcoffset() is None:
                current = current.replace(tzinfo=timezone.utc)
            if current.astimezone(timezone.utc) < scheduled:
                return {
                    "status": "Scheduled",
                    "color": "orange",
                    "icon": ":material/schedule:",
                    "detail": f"Target publication {scheduled.isoformat().replace('+00:00', 'Z')}",
                    "build_id": None,
                }
        except (TypeError, ValueError):
            pass
    return {
        "status": "Awaiting projections",
        "color": "gray",
        "icon": ":material/pending:",
        "detail": "No validated release is active for this week.",
        "build_id": None,
    }


def track_record_default_season(
    fallback: int = 2025,
    *,
    manifest: dict | None = None,
    root=None,
) -> int:
    payload = manifest if manifest is not None else load_manifest(root)
    grading = payload.get("grading", {})
    products = grading.get("products", {}) if isinstance(grading, dict) else {}
    predictions = products.get("predictions", {}) if isinstance(products, dict) else {}
    latest = predictions.get("latest") if isinstance(predictions, dict) else None
    if not isinstance(latest, dict):
        return int(fallback)
    try:
        if int(latest.get("final_games", 0)) > 0:
            return int(latest["season"])
    except (KeyError, TypeError, ValueError):
        pass
    return int(fallback)
