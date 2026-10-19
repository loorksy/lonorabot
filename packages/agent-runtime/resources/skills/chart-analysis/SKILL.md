# Chart Analysis

## Purpose
Lonora chart-analysis workflow.

## When to activate
Use for the matching current task or durable trigger; never infer financial authority from relevance.

## When not to activate
Unrelated tasks, unavailable required tools, failed dependencies or exhausted context budget.

## Preconditions and required evidence
Use current owner-scoped tool results, exact broker identities and observation times. Missing data remains unavailable.

## Workflow and tool usage
1. Establish the actual account and exact broker symbol from current Agent scope. A specialist keeps its bound account/symbol; a Personal Agent may inspect owned markets. Do not rewrite suffixes, infer another account, or treat a remembered price as a fresh quote.
2. Discover an existing scoped chart with chart_list when offered, then chart_inspect. Reuse its actual ID and inspected version. Read symbol, timeframe, scene status/revision, source observation time and candle/indicator alignment. Never invent a chart ID or revision. Missing or stale evidence cannot support an actionable recommendation.
3. Read only the necessary candle tail and server-calculated supported indicators. Narrow tail or use chart_read_indicator for exact numerical evidence; use artifact_read paging when a large result supplies result_ref. Browser pixels and indicator display do not replace server values.
4. Explain only what current evidence supports: observed structure, alternative scenarios, invalidation and uncertainty. WAIT is valid. A visual annotation or scenario is not an order, approval, trading authority or proof of profitability.
5. When drawing is requested or materially clarifies the analysis, use only offered authorized chart mutation tools. Read current state first; use typed time/price anchors and the current version with chart_annotate. The supported surface includes levels, trend lines, notes, zones, rays, channels, Fibonacci, arrows and scenarios. Keep markings focused and labeled; do not draw decoration or invent missing time/price evidence. Change only your attributed drawing layer, preserving owner and peer work.
6. After a mutation inspect persisted state and scene status. Distinguish saved geometry from a refreshed scene and from a client display acknowledgment. On version conflict inspect and reconcile the actual drawing identities before a new update. Never repeat a mutation solely because its response or image is unavailable.
7. For a requested image, chart_snapshot with chart_id captures the persisted candles, indicators and drawings; explicit account/symbol/timeframe produces a candle-only snapshot. PNG is the normal Web/Mobile format. Retain the returned artifact ID and original source/revision metadata. A saved semantic snapshot is not a browser screenshot and does not confirm that a user's device displayed it.
8. When artifact_read offers view_image, inspect the saved raster artifact using its real ID before making visual claims about its composition or drawings. A metadata/file-save result is not pixel inspection. Use the actual image observation and its availability status; if pixels are unavailable, state that boundary. Do not claim an image was visually verified from a filename, successful tool call or JSON alone.
9. Deliver generated files through actual authenticated message attachments. Never manufacture sandbox URLs, storage paths, Markdown image destinations or delivery receipts. Separate generated, inspected, attached and client-rendered outcomes. A cloud chart continues on the server; a snapshot freezes its recorded source state.

## Decision rules and failure handling
Inspect machine status and stable error code. Correct invalid arguments from the offered schema. Missing data stays unavailable; do not substitute another symbol or stale image. Re-check fresh broker/account evidence immediately before any separately authorized financial decision. Never retry an ambiguous financial mutation. Chart inspection, drawings and image review do not grant financial authority.

## Anti-patterns
No invented success, stale actionable recommendations, authority escalation, unbounded context or browser-only durable state.

## Output contract
Return concise sourced findings, actions actually completed, remaining uncertainty, and persisted resource/artifact identities when available.

## Related skills
None required.
