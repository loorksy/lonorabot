CODEX ENGINEERING MANDATE

Lonora — Complete Chat Runtime Repair, Streaming UX, Agent State Visibility, and Open Intelligent UI Integration

Target repository: https://github.com/loorksy/lonorabot

Primary reference: https://github.com/thesysdev/open-intelligent-ui

Underlying framework reference: https://github.com/thesysdev/openui

Official OpenUI Agent Skill: https://github.com/thesysdev/skills

Priority: Critical — Existing functionality is deployed but the actual user experience is broken.

Mission: Diagnose, repair, improve, and fully integrate Lonora's existing conversation experience using the best applicable engineering patterns, interaction systems, rendering architecture, streaming behavior, and UI capabilities from Open Intelligent UI and its underlying OpenUI ecosystem.

This is an implementation mandate, not a request for an architectural proposal or a new demonstration application.

---

1. CRITICAL CONTEXT — THE PREVIOUS IMPLEMENTATION FAILED IN PRACTICE

I previously provided a comprehensive specification named "prompt 2.md".

It required implementing:

- Model-native generative UI.
- Autonomous model-controlled presentation decisions.
- Mixed text and visual responses.
- Native interactive components.
- Unified Lonora design identity.
- Agent-controlled visualization.
- A native design Skill.
- Shared Python/TypeScript contracts.
- Web and Android rendering.
- Persistence and streaming.
- Functional interaction handling.

You already implemented substantial portions of this specification.

However, despite reported implementation success, the actual production experience is not functioning correctly.

Do not treat the previous implementation report, successful unit tests, generated screenshots, or documentation as proof that the live user experience is correct.

The implementation must now be verified against real user interactions.

The original "prompt 2.md" remains the product-level functional specification. This mandate adds critical runtime, integration, UX, performance, and reliability requirements.

Do not abandon valid work from the previous implementation. Investigate why it fails in actual use, reuse what works, and repair or replace defective portions.

---

2. CONFIRMED USER-FACING PROBLEMS

The following problems were observed in the actual Lonora chat interface on an Android device using Chrome.

Problem A — Sending a message feels extremely slow

After I submit a message, it can take approximately 10 seconds before the message appears to have been sent or handled correctly.

This is unacceptable for an ordinary conversation.

Investigate whether this delay happens in:

1. The local composer event handler.
2. Frontend state updates.
3. Message outbox enqueueing.
4. API request creation.
5. Network transmission.
6. Authentication or CSRF processing.
7. Message persistence.
8. Run creation.
9. Gateway dispatch.
10. Python Agent scheduling.
11. Model provider connection.
12. Streaming initialization.
13. Message acknowledgement.
14. Frontend event reconciliation.
15. UI rendering.

Do not assume the model is responsible for the delay.

Measure each stage separately and identify the actual bottleneck.

A user message must become visible immediately through optimistic rendering, without waiting for the language model to answer.

Problem B — Submitted messages remain in the composer

After sending a message, the message sometimes appears in the conversation while its original text remains inside the typing field.

This creates an incorrect and confusing experience.

Fix the complete composer lifecycle.

Expected behavior:

- The user types a message.
- The user presses Send.
- The outgoing message appears immediately.
- The composer clears immediately once the message is safely placed in the local sending outbox.
- The composer returns to its normal ready state.
- The message is acknowledged by the backend.
- The assistant begins its work.
- The response appears progressively.

If local enqueueing fails, preserve the user's draft.

If network submission fails after enqueueing, retain the message as a failed outgoing message with a Retry action.

Do not create duplicate messages.

Do not silently discard submitted text.

Do not leave already-submitted text inside the composer.

Problem C — Agent status is missing

When I send a message, I cannot reliably see what the Agent is doing.

There is no clear, continuous visual indication of its execution state.

I need visible Agent activity from the beginning of a turn until its completion.

Examples of meaningful states:

- Sending
- Queued
- Connecting
- Preparing
- Thinking
- Retrieving context
- Searching
- Using tools
- Analyzing
- Generating a response
- Streaming
- Waiting for external results
- Waiting for user input
- Completed
- Interrupted
- Failed
- Cancelled
- Reconnecting

These are examples, not permission to fabricate states.

The interface must display states according to actual runtime information.

Do not simulate reasoning or pretend that a tool is running when it is not.

Do not display hidden chain-of-thought content.

A compact activity indicator may remain visible while a turn is running, with expandable details for genuine tool and task events.

Problem D — Streaming is not experienced as real streaming

The conversation currently feels delayed and disconnected.

Investigate whether:

- The Python Agent emits tokens incrementally.
- Tokens are buffered unnecessarily.
- Gateway events are delayed.
- The API buffers SSE responses.
- Reverse proxies buffer responses.
- Frontend state updates happen only at completion.
- React components block progressive rendering.
- Structured UI parsing delays normal prose.
- Database writes prevent stream publication.
- The user sees nothing until the entire response is complete.

The message must visibly develop as content becomes available.

Streaming must include both ordinary text and generated UI, with appropriate validation boundaries.

Problem E — Raw technical syntax appears in assistant messages

Some responses display programming-like symbols or generated UI syntax at the end of the message.

Other content exposes unresolved variables such as:

"{{symbol}}", "{{timeframe}}", "{{direction}}", "{{entry}}", "{{sl}}", "{{tp1}}", and "{{tp2}}".

Investigate all serialization, templating, compilation, parser, Markdown, rich-content, and rendering paths.

Do not attempt to solve this through cosmetic CSS hiding or broad string replacement.

The user must never see internal UI instructions, parser fragments, incomplete structured documents, or unresolved application template markers presented as finished content.

Legitimate code requested by the user must continue to display normally.

Problem F — Interactive components are excessively large

Generated UI components occupy too much vertical space.

Their proportions, layout composition, spacing, typography, and information density are not professional.

