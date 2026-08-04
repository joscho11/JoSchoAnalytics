# Quarantined artifacts — NOT a public loading path

Nothing in this directory is read by the site. `site_pages/page_common.load_agent_analysis`
resolves `betting/agent_analysis_{season}_week{week}.json` and `dashboard_data._compute_hc_stats`
globs `betting/agent_analysis_*.json` — neither is recursive, so files here are unreachable.

## agent_analysis_2025_week10.json (quarantined 2026-08-03)

Contained 14 `Sharp Money` and 14 `Line Movement` assertions with specific figures
("45% sharp vs 60% public", "opened 3.5 now 2.5"). Every one was generated from the
hardcoded `WEEK_10_LINES` dictionary in `betting/sports_betting_agent.ipynb` — there was
no market data behind any of them. They rendered on the Weekly Predictions page as
analysis, on a site whose standing rule is that it has no sharp-money or line-movement
information.

Retained rather than deleted so the record of what was published survives. Do NOT move it
back. If genuine market data is ever wired in, a regenerated artifact must carry
`provenance.market_data` with a non-mock `source`, a `captured_at` stamp and
`verified: true`, which `dashboard_utils.market_provenance_ok` enforces.

Side effect, by design: this was the only agent cache, so the agent-derived
high-confidence statistic is now unavailable and the Help page omits it rather than
printing a figure derived from fabricated inputs.
