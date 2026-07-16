[probe] PFR pass season columns: ['bad_throw_pct', 'bad_throws', 'batted_balls', 'completed_air_yards', 'completed_air_yards_per_completion', 'completed_air_yards_per_pass_attempt', 'drop_pct', 'drops', 'intended_air_yards', 'intended_air_yards_per_pass_attempt', 'on_tgt_pct', 'on_tgt_throws', 'pa_pass_att', 'pa_pass_yards', 'pass_attempts', 'pass_yards_after_catch', 'pass_yards_after_catch_per_completion', 'pfr_id', 'player', 'pocket_time', 'pressure_pct', 'rpo_pass_att', 'rpo_pass_yards', 'rpo_plays', 'rpo_rush_att', 'rpo_rush_yards', 'rpo_yards', 'scramble_yards_per_attempt', 'scrambles', 'season', 'spikes', 'team', 'throwaways', 'times_blitzed', 'times_hit', 'times_hurried', 'times_pressured']
[join] PFR season rows -> gsis identity: 848/848
[join] (gsis,season) duplicate rows: 6 (multi-team rows expected; aggregated below)

[Gate1] R4 universe n=145; player-seasons with dropbacks>0: 581
  coverage-fraction deciles: [np.float64(0.5), np.float64(1.0), np.float64(1.0), np.float64(1.0), np.float64(1.0), np.float64(1.0), np.float64(1.0), np.float64(1.0), np.float64(1.0), np.float64(1.0), np.float64(1.0)]
  fully covered: 95% of 145 players
  coverage by dropback-volume tier: Q1_low:0.98  Q2:0.98  Q3:1.00  Q4_high:1.00
  corr(coverage, composite w): +0.165 (n=145)

[Gate3] persistence (adjacent player-season pairs, rel at pairs' own n, binomial rel):
  F1: n_pairs=360  rho_obs=+0.194  rel=0.731  rho_true=+0.266 
  F2: n_pairs=360  rho_obs=+0.128  rel=0.782  rho_true=+0.163 
  F2 construct check: stayers rho=+0.193 (n=235) vs movers rho=+0.059 (n=125) -> CONSTRUCT FAIL (line-owned)

[Gate4] redundancy vs five incumbents (SCORED universe n=31, raw values, Pearson + 95% CI):
  F1: cpoe -0.29[-0.58,+0.07]clear  bad -0.32[-0.61,+0.04]clear  qsucc -0.04[-0.39,+0.32]clear  q10 -0.18[-0.50,+0.19]clear  deep -0.45[-0.69,-0.11]clear
  F2: cpoe +0.31[-0.05,+0.60]clear  bad +0.24[-0.13,+0.55]clear  qsucc -0.54[-0.75,-0.23]clear  q10 -0.54[-0.75,-0.23]clear  deep +0.10[-0.27,+0.44]clear
  F1 x F2: -0.16 [-0.48,+0.21] n=31

[Gate6] MoM split-half sigma^2_alpha, NS=60, isolated child streams:
  F1: sig2a_med=0.001627 mean=0.001616 cs.std=0.000437 (sig^2 scale) CV=0.27 (denom=mean) <=0 0%±0 splits=60 | k=222.7 med-w(scored)=0.868 
  F2: sig2a_med=0.001045 mean=0.001040 cs.std=0.000110 (sig^2 scale) CV=0.11 (denom=mean) <=0 0%±0 splits=60 | k=451.8 med-w(scored)=0.764 

[F3] pocket_time column present in PFR pass season feed: True

[VERDICT TABLE] (gates: 1 coverage · 2 per-opportunity · 3 persistence · 4 redundancy · 5 workload-map(not a gate) · 6 sigma2a>0)
  F1: G1=PASS G2=PASS(per-opportunity by construction) G3=FAIL(rho_obs=+0.194, rho_true=+0.266) G4=PASS G6=PASS
  F2: G1=PASS G2=PASS(per-opportunity by construction) G3=FAIL(rho_obs=+0.128, rho_true=+0.163) G4=PASS G6=PASS | construct: CONSTRUCT FAIL (line-owned)
  F3: screened above
## F3 pocket_time — completion of the registered exploratory branch
(the main run mis-branched: column present but unscreened; completing, not re-screening)
[G1] pocket_time coverage: 571 player-seasons on R4 universe; non-null share of PFR-covered rows: 1.00
[G3] rho_obs=+0.154 (n_pairs=389); rho_true: UNMEASURABLE under the registered binomial rel (pocket_time is not a proportion) -> per prereg, UNMEASURABLE IS NOT PASSED -> Gate 3 FAIL
[G4] cpoe -0.16[-0.48,+0.21]clear  bad -0.22[-0.53,+0.15]clear  qsucc +0.43[+0.09,+0.68]clear  q10 +0.45[+0.11,+0.69]clear  deep +0.24[-0.12,+0.55]clear
[G6] sig2a_med=0.005139 cs.std=0.000776 (sig^2) CV=0.15 <=0 0% splits=60 | k=597.4
VERDICT F3: G1 PASS · G2 per-opportunity (time per dropback) · G3 FAIL (rho_true UNMEASURABLE by the registered method; not passed) · OUT at Gate 3