# Scripts

These are site diagnostics and artifact maintenance tools. None trains a model.
Run them from the repository root with the intended Python environment.

| Script | Role and effects |
|---|---|
| `bench_pages.py` | Measures page startup and resource use in fresh processes. Network is blocked by default; `--online` permits and counts outbound attempts. `--json PATH` writes a report to that path. |
| `bench_server.py` | Starts the local Streamlit server and measures boot, idle, and request costs. It is offline by default. `--json PATH` writes a report to that path. |
| `build_slate_2026.py` | Reads the 2026 schedule through `nflreadpy` and overwrites `betting/slate_2026.csv` with 272 regular-season matchups, without picks or lines. |
| `sync_optimizer_projection.py` | Converts the checksum-verified active weekly fantasy release with a pinned private-producer converter, then writes a DFS projection CSV and sidecar under `fantasy/optimizer_projections/`. It verifies source and output checksums, schedule coverage, and producer revision; reruns are idempotent for an already-matching artifact. The scheduled GitHub workflow checks out the private producer and may commit and push changed projection artifacts. |

The optimizer sync workflow runs after fantasy release changes, on its schedule,
or by manual dispatch. Local runs of the script also write files in the public
checkout. It does not fetch projections from an external API.
