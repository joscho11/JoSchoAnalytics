import sys; sys.path.insert(0, r'C:\Users\josep\Desktop\random_stuff\cowork_OS\JoSchoAnalytics')
import streamlit as st
import dashboard_chrome as c
events = []
c.send_ga_event = lambda name, extra_params=None: events.append([name, extra_params])
st.query_params['private_filter'] = 'never-log-this'
c.site_pageview('Home', '')
c.site_pageview('Home', '')
c.site_pageview('Draft Board', 'draft-board')
st.json(events)