Some interfaces resemble oversized forms rather than intelligent conversational responses.

The result must become:

- Compact.
- Modern.
- Context-aware.
- Information-dense when appropriate.
- Comfortable to read.
- Elegant on mobile.
- Consistent with Lonora's visual identity.
- Appropriately sized for conversational messages.

A simple answer must not produce a giant interface.

Complex answers can use progressive disclosure rather than forcing all controls to remain visible.

Problem G — Interactive elements are unreliable

Audit the behavior of all generated controls.

Check:

- Buttons.
- Forms.
- Inputs.
- Selectors.
- Sliders.
- Checkboxes.
- Tabs.
- Expandable sections.
- Tables.
- Charts.
- Calculators.
- Interactive diagrams.
- Actions.
- State transitions.
- Linked resources.

Controls must work, not merely look interactive.

---

3. FUNDAMENTAL OBJECTIVE

Lonora must provide a fluid AI conversation comparable in interaction quality to a modern intelligent chat interface.

The intended experience is:

One conversation, one Agent, immediate user feedback, visible execution activity, progressively streamed output, and professionally rendered native interactive responses.

The existing Lonora Agent must remain the decision-maker.

The existing backend, Gateway, task execution architecture, authentication, memory, tools, trading services, and persistent conversation storage must remain authoritative.

Do not introduce an unnecessary second conversation engine or a separate UI-generation Agent.

---

4. MANDATORY REFERENCE STUDY

Before implementing changes, inspect the actual source code of:

https://github.com/thesysdev/open-intelligent-ui

Also study:

https://github.com/thesysdev/openui

Do not rely exclusively on the README or screenshots.

Inspect the current source and understand how the reference system works end to end.

4.1 Open Intelligent UI — Required files and systems

Study at minimum:

"src/app/page.tsx"

Understand:

- How AgentInterface is initialized.
- How the component library is connected.
- How chat messages are represented.
- How the model transport is configured.
- How the chat shell is composed.

"src/app/api/chat/route.ts"

Understand:

- Request handling.
- Conversation forwarding.
- Model streaming.
- Response-event conversion.
- Provider compatibility.
- Error propagation.
- Stream completion.

"src/app/shell.css"

Understand:

- Chat layout.
- Message spacing.
- Composer styling.
- Mobile responsiveness.
- Message content width.
- Scroll behavior.
- Compact visual composition.

"src/lib/response-theme.ts"

Understand:

- Chat theme tokens.
- Message styling.
- Conversation visual consistency.
- Assistant/user message differentiation.

"src/lib/chat-storage.tsx"

Understand:

- Thread identity.
- Message storage.
- Message restoration.
- Interactive state retention.

Study these patterns, but do not replace Lonora's server-side conversation persistence with browser localStorage.

"src/lib/library.ts"

Understand:

- Model-facing component declarations.
- Component organization.
- Reusable visual primitives.
- Model-controlled composition.

"src/lib/prompt-options.ts"

Understand:

- Instructions for model-generated interfaces.
- Worked component examples.
- Practical design guidance.
- Guidance for generating working interactions.
- Response composition rules.

"src/lib/components/"

Inspect the complete component implementation, including relevant modules for:

- Layout.
- Typography.
- Forms.
- Controls.
- Tables.
- Charts.
- Maps.
- Media.
- SVG.
- Markdown.
- Code and mathematics.
- Theme and component styling.

"src/lib/functions/"

Inspect the actual function library and determine which safe declarative operations can improve Lonora.

"src/lib/actions.ts"

Understand the action mechanism and its relationship with rendered controls.

"src/generated/"

Understand how the component specification and system instructions remain synchronized.

"src/app/gallery/"

Inspect real working examples and component demonstrations.

"scripts/bench/"

Understand reference benchmark coverage and how generated UI output is validated.

"AGENTS.md"

Follow its link to the maintained OpenUI Agent Skill.

4.2 Study the actual OpenUI framework

Investigate the applicable packages:

- "@openuidev/lang-core"
- "@openuidev/react-lang"
- "@openuidev/react-headless"
- "@openuidev/react-ui"
- "@openuidev/server"
- "@openuidev/devtools"

Also inspect adapters and package-level facilities relevant to:

- Streaming.
- Parsing.
- Component evaluation.
- State management.
- Conversation management.
- Message reconciliation.
- Renderer lifecycle.
- Error recovery.
- Cancellation.
- Transport adaptation.
- Observability.
- Testing.

Do not install every package automatically.

Identify which capabilities can be directly integrated, which need adaptation, and which should remain implemented by Lonora's existing systems.

4.3 Required integration evaluation

For every relevant subsystem, classify it as:

1. Directly reusable.
2. Reusable through an adapter.
3. Useful as an architectural reference.
4. Already implemented correctly in Lonora.
5. Not suitable for Lonora.

Make this evaluation based on actual source inspection.

The goal is to obtain the benefits of Open Intelligent UI without creating redundant systems.

---

5. PRESERVE THE PYTHON BACKEND

Lonora uses Python for its actual backend and Agent runtime, while its frontend includes TypeScript/React and a React Native/Expo application.

Open Intelligent UI uses a TypeScript/React/Next.js implementation.

This language difference must not be treated as an obstacle.

It also does not justify rewriting Lonora's Python backend into TypeScript.

Use a clean integration boundary:

Python Agent → Python Gateway/API → Versioned Stream Events → TypeScript Chat Client → Native Component Renderer

Preserve:

- Python Agent orchestration.
- Tool execution.
- Agent reasoning and runtime lifecycle.
- Persistent tasks.
- Subagents.
- Model providers.
- Gateway.
- Existing database.
- Conversation history.
- Broker integrations.
- Financial authorization.
- Trading execution services.

Use TypeScript where appropriate for the frontend, renderers, client state machines, and shared client-side interaction logic.

