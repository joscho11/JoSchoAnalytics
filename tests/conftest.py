"""Put the repo root and `site_pages/` on sys.path so the suites here can import the
app modules (`dashboard_utils`, `model_explanations`, `page_*`) regardless of the
working directory pytest was invoked from. Mirrors what app.py does at startup.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (_ROOT, _ROOT / "site_pages"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
