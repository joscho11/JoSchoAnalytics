"""Cross-link page registry (design 4g). The entrypoint (app.py) populates
PAGES with the st.Page objects after building them; page modules read PAGES at render
time to build st.page_link cross-links without importing the entrypoint (no circular
import). Empty until the entrypoint runs — page modules must handle a missing key.
"""
# Public presentation only; odds capture, release artifacts, and grading are separate.
# Remove a slug after reviewing its data freshness to restore its page and promotions.
ARCHIVED_PAGES = frozenset({"anytime-tds", "college-basketball"})


def is_archived(slug: str) -> bool:
    return slug in ARCHIVED_PAGES


PAGES = {}