Python and TypeScript must agree on contracts through versioned schemas and tests.

Do not add a second backend merely to run the reference demo.

Do not require Next.js.

Do not route all Lonora conversations through an external Thesys service unless such an architectural change is separately justified and explicitly authorized.

The existing configured model providers must continue working.

---

6. COMPLETE CHAT PIPELINE AUDIT

Trace the actual message lifecycle across the entire application.

Audit:

1. User input.
2. Composer state.
3. Local message creation.
4. Optimistic UI insertion.
5. Message submission.
6. Client request identification.
7. Server acknowledgement.
8. Persistent message storage.
9. Run creation.
10. Task scheduling.
11. Gateway execution.
12. Agent initialization.
13. Tool activity.
14. Model inference.
15. Token streaming.
16. UI compilation and validation.
17. Rich-content publication.
18. Stream reconciliation.
19. Completion.
20. Message persistence.
21. Reload and recovery.

Determine exactly where delays, state inconsistencies, duplicated messages, or missing status transitions occur.

Inspect both the existing implementation and the deployed behavior.

The frontend and backend must agree on message identity and lifecycle.

---

7. REBUILD THE MESSAGE SUBMISSION EXPERIENCE

Create or repair a reliable message submission state machine.

A useful conceptual flow is:

"draft → locally_queued → submitting → acknowledged → agent_running → completed"

With explicit failure and cancellation paths.

This is a behavioral model, not necessarily the exact wire protocol.

Required behavior

Immediate optimistic rendering

A locally submitted message appears without waiting for the server or model.

Stable identifiers

Use stable client-generated request identifiers and canonical server message identifiers.

Reconcile them correctly.

Exactly-once visible semantics

Retries, reconnections, and repeated server events must not create duplicate visible messages.

Backend processing must use appropriate idempotency guarantees.

Correct draft lifecycle

Clear the submitted draft after successful local enqueueing.

Do not clear unsent text.

Restore or preserve recoverable content when submission fails.

Attachment handling

The composer must correctly distinguish:

- Pending uploads.
- Uploaded attachments.
- Failed uploads.
- Text-only messages.
- Multimodal messages.

Do not silently lose attachments.

Reliable sending behavior

Check:

- Enter to send.
- Shift+Enter for newline.
- Mobile keyboard behavior.
- IME composition.
- Send-button disabled states.
- Duplicate taps.
- Network interruption.
- Concurrent requests.
- Steering during an active Agent run.
- Message submission after switching conversations.

Preserve the intended existing steering and interruption behavior.

---

8. REAL-TIME AGENT STATUS SYSTEM

Implement visible execution status based on genuine Agent events.

Inspect Lonora's existing Run, Task, Gateway, SSE, and activity-event contracts.

Reuse those mechanisms.

8.1 Compact activity indicator

While the Agent is active, display a compact status near its current response.

The status should communicate the current execution phase.

Examples:

"Thinking..."

"Searching market data..."

"Reading account information..."

"Running an analysis..."

"Generating response..."

"Waiting for a tool..."

These labels must be backed by actual events.

8.2 Expandable activity details

When genuine execution information is available, allow the user to expand the status area.

It may show:

- Current task.
- Tool names.
- Relevant tool execution states.
- Completed steps.
- Waiting operations.
- Errors.
- Subagent activity.
- Actual execution timestamps.

Do not expose private internal reasoning.

Do not show meaningless technical logs to ordinary users by default.

8.3 Agent state transitions

Handle transitions consistently:

Queued → Running → Tool execution → Response generation → Streaming → Complete.

Support legitimate alternate paths:

- Running → Waiting for user input.
- Running → Failed.
- Running → Cancelled.
- Running → Interrupted.
- Connection lost → Reconnecting → Resumed.

Do not incorrectly mark a run as completed merely because one tool finished.

8.4 Long-running work

Lonora is a persistent Agent system.

It may perform long-running trading monitoring, multi-tool analysis, background tasks, and subagent coordination.

The UI must distinguish:

- The current conversational response.
- A persistent Agent task.
- A background monitoring process.
- A delegated subagent operation.

Use actual task identities instead of presenting unrelated activity as part of the current turn.

---

9. TRUE END-TO-END STREAMING

Study Open Intelligent UI's model-stream integration and the underlying OpenUI streaming renderer.

Implement equivalent user-facing streaming quality using Lonora's existing transport.

Required support

- Incremental text rendering.
- Mixed text/UI responses.
- Typed stream events.
- Actual Agent state updates.
- Tool lifecycle events.
- Incrementally received content.
- Validated component delivery.
- Stream completion.
- Cancellation.
- Reconnection.
- Resume.
- Error recovery.
- Deterministic event ordering.

9.1 Distinguish the important timings

Measure:

- User interaction to local message visibility.
- User interaction to server acknowledgement.
- Request acceptance to Agent start.
- Agent start to model request.
- Model request to first provider output.
- First provider output to first client-visible content.
- Time between consecutive visible updates.
- Time to first UI component.
- Total response duration.

Do not combine all of these into a single misleading latency number.

9.2 Investigate buffering

Check all buffering boundaries:

- Python async generators.
- Provider SDKs.
- Gateway queues.
- SSE adapters.
- FastAPI response delivery.
- Reverse proxies.
- Compression middleware.
- API gateways.
- Browser stream readers.
- Component compilation.
- React state batching.
- Rendering and Markdown processing.

If any layer waits for full completion before updating the conversation, determine whether that delay is necessary.

9.3 Stream text naturally

Plain text should appear progressively.

Do not wait for rich UI validation before displaying independent, valid prose.

9.4 Stream structured UI safely

Never render unsafe or invalid partial structures.

A component may become visible after enough validated structure exists to render it safely.

Choose an appropriate strategy based on the selected renderer and validated protocol.

Do not withhold the entire response merely because one later UI component is incomplete.

