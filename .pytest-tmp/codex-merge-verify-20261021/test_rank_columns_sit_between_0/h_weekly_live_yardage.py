import sys; sys.path[:0] = [r'C:\Users\josep\Desktop\random_stuff\cowork_OS\JoSchoAnalytics', r'C:\Users\josep\Desktop\random_stuff\cowork_OS\JoSchoAnalytics\site_pages']
import page_weekly_fantasy as p
_live = p.load_actual_stats
try:
    p.load_actual_stats = lambda season, week: {
        'qb_pass_yds': {'00-0034857': 250.0}, 'qb_rush_yds': {'00-0034857': 12.0},
    }
    p.render()
finally:
    p.load_actual_stats = _live
