"""No provider credential material may appear in tracked text, notebook source, or outputs.

Regression of record: `betting/sports_betting_agent.ipynb` carried a SAVED CELL OUTPUT with
an `sk-ant-api03-` prefix plus secret characters, committed to a public repo since
2026-05-12. The generating code had already been fixed months earlier; the stale OUTPUT was
never cleared, so the fix never reached the repo.

This scan reads only for PATTERNS. It never prints, logs or returns a matched value — a
leak-detector that echoes the leak is worse than no detector.
"""
import json
import re
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]

# Provider key shapes. Each requires enough post-prefix entropy that a bare placeholder
# ("sk-ant-api03-...", "<your key here>") is not flagged.
_PATTERNS = {
    "anthropic": re.compile(r"sk-ant-api\d{2}-[A-Za-z0-9_\-]{6,}"),
    "openai": re.compile(r"\bsk-[A-Za-z0-9]{32,}"),
    "github_pat": re.compile(r"\b(ghp|gho|ghs|ghr)_[A-Za-z0-9]{20,}"),
    "github_fine": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    "aws": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "slack": re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"),
    "private_key": re.compile(r"-----BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
}
_TEXT_SUFFIXES = {".py", ".md", ".txt", ".yml", ".yaml", ".json", ".cfg", ".toml", ".ps1"}


def _tracked_files():
    out = subprocess.run(
        ["git", "-c", f"safe.directory={_ROOT}", "ls-files"],
        cwd=_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        pytest.skip("git unavailable")
    for rel in out.stdout.splitlines():
        p = _ROOT / rel
        if p.is_file():
            yield rel, p


def _hits(text):
    """Return provider NAMES only — never the matched substring."""
    return sorted({name for name, pat in _PATTERNS.items() if pat.search(text)})


def test_no_credential_material_in_tracked_text_files():
    offenders = []
    for rel, p in _tracked_files():
        if p.suffix.lower() not in _TEXT_SUFFIXES or p.suffix.lower() == ".ipynb":
            continue
        if rel.startswith("tests/test_no_credential_leak.py"):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        h = _hits(text)
        if h:
            offenders.append(f"{rel} -> {h}")
    assert offenders == [], f"credential material in tracked files: {offenders}"


def test_no_credential_material_in_notebook_source_or_outputs():
    """Covers BOTH cell source and saved outputs — the output was the actual leak."""
    offenders = []
    for rel, p in _tracked_files():
        if p.suffix.lower() != ".ipynb":
            continue
        try:
            nb = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            continue
        for i, c in enumerate(nb.get("cells", [])):
            s = _hits("".join(c.get("source", [])))
            if s:
                offenders.append(f"{rel} cell {i} SOURCE -> {s}")
            for j, o in enumerate(c.get("outputs", []) or []):
                oh = _hits(json.dumps(o))
                if oh:
                    offenders.append(f"{rel} cell {i} OUTPUT {j} -> {oh}")
    assert offenders == [], f"credential material in notebooks: {offenders}"


def test_no_code_prints_key_material():
    """Only a boolean/status may be printed — never a prefix, length, or slice."""
    bad = re.compile(
        r"print\([^)]*(?:API_KEY|api_key|TOKEN|token|SECRET|secret)\s*\[|"      # slicing
        r"print\([^)]*len\(\s*(?:[A-Za-z_]*API_KEY|[A-Za-z_]*api_key)|"        # length
        r"print\([^)]*\{\s*(?:[A-Za-z_]*API_KEY|[A-Za-z_]*api_key)\s*\}")      # whole value
    offenders = []
    for rel, p in _tracked_files():
        if p.suffix.lower() not in {".py", ".ipynb"}:
            continue
        if rel.startswith("tests/test_no_credential_leak.py"):
            continue
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if p.suffix.lower() == ".ipynb":
            try:
                nb = json.loads(raw)
            except json.JSONDecodeError:
                continue
            raw = "\n".join("".join(c.get("source", [])) for c in nb.get("cells", []))
        for i, line in enumerate(raw.splitlines(), 1):
            if bad.search(line):
                offenders.append(f"{rel}:{i}")
    assert offenders == [], f"code prints credential material at: {offenders}"


def test_env_file_is_not_tracked():
    tracked = {rel for rel, _ in _tracked_files()}
    for name in (".env", ".env.local", ".env.production", ".streamlit/secrets.toml"):
        assert name not in tracked, f"{name} is tracked"


def test_the_scanner_actually_bites():
    """Self-proof against a synthetic value that is not a real credential."""
    planted = "sk-ant-api03-" + "A" * 40
    assert "anthropic" in _hits(planted)
    assert _hits("sk-ant-api03-") == [], "a bare placeholder must not be flagged"
