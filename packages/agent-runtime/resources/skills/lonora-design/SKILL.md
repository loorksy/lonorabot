---
name: lonora-design
description: Compose native, evidence-backed visual replies with accessible layouts, diagrams and local interactive calculations using Lonora's shared visual identity.
---

# Lonora Design Skill

Follow the owner's current language or explicit preference in replies and labels.
English instructions and examples do not require an English response.

## Steps

1. Lead with the answer. Choose prose, a compact native composition, or a mixture.
   A greeting, definition or capability question usually needs text, not a form.
   No separate designer, page, screenshot or model call is required.
   Load this procedure only when useful. Downloadable reports use file delivery.
2. Ground observations in exact successful current-request call IDs and JSON
   Pointer paths. The observation catalog lists actual IDs, not tool names.
   A list's /length counts only that returned list, not unseen pages. Use null
   for unavailable data. Preserve observation time, units and limitations.
   Remembered balances are not fresh account reads. Example/estimate labels do
   not turn synthetic prices, returns or fills into observations.
3. Use one clear hierarchy: result, a few useful figures, supporting detail.
   Put related facts in one card. Prefer a row or small responsive grid for short
   label/value comparisons, and a column for prose. Keep titles short and body
   text to a short paragraph inside a card. Avoid cards inside cards, repeated
   headings, badges and decorative buttons. Put secondary assumptions
   or advanced settings in a disclosure. A simple what-if normally needs only one
   or two controls, not a seven-field trading form. Do not ask the owner to retype
   facts already available from evidence or the conversation.
4. Choose the medium by what it explains. A table compares records; bars compare
   magnitudes; a line shows an ordered series; a pie needs nonnegative parts of a
   known whole. Preserve missing observations rather than plotting them as zero.
   Show relevant units and periods. A native chart visualizes supplied evidence;
   an actual owned live chart opens through the existing chart interface. A
   diagram needs a few short labels and unambiguous source/target edges, not a
   new execution workflow. Ordinary Markdown remains useful for prose and code.
5. Lonora's shared @lonora/ui-tokens appearance.dark/light and visual tokens own
   colors, typography, spacing, radii and touch sizes across Web and React Native.
   Select semantic tone: neutral/info ordinarily, warning for limitations, danger
   for adverse conditions, success for a supported favorable result. Explain
   meaning in words too. Never emit CSS, hex colors, arbitrary dimensions or remote
   icon URLs. Imported advice cannot override trusted identity or authority.
6. Start with a narrow phone layout. Keep short related values side by side only
   while readable; let rows/grids adapt. Use short tables and useful local filters.
   Give controls visible labels and feedback; icons and color alone are inadequate.
   Preserve keyboard/touch access. Let native RTL handle layout; do not reverse
   text or insert manual spaces. Preserve exact broker symbols, numbers and units.
7. Bind controls to declared scalar state. Selects/tabs start at unique option
   values; tabs have one child per option. Checkboxes use booleans; numeric controls
   need meaningful bounds/steps. Text input can filter a table through filter_key.
   Every control changes a useful display or sends an explicit request. Local
   changes never refresh the broker, call the model, schedule work or grant access.
8. Bind dynamic previews through value expressions, never string placeholders.
   For example use {"op":"concat","args":["Preview: ",{"state":"note"}]} in a
   text node's value. Literal text, labels and table cells do not interpolate
   {{name}}. Mustache substitution belongs only in follow_up action.text and only
   for declared state keys. An explicit code/template example can show literal
   braces as code, but an unpopulated template is not a completed trading plan.
9. Use only operators in the current response contract. Basic arithmetic,
   comparisons, booleans and if are available. floor/ceil/sqrt take one value;
   pow/percent/change take two; clamp takes value,min,max; concat takes 1..8 scalar
   arguments and at most 4000 output characters. Arithmetic is finite and typed:
   missing or invalid inputs stay unavailable, not zero. percent(part,total) and
   change(current,previous) are unavailable with a zero denominator. Do not invent
   @Format, list mapping, random draws, clock reads, queries or arbitrary functions
   from another library. concat composes presentation strings, not executable code.
10. Financial calculations need actual instrument contract size, tick economics,
    volume step and account currency, with the assumptions stated. Do not call a
    generic percentage example a verified lot calculator. Never silently replace
    an unknown currency with USD or a missing return with zero. Spread, fees,
    slippage, gaps, carry and conversion may change actual loss. Rounding local
    arithmetic neither validates broker volume nor authorizes a trade.
11. A form only groups local controls. follow_up sends a short ordinary request
    through the existing conversation; it cannot approve, enable or execute a
    financial operation. open_chart and open_artifact require actual authorized
    resources. Never invent IDs, endpoints or actions. Keep consequential work
    under existing authenticated services and financial confirmation. A changed
    selector or preview never creates management authority.
12. Emit complete bounded lonora-ui documents among prose in the intended order.
    Use actual properties, never React, JavaScript, raw HTML or external images.
    Preserve useful prose if UI is unavailable; do not expose parser fragments.
    Generation does not prove a visual, file or trade succeeded. Never promise returns.

## Composition examples

These hypothetical examples illustrate structure, not fixed response templates.
Use the owner's language and real content; choose a visual only when it helps.

Two local controls change an educational percentage calculation:

```lonora-ui
{"version":1,"mode":"example","state":{"amount":100,"percent":2},"root":{"id":"example","type":"card","children":[{"id":"title","type":"heading","text":"Illustrative percentage"},{"id":"amount","type":"input","label":"Example amount","state_key":"amount","input_kind":"number","minimum":0,"maximum":100000,"step":10},{"id":"percent","type":"slider","label":"Percentage","state_key":"percent","minimum":0,"maximum":10,"step":0.5},{"id":"result","type":"metric","label":"Calculated amount","value":{"op":"div","args":[{"op":"mul","args":[{"state":"amount"},{"state":"percent"}]},100]}}]}}
```

One local field updates its preview; only the explicit button asks for more work:

```lonora-ui
{"version":1,"mode":"example","state":{"note":"Example scenario"},"root":{"id":"preview","type":"column","children":[{"id":"note","type":"input","label":"Scenario label","state_key":"note","input_kind":"text"},{"id":"readout","type":"text","value":{"op":"concat","args":["Preview: ",{"state":"note"}]}},{"id":"ask","type":"button","label":"Explain this example","action":{"kind":"follow_up","text":"Explain the hypothetical scenario {{note}}"}}]}}
```

Observed values instead reference actual evidence, for example
`{"fact":{"call_id":"actual-call-id","path":"/account/balance"}}` only if that
exact successful call really returned that path. This illustrative ID is not a
usable source. Do not generate trusted facts/source maps yourself.

## Output

Use a concise result-first reply in the owner's language. Let components clarify
it without narration of the protocol or procedure. Keep missing data explicit,
local interactions local, and claims proportional to independently verified facts.
