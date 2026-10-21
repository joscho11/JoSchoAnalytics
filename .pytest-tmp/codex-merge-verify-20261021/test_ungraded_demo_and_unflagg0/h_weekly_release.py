import sys; sys.path[:0] = [r'C:\Users\josep\Desktop\random_stuff\cowork_OS\JoSchoAnalytics', r'C:\Users\josep\Desktop\random_stuff\cowork_OS\JoSchoAnalytics\site_pages']
from pathlib import Path
import page_weekly_fantasy as p
_available = p.available_projection_files
_default = p.page_common.release_default_selection
_status = p.page_common.render_release_status
try:
    p.available_projection_files = lambda: {(2026, 6): Path(r'C:\Users\josep\Desktop\random_stuff\cowork_OS\JoSchoAnalytics\data\releases\results\fantasy\2026\week06\fantasy-2026w06-3cfa101a43f4-graded.csv')}
    p.page_common.release_default_selection = lambda *a, **k: (2026, 6)
    p.page_common.render_release_status = lambda *a, **k: None
    p.render()
finally:
    p.available_projection_files = _available
    p.page_common.release_default_selection = _default
    p.page_common.render_release_status = _status