9.5 Stream reconciliation

The final persisted message must accurately represent the streamed response.

There must be no:

- Duplicate text.
- Missing chunks.
- Changed content ordering.
- Repeated components.
- Blank response replacement.
- Broken component references.
- Raw parser fragments.

---

10. FIX MODEL OUTPUT PARSING AND INTERNAL SYNTAX LEAKAGE

This is a critical requirement.

Lonora's existing implementation uses model-generated structured visual output.

Inspect the complete compiler/renderer boundary.

Investigate whether the current fenced-JSON approach creates avoidable latency, ambiguous parsing, or malformed-message leakage.

Study OpenUI Lang and its streaming-first parsing approach as a potential improvement.

However, do not replace a working contract solely because another syntax is more fashionable.

Evaluate actual tradeoffs:

- Token efficiency.
- Model generation reliability.
- Incremental parseability.
- Schema validation.
- Error recovery.
- Python compatibility.
- Browser rendering.
- React Native compatibility.
- Existing message migration.
- Provider support.
- Security.
- Maintenance cost.

If necessary, improve or replace the current visual serialization layer through a backward-compatible, versioned migration.

Mandatory parser behavior

1. Keep internal structured UI instructions separate from user-visible prose.
2. Validate component types and properties.
3. Preserve legitimate requested code blocks.
4. Handle incomplete streaming documents.
5. Handle malformed component structures.
6. Handle unknown components.
7. Handle invalid properties.
8. Handle broken references.
9. Handle interrupted streams.
10. Handle mixed Markdown and structured content.
11. Avoid printing raw protocol text.
12. Fall back to useful readable text when possible.

Unresolved placeholder protection

A response must not present raw placeholders such as "{{symbol}}" as completed, populated trading information.

Trace where these originate:

- Prompt templates.
- Tool outputs.
- UI component examples.
- Model responses.
- Dynamic preview logic.
- Component state.
- Rendering.

Resolve values only from appropriate actual data or explicitly mark the content as an unpopulated example.

Never fabricate missing account or market values.

Do not strip legitimate literal braces from code examples.

---

11. ADOPT OPEN INTELLIGENT UI'S COMPOSITION MODEL

The core advantage of Open Intelligent UI is that the language model composes responses using general-purpose visual primitives.

Lonora should preserve and strengthen this capability.

The model must autonomously choose whether to respond with:

- Plain text.
- Structured prose.
- A compact visual element.
- Several visual elements.
- A chart.
- An interactive control.
- A diagram.
- A combination of text and UI.

Do not force every answer into a visual template.

Do not add a separate presentation-classification Agent.

Do not use a keyword-to-template router as the main presentation mechanism.

The existing Lonora Agent must remain the owner of response composition.

Important distinction

A simple message like:

"طيب ماهي قدراتك"

should generally receive a natural, readable conversational answer unless the Agent has a genuinely useful reason to add an interface.

It should not automatically produce an oversized interactive form.

---

12. AUDIT AND EXPAND THE COMPONENT LIBRARY

Compare Lonora's current component registry against the relevant reusable capabilities in Open Intelligent UI.

The reference supports a broad component vocabulary.

Audit each category and implement missing or defective capabilities where they materially improve Lonora.

12.1 Layout primitives

Study:

- Column.
- Row.
- Box.
- Grid.
- Card.
- Carousel.
- Popover.
- Divider.
- Spacer.
- Flexible containers.
- Nested layouts.

Ensure the model can combine them without hardcoded response templates.

12.2 Text primitives

Study:

- Title.
- Text.
- Caption.
- Label.
- Badge.
- Link.
- Markdown.
- Lists.
- Inline formatting.
- Quotes.
- Code blocks.
- Mathematical expressions.

Support correct composition of text with embedded UI elements.

12.3 Input components

Study:

- Button.
- IconButton.
- Pressable.
- Input.
- TextArea.
- Select.
- SegmentedControl.
- Slider.
- Checkbox.
- RadioGroup.
- DatePicker.
- Timer.
- Form.

Every supported interactive element must have correct behavior and accessible feedback.

12.4 Data presentation

Study:

- Tables.
- Sortable and filterable data.
- Charts.
- Numeric metrics.
- Progress indicators.
- Timelines.
- Comparative displays.
- Trend visualization.
- Responsive data layouts.

Investigate the applicability of:

- Bar charts.
- Line charts.
- Area charts.
- Pie charts.
- Donut charts.
- Scatter plots.

Preserve specialized existing trading-chart infrastructure.

Do not replace live market charting with a generic static chart.

12.5 Media and advanced visualizations

Evaluate:

- Images.
- Image search.
- Maps.
- Map markers.
- Video embeds.
- SVG composition.
- Interactive diagrams.
- Flowcharts.
- Flashcards.
- Lightweight animated feedback.

Not every reference component is necessary for trading.

Adopt capabilities selectively.

Remote search, map routing, and third-party content should not introduce unnecessary external dependencies or privacy risks.

12.6 Domain-specific financial primitives

Where useful, extend general primitives with safe, reusable financial capabilities:

- Price formatting.
- Currency formatting.
- Percentage changes.
- Position summaries.
- Risk/reward displays.
- Exposure metrics.
- Instrument metadata.
- Multi-timeframe comparisons.
- Trade journals.
- Account performance.
- Drawdown visualizations.
- Position sizing education.
- Market session timelines.
- Trade execution receipts.

These must be composable components, not a rigid template for each possible user question.

All real trading information must remain grounded in authenticated tools.

---

13. IMPROVE LOCAL INTERACTION AND DECLARATIVE COMPUTATION

Open Intelligent UI demonstrates reactive local variables, actions, and reusable functions.

Study its mechanisms for:

- State variables.
- Reactive expressions.
- Conditional rendering.
- List mapping.
- State transitions.
- Local calculations.
- Actions.
- Derived values.

