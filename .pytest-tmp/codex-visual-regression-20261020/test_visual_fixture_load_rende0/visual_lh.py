import os
os.environ['APP_OFFLINE'] = '1'
os.environ['JSA_VISUAL_LH_FIXTURE'] = r'C:\Users\josep\Desktop\random_stuff\cowork_OS\JoSchoAnalytics\tests\visual\fixtures\league_history.json'
import sys; sys.path[:0] = [r'C:\Users\josep\Desktop\random_stuff\cowork_OS\JoSchoAnalytics', r'C:\Users\josep\Desktop\random_stuff\cowork_OS\JoSchoAnalytics\site_pages']
import page_league_history as p
p._OFFLINE = True
p.render()
