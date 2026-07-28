# U2 seasonal_projections + draft_board — Lens B

- U2B-1 - draft_board_2026.py:102,230,259 - @st.cache_data with no ttl on
  _load_board_2026/_refresh_date/_load_rank_equiv - a long-lived Streamlit process
  would serve a stale ADP overlay after the daily refresh - LOW - RISK - screened
  T10 (overlay churn is by design) - mitigation already in place: the refresh cron
  COMMITS and Streamlit Cloud redeploys on push, so a fresh process reads fresh
  bytes daily. Action: document; no code change.
- U2B-2 - refresh_board_adp.py:70,86 - ledger append + atomic tmp-file write, scoped
  to the overlay only - verified it cannot touch a frozen artifact (note, not a finding).

Coverage: as Lens A. NO FINDINGS of severity >= HIGH.
