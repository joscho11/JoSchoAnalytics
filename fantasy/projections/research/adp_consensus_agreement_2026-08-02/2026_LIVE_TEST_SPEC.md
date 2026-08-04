# 2026 live-test specification

This document records the analysis universe before 2026 outcomes are known. It prevents the player cutoff from being selected after seeing which population performs best.

## Player populations

The published 2026 board may extend through the top 300 players by same-date overall ADP, subject to projection availability.

The **only formal test population** is overall ADP ranks **1–245**, inclusive. A player is eligible only when the locked point-in-time snapshot contains valid ADP, Sleeper projection, and JoScho model projection values for that player.

Overall ADP ranks **246–300** are a separate exploratory deep-sleeper population. They must be reported separately and must never be pooled into the top-245 hit rate, confidence interval, permutation test, incremental-lift estimate, or headline. This population may support a later deep-sleepers/undrafted video, but it is not part of the confirmatory test.

There is no top-180 2026 test. Top 180 belongs only to the historical study's drafted-player sensitivity analysis and is not a required 2026 reporting universe.

## Point-in-time lock

The primary input is the last successful dated snapshot at or before the declared 2026 board/video publication cutoff. That cutoff must be recorded before regular-season outcomes are examined. ADP and Sleeper projections must come from the same archived retrieval event, and the JoScho model version used for the published board must be frozen and hashed.

Later snapshots may be used to study market movement or contamination, but the best-performing cutoff may not replace the declared primary cutoff.

## Confirmatory analysis

Within ADP ranks 1–245, evaluate cases where the JoScho and Sleeper models disagree with ADP in the same direction. Report the pre-established positional-rank disagreement thresholds:

- greater than 5 spots;
- greater than 7.5 spots;
- greater than 10 spots.

The zero-threshold result may be shown descriptively but is not a large-disagreement headline.

For every threshold, report the numerator, denominator, hit rate, uncertainty interval, and comparison with Sleeper-only calls. A high hit rate does not establish incremental JoScho value unless the corresponding lift over Sleeper alone excludes zero under the declared inference procedure.

## Deep-sleeper analysis

Analyze ranks 246–300 only after labeling them exploratory. Report player-level calls and sample sizes. Do not combine this range with ranks 1–245, and do not describe its results as confirmation of the primary hypothesis.

The boundary is intentionally non-overlapping: rank 245 belongs to the formal population; the deep-sleeper population starts at rank 246.
