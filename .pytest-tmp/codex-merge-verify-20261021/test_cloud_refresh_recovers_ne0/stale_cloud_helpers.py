import sys; sys.path[:0] = [r'C:\Users\josep\Desktop\random_stuff\cowork_OS\JoSchoAnalytics', r'C:\Users\josep\Desktop\random_stuff\cowork_OS\JoSchoAnalytics\site_pages']
import app
import dashboard_utils as du
import page_weekly_predictions as weekly
import page_track_record as track
for name in ('ats_record_parts', 'format_ats_metric_delta', 'format_ats_record', 'push_mask'):
    if hasattr(du, name):
        delattr(du, name)
from pathlib import Path
du.__joscho_source_mtime_ns__ = Path(du.__file__).stat().st_mtime_ns
weekly.__joscho_source_mtime_ns__ = 0
track.__joscho_source_mtime_ns__ = 0
app._refresh_cloud_synced_modules()
assert all(hasattr(du, name) for name in ('ats_record_parts', 'format_ats_metric_delta', 'format_ats_record', 'push_mask'))
assert weekly.ats_record_parts is du.ats_record_parts
assert track.ats_record_parts is du.ats_record_parts
