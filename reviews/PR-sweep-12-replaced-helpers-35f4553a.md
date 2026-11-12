# sweep/12-replaced-helpers at 35f4553a (W-SWEEP; no PR number yet)

- Branch: `sweep/12-replaced-helpers`
- Head: 35f4553a
- Base: main 40183fb6
- Verdict: **CLEAN**

## Verified findings
None.

## What I checked
- **Migration 0190** (`0190_drop_unused_resource_tables`):
  - It is in W-SWEEP's range (0190-0194) and chained to main's single head `0131_agent_model_owner_only`. The branch has one head.
  - It drops `ln_broker_subscriptions` and `ln_chart_indicators`. Their only users were the deleted repositories (`broker_subscriptions.py`, `chart_indicators.py`), which nothing imported. No other code, test or script references the tables or their row classes.
  - The downgrade recreates exactly the columns, foreign keys and index of the originals (`0009_broker_sessions`, `0010_charts_watches`).
  - Round trip on a fresh PostgreSQL DB: upgrade head, downgrade to 0131 (both tables back), upgrade head (both gone). The current revision is 0190 (head).
- **13.2 deletions:** `trim_candle_history`, `load_chart_state`, `chart_stream`, `compact_document`, `retrieve_sections`, `semantic_retrieve` and the three repositories have no remaining callers in `*.py` or `*.ts`. The only hit is a test comment.
- **13.1 chat path:** `capabilities_list` now returns `charts: chart_capabilities()` (the supported timeframes and indicators), and its description says so. `export_agent_tool_reference.py --check` passes, and the manifest only names tools.
- **Tests:**
  - pytest `test_chart_capabilities.py`, `test_memory_retrieval.py`, `test_capability_exposure.py`: 63 passed.
  - `pytest --collect-only tests`: 2931 collected.