Audit the 59 generic functions documented by the reference and inspect their real implementations.

Consider applicable operations from the following groups.

Lists

Append, Remove, Update, Toggle, Includes, Range, Chunk, Group, Sort, Filter, and related operations.

Numeric calculations

Pow, Clamp, Percent, Allocate, Payment, Convert, and applicable arithmetic operations.

Text

Format, Join, Split, Replace, Capitalize, Plural, Duration, and Default.

Dates and time

Today, FormatDate, AddDays, AddMonths, DaysBetween, MonthsBetween, and StartOf.

Data analysis

GroupBy, Pivot, Top, Between, Bucket, Cumulative, MovingAvg, Change, Histogram, and Stats.

Only enable functions with well-defined types, bounded execution, and safe deterministic behavior where required.

Do not blindly copy the function library.

Local interactions must remain local

Examples:

- Changing a slider updates a calculation.
- Selecting a timeframe changes the displayed local comparison.
- Expanding a section reveals additional information.
- Switching tabs changes the visible content.
- Checking an option updates derived values.

These operations must not unnecessarily call the LLM or Python Agent.

Backend actions

When interaction genuinely requires the Agent or a server-side tool, dispatch an authorized typed action through Lonora's existing services.

Do not let model-generated UI invoke arbitrary endpoints.

Financial actions must preserve existing server-side authorization and broker-specific controls.

---

14. REWORK THE GENERATED UI DESIGN SYSTEM

The generated elements currently lack professional visual density.

Study Open Intelligent UI's:

- Component styles.
- Layout spacing.
- Typography.
- Theme variables.
- Cards.
- Input styling.
- Responsive behavior.
- Message embedding.
- Control proportions.

Adapt relevant patterns to Lonora's visual identity.

Do not blindly replace Lonora's colors or visual branding.

Core design requirements

Compact presentation

Use sensible defaults for:

- Padding.
- Vertical spacing.
- Control height.
- Text sizes.
- Card radius.
- Section gaps.
- Icon sizes.
- Border treatment.
- Information hierarchy.

Avoid oversized forms

An educational example containing several fields should not occupy multiple phone screens unnecessarily.

Use:

- Compact rows.
- Appropriate grouping.
- Expandable advanced options.
- Contextual disclosures.
- Responsive grids.
- Progressive detail.

Avoid excessive nesting

Do not generate deeply nested cards inside cards without a clear visual purpose.

Avoid excessive UI generation

Encourage concise layouts with the minimum components needed to communicate useful information.

Preserve visual variety

Do not force all responses into the same layout.

The Agent must be able to compose different structures from the same primitives.

Unified design tokens

Use centralized semantic values for:

- Color.
- Typography.
- Spacing.
- Borders.
- Shadows.
- Motion.
- Interaction states.
- Responsive breakpoints.

Arabic and English

Ensure proper:

- RTL layouts.
- LTR content.
- Numeric isolation.
- Currency presentation.
- Trading symbol formatting.
- Decimal formatting.
- Text wrapping.
- Mixed Arabic/English content.

Accessibility

Include:

- Keyboard access.
- Visible focus states.
- Screen-reader labels.
- Appropriate contrast.
- Touch-friendly controls.
- Reduced-motion support.

A sophisticated interface must remain usable on narrow mobile screens.

---

15. IMPROVE THE CHAT SHELL AND COMPOSER

Study the reference chat interface and adapt useful behavior without replacing Lonora's product architecture.

Focus on:

- Message grouping.
- User message alignment.
- Assistant response layout.
- Response content width.
- Message spacing.
- Composer behavior.
- Active-run indication.
- Floating composer layout.
- Attachment controls.
- Keyboard interactions.
- Scroll handling.
- Tool activity presentation.
- Error states.
- Retry actions.

Composer requirements

- Immediate Send feedback.
- Correct draft clearing.
- Correct text selection behavior.
- Stable composer height.
- Mobile keyboard responsiveness.
- Reliable send button.
- Support for attachments.
- Cancellation controls.
- No delayed clearing.
- No duplicated outgoing text.
- Proper disabled/loading states.
- Preserved unsent drafts when appropriate.

Scroll behavior

The conversation must:

- Follow new content when the user is near the bottom.
- Preserve manual scroll position when reading older messages.
- Avoid forced jumps during streaming.
- Avoid layout jumps when interactive elements appear.
- Restore a sensible scroll position after reopening a thread.
- Keep the composer accessible when the mobile keyboard opens.
- Preserve usable layout when charts or tables expand.

Study OpenUI's scroll-follow behavior and adapt it to Lonora's current conversation components.

---

16. WEB AND ANDROID CONSISTENCY

The actual reported problem was observed on Android Chrome.

Therefore, mobile browser behavior is a mandatory acceptance target.

Also validate the actual React Native/Expo implementation.

Use shared contracts and evaluation logic wherever possible.

Test the following

- Android Chrome.
- Narrow Android viewport.
- Mobile keyboard open and closed.
- Arabic RTL.
- English LTR.
- Light mode.
- Dark mode.
- Long messages.
- Streaming responses.
- Interactive cards.
- Table overflow.
- Chart rendering.
- Input state restoration.
- Cancellation.
- Reconnection.
- Conversation switching.

Web and Native may use different rendering implementations, but they must produce functionally equivalent experiences.

Do not assume Expo Web proves that a signed Android application works.

Verify native behavior through an appropriate device or emulator when available.

Do not claim physical-device verification without actually performing it.

---

17. PERSISTENCE, MESSAGE RECONCILIATION, AND RECOVERY

Study the thread management patterns from Open Intelligent UI.

However, preserve Lonora's server-side conversation persistence.

The canonical source of truth must remain Lonora's authenticated backend.

Requirements

Messages and visual components must survive:

