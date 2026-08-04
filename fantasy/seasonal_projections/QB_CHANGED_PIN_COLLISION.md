# ✅ RESOLVED — superseded, retained for the record

> Resolved by moving the v39 experiment to an immutable 2014–2025 veteran snapshot, so it
> no longer pins the live 2026-bearing dataset. Neither option below was taken; do NOT repin
> or revert. The coaching suite passes 1103/1103. Text preserved as the record of the
> collision and the decision.

# ⚠ ACTION REQUIRED — the qb_changed join broke a v39 pinned input hash

**Caused by this work on 2026-08-03. Not fixed here, deliberately.**

## What happened

`join_qb_changed_2026.py --promote` populated `qb_changed` for the 916 rostered 2026 rows
of `season_dataset_2014_2026.csv`. That file is a **hash-pinned input** of the coach-quality
v39 prefit experiment:

```
fantasy/projections/coaching/assemble_real_panel_v39.py:56
FEATURE_SOURCE_MD5 = "8322a59e43251820cb393d40787f60e6"
```

| | md5 |
|---|---|
| pinned in `assemble_real_panel_v39.py` | `8322a59e43251820cb393d40787f60e6` |
| file before the join (backup kept) | `8322a59e43251820cb393d40787f60e6` |
| file now | `71bad6a2d6af122b5f24ce1f03d486b9` |

So the file DID match its pin immediately before the join, and the join moved it.
Consequence: **4 tests fail** under `fantasy/projections/coaching/tests/`, all from
`verify_pinned_activation_inputs()` raising
`AssemblyError: veteran feature source md5 71bad6a2... != pinned 8322a59e...`.
The rest of that suite is green (1052 passed).

## Why it was not "fixed" here

v39 pins its inputs BY VALUE under a committed pre-registration; the pin is the contract,
not a lint. Silently editing `FEATURE_SOURCE_MD5` to match a file I just changed would
defeat the entire point of pinning — the same failure class the v39 work exists to prevent.
Re-pinning is a deliberate, prereg-governed act and it is **Joseph's call**.

## The two options

1. **Re-pin** (if the qb_changed population is accepted as an intended input change):
   set `FEATURE_SOURCE_MD5 = "71bad6a2d6af122b5f24ce1f03d486b9"` and re-run the coaching
   suite. Note the v39 locks remain closed either way; this only restores the input gate.
2. **Revert** (if v39 must stay on the exact pinned bytes):
   `cp fantasy/seasonal_projections/season_dataset_2014_2026.pre_qbchanged.csv \
       fantasy/seasonal_projections/season_dataset_2014_2026.csv`
   — the byte-exact pre-join backup is retained at that path. This re-opens the
   `qb_changed` defect (all 923 2026 rows unpopulated across 12 consumers).

These conflict: option 2 restores v39's pin at the cost of reinstating a known-wrong
feature in the shipped 2026 projections. That trade is not mine to make.

## Related prior note

Workspace memory records an earlier, separate instance of this same file moving
(`8322a59e` → `71bad6a2`) from a concurrent session, left "NOT reverted, NOT re-pinned —
revert-or-re-pin is Joseph's call". The measurements above are from THIS session and show
the file matching `8322a59e` immediately before the join, so treat this as the live state
regardless of that history.
