import sys; sys.path[:0] = [r'C:\Users\josep\Desktop\random_stuff\cowork_OS\JoSchoAnalytics', r'C:\Users\josep\Desktop\random_stuff\cowork_OS\JoSchoAnalytics\site_pages']
import streamlit as st; st.session_state['atd_week'] = 6
import page_anytime_td as p
p.render()