- Page reload.
- Browser restart.
- Conversation switching.
- Mobile app restart.
- Network interruption.
- Gateway restart.
- Agent task continuation.
- Stream reconnection.

Maintain:

- Stable message IDs.
- Stable component identities.
- Ordered content parts.
- Versioned UI contracts.
- Correct optimistic-message reconciliation.
- Correct interaction state scope.
- Authorized resource references.

Avoid storing the same canonical conversation independently in incompatible client systems.

Local UI state can be persisted where appropriate, but it must not become a second authoritative conversation database.

---

18. IMPROVE MODEL-FACING UI INSTRUCTIONS

Audit Lonora's current native visual response prompt.

Compare it against the reference project's:

"src/lib/prompt-options.ts"

"src/generated/system-prompt.txt"

"src/lib/library.ts"

Study how OpenUI derives model-facing instructions from actual registered components.

Required improvements

1. Keep prompt instructions consistent with the real component registry.
2. Ensure the model knows valid component types.
3. Document supported properties.
4. Document valid interactions.
5. Provide correct compact examples.
6. Avoid ambiguous component instructions.
7. Avoid contradictory formatting rules.
8. Avoid requiring visual output on every turn.
9. Prevent example values from appearing as real account facts.
10. Reduce unnecessary prompt overhead.
11. Support configured model-provider differences.
12. Test actual generation reliability.

Do not solve all rendering defects by adding an enormous system prompt.

A model-facing contract should be compact, clear, and consistent with its runtime.

If the component schema changes, ensure its documentation and generated prompt specification are updated together.

---

19. INVESTIGATE THE OFFICIAL OPENUI SKILL

Study the maintained Skill:

https://github.com/thesysdev/skills

Specifically inspect the "openui" Skill and its relevant reference files.

Read guidance concerning:

- Existing application integration.
- Agent Interface.
- Component library design.
- The OpenUI language.
- Streaming adapters.
- Reliability.
- Rendering.
- Theming.
- Artifact integration.
- Backend compatibility.
- Debugging malformed model output.

Integration strategy

Determine whether the official Skill should be:

- Used as a development Skill by Codex.
- Referenced as implementation knowledge.
- Adapted into Lonora's existing Design Skill.
- Partially reused for model-facing UI guidance.

Distinguish clearly between a coding-agent Skill and a runtime Skill available to Lonora's trading Agent.

Do not install developer-oriented instructions as trading-agent capabilities without adaptation.

Lonora Design Skill

Improve the existing "lonora-design" Skill using applicable reference knowledge.

It should teach the Agent:

- Professional visual composition.
- Compact conversational interfaces.
- Information hierarchy.
- Responsive layout design.
- Interactive response composition.
- Correct component selection.
- Accessible design.
- Arabic RTL design.
- Trading-data visualization.
- Minimal UI complexity.
- Proper progressive disclosure.
- Valid interaction patterns.

It must reference Lonora's real component vocabulary and centralized design tokens.

Do not require loading a large Skill for every simple response.

Do not add another Agent to control presentation.

---

20. RELIABILITY, SECURITY, AND FINANCIAL CORRECTNESS

All generated UI must remain bounded and trusted.

Required defenses

- Schema validation.
- Unknown component rejection.
- Invalid property rejection.
- Bounded component trees.
- Bounded expression evaluation.
- Safe URLs.
- Resource authorization.
- No arbitrary executable JavaScript.
- No arbitrary browser API access.
- No direct privileged operations from generated markup.
- Protection against hostile generated content.
- Correct ownership checks.
- Safe cancellation and retries.
- Idempotent backend operations.

Financial requirements

Do not fabricate:

- Balances.
- Prices.
- Equity.
- Profits.
- Losses.
- Positions.
- Orders.
- Broker confirmations.
- Backtest performance.

Observed values must originate from authorized tools.

Hypothetical examples must be identified as examples.

Financial calculators must use correct instrument specifications and assumptions.

Keep trade authorization, emergency-stop behavior, broker execution, and risk enforcement under existing Python backend services.

Rendering a trading control does not grant additional trading authority.

---

21. PERFORMANCE ENGINEERING

Performance must be measured, not guessed.

Add or improve development instrumentation across the critical conversation path.

Required measurements

- Composer submit-to-render latency.
- Submit-to-server acknowledgement latency.
- Gateway queue delay.
- Agent initialization time.
- Provider time to first token.
- Server-to-client stream forwarding delay.
- First visible assistant update.
- Rich-component validation delay.
- Frontend rendering time.
- Total turn completion time.
- Reconnection recovery time.

Collect correlated timings for one request across the client, API, Gateway, and Agent.

Do not expose secrets or sensitive model context in logs.

Performance objectives

The implementation should aim for:

- Immediate local message visibility, typically within the next UI frame.
- No artificial waiting for model completion before a user message appears.
- Immediate acknowledgement that the Agent is working.
- Progressive text presentation when text becomes available.
- Prompt rendering of independently validated UI components.
- Smooth mobile scrolling.
- No unnecessary second model call for UI presentation.
- No mandatory screenshot loop.
- No unnecessary heavyweight per-turn design prompt.
- No redundant backend round trips for local interactions.

Actual provider inference may still take time.

Do not promise a fixed model-response duration.

The interface must remain responsive and accurately communicate progress regardless of model latency.

---

22. MANDATORY ROOT-CAUSE INVESTIGATION

Before applying fixes, investigate the exact causes of the observed failures.

At minimum, inspect:

- The existing visual response compiler.
- Python response generation.
- Prompt assembly.
- Provider streaming adapters.
- Gateway streaming.
- API event transport.
- Frontend event handling.
- Web composer.
- Web transcript.
- Message rendering.
- Native message renderer.
- Client outbox.
- Agent status projection.
- Shared contracts.
- Generated UI state evaluator.
- Message persistence.
- Production asset/version alignment.

