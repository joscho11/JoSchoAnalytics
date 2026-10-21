import sys; sys.path[:0] = [r'C:\Users\josep\Desktop\random_stuff\cowork_OS\JoSchoAnalytics', r'C:\Users\josep\Desktop\random_stuff\cowork_OS\JoSchoAnalytics\site_pages']
from pathlib import Path
import page_weekly_fantasy as p
_available = p.available_projection_files
_default = p.page_common.release_default_selection
_status = p.page_common.render_release_status
try:
    p.available_projection_files = lambda: {(2026, 1): Path(r'C:\Users\josep\Desktop\random_stuff\cowork_OS\JoSchoAnalytics\.pytest-tmp\week7-final-suite\test_future_release_uses_enabl0\projections_2026_week01.csv')}
    p.page_common.release_default_selection = lambda *a, **k: (2026, 1)
    p.page_common.render_release_status = lambda *a, **k: None
    p.render()
finally:
    p.available_projection_files = _available
    p.page_common.release_default_selection = _default
    p.page_common.render_release_status = _status
