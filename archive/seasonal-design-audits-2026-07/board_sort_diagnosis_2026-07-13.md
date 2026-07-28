# Draft Board sort — root-cause diagnosis (2026-07-13)

**Root cause (one paragraph):** `st.dataframe` sorts each column by its underlying pandas
dtype, not by the on-screen format. The board builds three display columns as formatted
**strings** (`object`/`str` dtype, rendered via `TextColumn`), so clicking their headers sorts
them **lexicographically**, not numerically — `gap_disp` (`"20"` sorts below `"5"`; negatives
like `"-11"` mis-order against `"-1"`), `p50_disp` (sorts on the whole `"317 (100th %ile)"`
string, so the percentile suffix pollutes the order), and `eff_disp` (`"98"`/`"Rookie"`/`"–"`
mixed, 32 sentinel rows). A fourth column, `proj_pos_rank`, is numeric (`Int64`) but carries one
`<NA>` (Gainwell), and `st.dataframe`'s native sort places NaN inconsistently — the "NaN is the
bug" case. The remaining numeric columns already sort correctly.

## Column-by-column (verified against `_load_board_2026()` output, 180 rows)

| Displayed column | source col | config | dtype | sorts | verdict |
|---|---|---|---|---|---|
| Gap | `gap_disp` | Text | str | lexicographic | **BROKEN** — negatives + magnitude; `'–'` ×1 |
| Expected | `p50_disp` | Text | str | lexicographic on `"317 (100th %ile)"` | **BROKEN** — sorts incl. the %ile suffix |
| NFL Efficiency %ile | `eff_disp` | Text | str | lexicographic | **BROKEN** — `'Rookie'` ×14, `'–'` ×18 |
| Proj position rank | `proj_pos_rank` | Number | Int64 (1 `<NA>`) | numeric, NaN mis-placed | **SENTINEL BUG** (not string) |
| Position rank | `adp_pos_rank` | Number | int64 (0 null) | numeric | OK — already correct |
| Floor | `p10` | Number | float64 (0 null) | numeric | OK |
| Ceiling | `p90` | Number | float64 (0 null) | numeric | OK |
| Top-12 chance | `top12_pct` | Number | float64 (0 null) | numeric | OK |
| Draft Price (ADP) | `adp_half_ppr` | Number | float64 (0 null) | numeric | OK |
| Player / Pos / Team | `*_disp`/`team` | Text | str | lexicographic | OK (names/labels — string sort is correct) |

So of the eight named columns, **three are string-broken (Gap, Expected, Efficiency)**, **one
has the NaN-sentinel bug (Proj position rank)**, and **four are already numeric and correct
(Position rank, Floor, Ceiling, Top-12 chance)** — Joseph's expected list was a superset; this
narrows it.

## Structural constraint the fix must navigate (flag for the step-3 approach)

`st.dataframe` has **no per-column custom sort key** — a column sorts by its own dtype. So
"numeric sort + unchanged display string" cannot both hold on one column when the display carries
non-numeric text (`'–'`, `'Rookie'`, the `%ile` suffix): a `NumberColumn` sorts numerically but
can only show a number (NaN → blank, not `'–'`), and a `TextColumn` shows the string but sorts
lexicographically. Separately, "sentinels at the bottom in **both** ascending and descending"
is impossible with `st.dataframe`'s native single-direction header-click sort and a static
value (a high value is bottom-asc but top-desc). Both requirements are only satisfiable with an
**explicit, app-controlled sort** (a "Sort by" + direction control, sorting in pandas with
`na_position='last'`, which pins sentinels to the bottom regardless of direction) — which also
lets the display strings stay exactly as they are. The alternative (make the columns numeric so
native header-click is numeric) fixes the sort but changes the display (loses `'–'`/`'Rookie'`/
the in-cell `%ile`). This is the design fork for step 3.