Use current real repository paths rather than assuming historical paths still exist.

Known areas worth checking include:

- "apps/api/"
- "apps/web/"
- "apps/mobile/"
- "packages/agent-runtime/"
- "packages/contracts/"
- "packages/core/"
- "packages/ui-web/"
- "packages/ui-tokens/"
- "packages/db/"
- "apps/web/src/pages/Shell.tsx"
- "apps/web/src/pages/shell/message-cards.tsx"
- "apps/mobile/components/message-bubble.tsx"
- "docs/native-visual-responses.md"
- "docs/native-visual-acceptance.md"

Find the real implementation files and execution paths.

Investigate whether production currently serves the expected API revision, database schema, frontend bundle, and Android update.

Do not confuse stale assets or a deployment mismatch with an application architecture defect.

---

23. IMPLEMENTATION EXECUTION ORDER

Execute the work in the following practical sequence.

Phase 1 — Full investigation

Reproduce the reported problems.

Trace the complete message and response lifecycle.

Study the Open Intelligent UI reference and relevant OpenUI framework implementation.

Identify actual causes.

Phase 2 — Message submission repair

Fix optimistic rendering, composer clearing, submission state, acknowledgements, retries, and deduplication.

Phase 3 — Agent status visibility

Repair the projection and rendering of real Agent execution events.

Phase 4 — Streaming repair

Fix the entire streaming pipeline, including buffering, event handling, incremental display, and reconciliation.

Phase 5 — Generated UI reliability

Repair structured-output parsing, invalid-content handling, fallback behavior, and hidden syntax leakage.

Phase 6 — Interactive component behavior

Fix existing controls and improve local state/action execution.

Phase 7 — Reference capability integration

Integrate the applicable reusable patterns and components from Open Intelligent UI.

Avoid unnecessary dependencies or duplicate architecture.

Phase 8 — Visual design refinement

Improve layout density, mobile proportions, cards, typography, forms, and conversation composition.

Phase 9 — Model instruction and Skill refinement

Synchronize schemas, component guidance, examples, and the Lonora Design Skill.

Phase 10 — Full regression testing

Test real frontend/backend integration, streaming, persistence, security, and platform compatibility.

Phase 11 — Production verification

Verify the actual deployed experience using the existing project delivery process.

Do not declare completion based only on unit tests or local mock components.

---

24. MANDATORY END-TO-END ACCEPTANCE SCENARIOS

Automated tests are necessary, but actual user-facing behavior must also be exercised.

Scenario A — Simple message

Send:

"Hello"

Expected:

- User message appears immediately.
- Composer clears.
- Agent status appears promptly.
- The actual response streams.
- No UI syntax appears.
- No duplicate messages occur.
- The final message persists.

Scenario B — Arabic conversational question

Send:

"طيب ماهي قدراتك"

Expected:

- Correct Arabic RTL rendering.
- Immediate message submission.
- Clear Agent working status.
- Natural assistant answer.
- No unnecessary giant form.
- No raw protocol syntax.
- No unresolved placeholders.

Scenario C — Long-running analysis

Ask the Agent to perform a multi-step task using actual available tools.

Expected:

- Real activity transitions.
- Relevant tool states.
- Continuous UI responsiveness.
- Correct final response.
- No fake tool progress.
- No loss of activity during reconnection.

Scenario D — Mixed content

Generate a response containing:

- Introductory text.
- Metrics.
- A table or chart.
- Explanatory text.
- An expandable section.

Expected:

- Correct ordering.
- Compact presentation.
- Correct streaming.
- Working interactions.
- Correct final persistence.

Scenario E — Interactive calculation

Generate an educational calculator.

Expected:

- Inputs are functional.
- Changing values updates calculations immediately.
- No unnecessary model request.
- No trade execution.
- Correct assumptions and number formatting.

Scenario F — Malformed generated UI

Force representative malformed outputs.

Expected:

- No raw parser syntax leaks.
- Normal conversation remains usable.
- Valid content is preserved where possible.
- Clear fallback behavior.
- Errors are observable for developers.

Scenario G — Unresolved placeholders

Test a response involving trading symbols, timeframes, entries, stop losses, and targets.

Expected:

- Real values are populated only from valid sources.
- Missing data is identified.
- Example templates are never misrepresented as actual recommendations.
- Raw template variables are not presented as finished market data.

Scenario H — Slow model

Introduce controlled model-response delay.

Expected:

- User message still appears immediately.
- Composer is cleared appropriately.
- Actual Agent status remains visible.
- The UI stays responsive.
- Text begins streaming when provider data is available.

Scenario I — Network interruption

Interrupt a response and reconnect.

Expected:

- Stable message identity.
- Correct recovery.
- No duplicate output.
- No repeated privileged action.
- Reasonable error/retry behavior.

Scenario J — Android browser

Repeat scenarios on Android Chrome or an equivalent authentic mobile browser environment.

Expected:

- Correct keyboard behavior.
- No broken composer.
- No abnormal horizontal overflow.
- No giant fixed-width interfaces.
- Working touch controls.
- Correct RTL text.
- Smooth scroll-follow behavior.

Scenario K — React Native

Verify functionally equivalent behavior on the supported native application.

If device-level testing is unavailable, state that limitation explicitly.

Scenario L — Real model integration

Run actual configured-model conversations through Lonora's real Agent and backend.

Do not accept only manually constructed component fixtures.

The final acceptance must exercise the real model-to-transport-to-renderer path.

---

25. BENCHMARKS AND REGRESSION PROTECTION

Build a representative test suite using actual reference-inspired scenarios.

Include:

- Short replies.
- Long replies.
- Arabic.
- English.
- Mixed RTL/LTR.
- Tool-using requests.
- Chart responses.
- Interactive calculations.
- Forms.
- Multi-section responses.
- Interrupted streams.
- Corrupted UI documents.
- Reconnection.
- Duplicate events.
- Slow provider responses.
- Mobile viewport stress tests.

Measure:

- Rendering failures.
- Parser failures.
- UI component failures.
- Interaction failures.
- Duplicate message rate.
- Composer-state errors.
- Time to visible user message.
- Time to first actual Agent activity.
- Time to first streamed output.
- UI overflow.
- Unexpected backend calls from local interactions.

Repeat representative model-generation tests because one successful response is insufficient to demonstrate reliability.

Use reference benchmarks where applicable, adapted to Lonora's real component contract and products.

---

26. OBSERVABILITY AND DEBUGGING

Study OpenUI's development tools and reliability patterns.

Implement appropriate diagnostics compatible with Lonora.

Developers should be able to determine:

- Which component failed to parse.
- Which schema property was invalid.
- Which stream event was lost.
- Which rendering stage failed.
- Which message could not reconcile.
- Whether a UI structure was incomplete.
- Whether a provider returned malformed output.
- Whether the model produced an unsupported function.
- Whether an interaction incorrectly called the backend.

When appropriate, implement a development-only replay mechanism for captured, sanitized failed responses.

Do not expose internal debug output in the ordinary production conversation.

Do not send sensitive data to third-party observability systems without authorization.

---

27. NON-NEGOTIABLE ARCHITECTURAL RULES

1. Do not replace Lonora's Python Agent.
2. Do not create a second Agent for presentation.
3. Do not duplicate the Gateway.
4. Do not duplicate canonical conversation storage.
5. Do not rewrite the entire backend in TypeScript.
6. Do not replace the application with the Open Intelligent UI demo.
7. Do not introduce a new model provider requirement without justification.
8. Do not destroy previously implemented functionality.
9. Do not use fixed templates as the main generative UI mechanism.
10. Do not rely on raw arbitrary generated JavaScript.
11. Do not allow generated UI to bypass financial authorization.
12. Do not conceal parser defects with cosmetic CSS hacks.
13. Do not present mocked results as production verification.
14. Do not assume documented success means deployed success.
15. Do not add unnecessary latency through multiple presentation-model calls.
16. Do not force UI output for every conversational answer.
17. Do not sacrifice desktop usability to improve mobile.
18. Do not sacrifice mobile usability to preserve desktop.
19. Do not introduce large unexplained architecture changes when a smaller verified repair is sufficient.
20. Do not stop after writing a plan or report.

Reuse existing assets and infrastructure intelligently.

Any imported or adapted reference code must respect its applicable licensing and attribution requirements.

---

28. REQUIRED ENGINEERING DELIVERABLES

At completion, provide a factual implementation report containing:

A. Root-cause analysis

For each reported defect:

- Exact cause.
- Affected files.
- Evidence.
- Implemented fix.
- Verification method.
- Final result.

B. Reference integration report

Explain which Open Intelligent UI / OpenUI capabilities were:

- Directly reused.
- Adapted.
- Reimplemented using existing Lonora services.
- Already supported.
- Deliberately excluded.

Explain the reasoning for major architectural decisions.

C. Message lifecycle

Document the working flow from user submission through Agent execution to final persisted output.

D. Streaming implementation

Identify the actual stream protocol and how client/server state is reconciled.

E. Agent status implementation

Identify the real event sources and how they map to visible execution states.

F. Generative UI implementation

Document:

- Supported components.
- Composition rules.
- Renderer integration.
- Schema validation.
- Error recovery.
- State and actions.
- Mobile behavior.

G. Skill integration

Explain how the official OpenUI development Skill informed the implementation and what was incorporated into Lonora Design Skill.

H. Performance evidence

Provide actual timings before and after changes for relevant execution stages.

I. Test evidence

Provide:

- Automated test results.
- Real browser verification.
- Actual configured-model results.
- Mobile verification.
- Native verification if performed.
- Screenshots or recordings when available.

J. Production verification

Confirm which deployed components and actual client assets were verified.

Distinguish source-code completion from live deployment.

K. Remaining limitations

Explicitly list incomplete, unverified, or intentionally unsupported functionality.

Do not present partial features as fully working.

---

29. FINAL DEFINITION OF DONE

This task is finished only when:

- A submitted user message appears immediately.
- The composer clears correctly after local enqueue.
- Failed submissions remain recoverable.
- Duplicate messages are prevented.
- The Agent visibly indicates real activity.
- Genuine execution states transition correctly.
- Normal answers stream progressively.
- Structured UI displays inside the ordinary chat.
- No raw generated UI syntax appears unexpectedly.
- Unresolved placeholders are not presented as real finished data.
- Interactive controls work.
- Local controls respond without unnecessary model calls.
- Component layouts are compact and professional.
- Mobile rendering is responsive.
- Arabic RTL and English LTR work.
- Chat scrolling remains stable.
- Conversations survive reload and reconnection.
- Existing tools, memory, task execution, trading, voice, attachments, and financial authorization continue working.
- Real configured-model tests pass.
- Production behavior is actually verified.
- The previous "prompt 2.md" objectives remain supported.

The user must experience an immediate, responsive, visually intelligent conversation, not a delayed sequence of oversized cards and broken templates.

---

FINAL DIRECTIVE

Study Open Intelligent UI at the source-code level.

Extract every relevant improvement in conversation behavior, streaming, rendering, interaction design, component composition, state management, reliability, visual consistency, and developer Skills.

Integrate the appropriate capabilities into Lonora's existing Python-and-TypeScript architecture.

Prioritize repairing the current real user experience over adding superficial new features.

Preserve the existing Agent as the single reasoning and presentation authority.

Implement working code, run the tests, verify the real application, and report actual outcomes.

Do not stop at analysis. Do not repeat the previous incomplete implementation. Deliver a functioning, professional, production-quality Lonora conversation experience.