CODEX MASTER ENGINEERING MANDATE

Lonora — Model-Native Generative UI, Autonomous Visual Responses & Unified Design Intelligence

Repository: https://github.com/loorksy/lonorabot

Mission: Full repository inspection, architectural integration, implementation, testing, and production-ready delivery.

Priority: Critical

Implementation requirement: Implement the requested capabilities in actual working code. Architecture proposals, static demonstrations, screenshots, isolated prototypes, or prompt-only modifications are not sufficient.

---

1. Core Vision

Transform Lonora into an AI agent capable of expressing its intelligence through both natural language and dynamically composed, native, interactive visual interfaces.

The objective is to achieve a conversational experience comparable to ChatGPT's ability to generate rich visual components directly within its responses.

Lonora must not require the user to explicitly request an Artifact, dashboard, card, chart, diagram, or interface.

The language model must autonomously determine whether visual presentation improves the response.

For example, the user may simply ask:

"What is happening with my trading account?"

Lonora must:

1. Understand the question in conversational context.
2. Retrieve actual account information through its existing tools.
3. Analyze balances, positions, exposure, performance, and relevant risks.
4. Determine the most useful way to communicate its findings.
5. Respond naturally, using plain text, visual components, interactive elements, or a combination of them.

The model might provide a short textual answer when the account is stable.

Alternatively, if the information is complex, it might compose a rich account overview with metrics, charts, position distribution, risk explanations, and interactive controls.

Both responses are equally valid. The model decides.

There must be no fixed rule that account-related questions require dashboards, trading questions require charts, or technical questions require diagrams.

The visual presentation is part of the model's expressive intelligence.

---

2. Fundamental Architectural Principle

Implement:

Model-Native Generative UI

The desired architecture is:

User's Natural Language
         |
         v
Existing Lonora Agent
         |
         | Understands the request
         | Uses existing tools
         | Analyzes verified information
         | Chooses its response presentation
         |
         v
Model-Native Rich Response
         |
         | Text
         | Native UI components
         | Interactive elements
         | Charts and diagrams
         | Existing verified attachments
         |
         v
Native Conversation Renderer
         |
         v
Web / Android

The existing Lonora Agent must remain the intelligence responsible for:

- Understanding the conversation.
- Selecting and using tools.
- Reasoning about tool results.
- Deciding what information to present.
- Deciding whether visualization is appropriate.
- Selecting visual components.
- Composing their structure and content.
- Selecting useful interactive behavior.

The rendering layer is responsible for validating and displaying the resulting interface.

It must not independently decide when the language model should generate visual components.

Explicitly Forbidden

Do not introduce:

- A second AI agent responsible for designing ordinary responses.
- A separate UI-generation LLM pipeline.
- A keyword-based visualization classifier.
- A mandatory presentation-selection model call.
- A collection of hardcoded response templates.
- A second conversation engine.
- A second Gateway.
- A duplicate artifact storage system.
- A mandatory HTML-generation step.
- A mandatory screenshot-generation step.
- A mandatory visual inspection loop.

The existing Lonora Agent is the single decision-making authority for conversational presentation.

---

3. Mandatory Repository Audit

Before modifying code, inspect the real repository and identify existing reusable systems.

At minimum, investigate:

- Agent runtime and model-provider integrations.
- System instructions and Skills architecture.
- Tool execution and structured responses.
- Conversation messages and persistence.
- Streaming and Gateway event handling.
- Artifact creation, storage, and attachment delivery.
- Existing analytical workspaces.
- React Web message rendering.
- React Native / Expo message rendering.
- Shared contracts and component libraries.
- Existing charting and trading interfaces.
- Theme, design tokens, localization, and RTL support.
- Authorization and financial safety boundaries.

Known areas to inspect include:

packages/agent-runtime/
packages/tools/
packages/contracts/
packages/core/
packages/db/

apps/api/
apps/web/
apps/mobile/

apps/web/src/pages/shell/message-cards.tsx

apps/mobile/components/message-bubble.tsx

packages/db/src/lonora_db/generated_artifacts.py

Verify current paths and behavior instead of assuming these references remain unchanged.

Reuse working infrastructure wherever possible.

Do not rewrite unrelated systems.

---

4. The Model Must Own Presentation Decisions

The model must be capable of producing different visual responses to different conversational needs without predefined triggers.

Examples:

Simple account question

User:

"Is my account okay?"

The model may reply with two sentences.

No visual artifact is required.

Complex account exposure

User:

"What is happening with my account?"

After retrieving actual account data, the model may decide to compose:

- Account balance and equity metrics.
- Current floating profit or loss.
- Open position information.
- Exposure distribution.
- Risk observations.
- Contextual explanations.

The model decides the arrangement.

No mandatory account dashboard template should be imposed.

Architecture explanation

User:

"How does Lonora's Agent work?"

The model may compose a flow diagram with:

- Agent.
- Tools.
- Memory.
- Gateway.
- Task execution.
- Output.

It may use cards, arrows, labels, and expandable sections.

Short factual question

User:

"What does drawdown mean?"

The model may provide a simple definition without generating any special interface.

Trading strategy comparison

The model may decide that an interactive comparison or chart better communicates the result.

These examples describe expected intelligence, not fixed routing rules.

There must be no keyword-to-component mapping and no mandatory visualization policy for any question category.

---

5. Introduce a Native Visual Response Language

Give the language model a structured visual vocabulary that it can use naturally while composing ordinary assistant responses.

The vocabulary must support both text and UI components in a single answer.

The model should be able to express concepts such as:

- Text.
- Headings.
- Cards.
- Columns.
- Rows.
- Grids.
- Containers.
- Dividers.
- Icons.
- Badges.
- Metrics.
- Tables.
- Lists.
- Progress indicators.
- Timelines.
- Flowcharts.
- Diagrams.
- Charts.
- Images.
- Expandable sections.
- Buttons.
- Selectors.
- Checkboxes.
- Sliders.
- Forms.
- Interactive calculations.

These are reusable visual primitives, not fixed response templates.

The model must be free to compose and nest supported components into different visual structures.

A small, flexible set of primitives should support a large variety of layouts.

Important Distinction

Do not implement fixed components such as:

GoldAnalysisAnswer
AccountStatusAnswer
RiskExplanationAnswer
StrategyComparisonAnswer

as the primary conversational presentation mechanism.

Instead, expose general-purpose compositional primitives.

The model should be able to construct these experiences itself.

Domain-specific chart controls or financial visualizations may still exist as reusable lower-level components where necessary.

---

6. Native Structured Output

Implement a well-defined, versioned, model-facing UI representation.

The representation must be:

- Declarative.
- Typed.
- Schema-validated.
- Composable.
- Stream-compatible.
- Persistable.
- Platform-independent.
- Safe by construction.

The model must not need to generate React source code to display a normal conversational component.

The model should produce structured component descriptions, including:

- Component type.
- Properties.
- Children.
- Layout relationships.
- Semantic roles.
- Data values or verified references.
- Interaction specifications.

For example, the model may express:

{
  "version": 1,
  "type": "ui",
  "root": {
    "type": "column",
    "children": [
      {
        "type": "card",
        "children": [
          {
            "type": "heading",
            "text": "Account Overview"
          },
          {
            "type": "metric",
            "label": "Balance",
            "value": "10000",
            "unit": "USD"
          }
        ]
      }
    ]
  }
}

This is only a conceptual example.

Implement the actual schema according to the repository's existing contracts and requirements.

Example values must not be mistaken for actual financial data.

The runtime must reject unsupported component types and invalid properties.

Avoid overly complicated markup languages or unnecessarily large schemas.

The goal is expressive visual composition with minimal protocol complexity.

---

7. Mixed Text and Visual Responses

Lonora must support normal conversational replies containing multiple types of content.

A response may contain:

1. An introductory paragraph.
2. A metric card.
3. A chart.
4. A short explanation.
5. An expandable section.
6. A follow-up question.

All of these elements should appear naturally within the same conversation response.

The model must be able to choose both their content and ordering.

Do not force an entire response to be either plain text or one large UI document.

Implement an ordered mixed-content response structure.

Preserve existing text-only compatibility.

If the model does not request visual elements, the existing text rendering must continue to work normally.

---

8. Unified Lonora Visual Identity

All model-generated native interfaces must automatically follow Lonora's existing visual identity.

The visual identity should be implemented as a centralized design system and source of truth.

It must define or expose:

- Semantic color tokens.
- Background and surface colors.
- Text colors.
- Accent colors.
- Status colors.
- Typography.
- Font scaling.
- Spacing.
- Border radius.
- Borders.
- Elevation and shadows.
- Iconography.
- Layout density.
- Responsive behavior.
- Motion and transitions.
- Light and dark themes.
- Arabic RTL and English LTR behavior.

Do not hardcode visual identity values in individual model-generated documents.

Whenever possible, the model should select semantic meaning, and the renderer should apply the correct visual tokens.

For example:

A model can indicate that a value represents a warning, positive change, or negative change.

The renderer determines its visual treatment according to the existing design system.

This ensures consistent interfaces without forcing the model into fixed layouts.

Changes to Lonora's visual identity should propagate automatically to supported native components.

Do not invent a new visual identity without inspecting the existing application.

---

9. Native Lonora Design Skill

Implement or adapt a first-class Skill named:

Lonora Design Skill

This Skill must integrate with Lonora's existing Skills architecture.

It must provide the model with professional interface-design knowledge.

Its responsibilities include:

- Visual hierarchy.
- Layout composition.
- Information density.
- Card design.
- Dashboard composition.
- Chart selection.
- Diagram composition.
- Responsive design.
- Interaction design.
- Mobile usability.
- Accessibility.
- Arabic RTL design.
- Trading interface conventions.
- Consistent use of Lonora's visual identity.

The Skill must reference the existing centralized design system rather than duplicating colors, fonts, or spacing values.

Skill Behavior

The Skill must assist the model in deciding how to compose high-quality visual responses.

It must not become a separate agent or mandatory decision engine.

The model must remain free to produce a simple text response.

Do not require an explicit Skill invocation for every ordinary card if essential design guidance is already available in the model's response vocabulary or component contracts.

Expose additional Skill knowledge through the existing Skill discovery and loading mechanisms when relevant.

The Skill should help the model understand good design principles without adding unnecessary latency or token consumption.

Future Extensibility

Other imported design-related Skills should be able to use the same design tokens and rendering contracts.

An imported Skill must not silently override Lonora's trusted visual identity or security policies.

---

10. Immediate Native Rendering

Native generated components must render directly inside the conversation.

The ordinary execution path must be:

Model Output
    |
    v
Structured UI Validation
    |
    v
Native Component Rendering
    |
    v
Visible Conversation Response

Do not require:

- HTML generation.
- File creation.
- Image generation.
- Screenshot review.
- A browser-based editing session.
- A separate artifact-generation agent.
- A second LLM review.

These are not prerequisites for ordinary generated visual responses.

The model composes the interface.

The native rendering system displays it.

A lightweight structural and safety validation step is required, but a mandatory visual-review cycle is not.

The design system must provide visual consistency by default.

---

11. Interactive Components

Lonora-generated interfaces must support genuine user interaction.

Examples include:

- Expanding and collapsing sections.
- Switching tabs.
- Selecting trading timeframes.
- Adjusting sliders.
- Checking options.
- Changing displayed chart types.
- Filtering tables.
- Changing local calculations.
- Displaying conditional content.
- Opening an existing chart or attachment.
- Submitting a follow-up request.

Purely local UI interactions must execute without unnecessary LLM calls.

The model must be able to describe:

- Initial state.
- Supported state transitions.
- Derived values.
- Conditional visibility.
- Interaction targets.
- Allowed actions.

Implement a safe declarative state and calculation mechanism.

Do not execute arbitrary model-generated JavaScript in trusted native components.

When a model-generated calculation cannot be safely expressed through the supported declarative operators, use an existing authorized analytical tool or provide a clear fallback.

Every visible interactive control must perform its stated action.

No decorative or nonfunctional buttons.

---

12. Tool-Driven and Evidence-Backed Content

Visual interfaces must be grounded in real data.

For example, if Lonora creates a trading account overview, the values must come from actual account tools.

The interface must not contain fabricated:

- Balances.
- Equity.
- Profit and loss.
- Open positions.
- Market prices.
- Order fills.
- Account exposure.
- Strategy performance.
- Backtesting results.

If information is unavailable, show that it is unavailable.

If a visualization is based on hypothetical information, label it as an example or simulation.

The model must distinguish:

- Observed facts.
- Tool results.
- Calculated values.
- Estimates.
- Simulations.
- Model interpretations.

Preserve provenance, timestamps, appropriate units, and relevant financial context.

Generated visuals must not make unsupported claims.

---

13. Typed Actions and Financial Safety

Interactive components may trigger authorized application actions.

Examples:

- Refresh account data.
- Request another analysis.
- Open a chart.
- Open an artifact.
- Ask the existing Agent a follow-up.
- Start an authorized workflow.
- Request a risk calculation.

These actions must use a typed, allowlisted protocol connected to existing Lonora services.

The renderer must never execute arbitrary actions invented by the model.

For financial operations:

- Preserve existing owner authentication.
- Preserve financial authorization.
- Preserve broker-specific safety rules.
- Preserve risk checks.
- Preserve approval boundaries.
- Preserve idempotency.
- Preserve execution receipts and reconciliation.

Changing a selector, pressing a generated button, or modifying a local state value must never implicitly grant trading authorization.

The visual response system is a presentation and interaction capability, not an alternate execution authority.

---

14. Native Web and React Native Integration

Implement rendering inside Lonora's existing conversation components.

Web

Use the existing React architecture.

Reuse existing:

- UI components.
- Design tokens.
- Conversation layout.
- Markdown rendering.
- Chart infrastructure.
- Localization.
- Theme management.

Android / React Native

Implement equivalent native rendering using the existing React Native / Expo architecture.

Support:

- Native touch interactions.
- Responsive layouts.
- Small screens.
- Scrolling.
- Keyboard behavior.
- Accessibility.
- RTL layout.
- Theme consistency.

Use shared contracts for both platforms.

Prefer reusing existing component primitives rather than duplicating layout logic.

A model-generated UI document should produce functionally equivalent experiences on supported platforms.

Avoid depending on a WebView for ordinary generated UI.

---

15. Streaming and Conversation Continuity

The visual response system must integrate with Lonora's existing conversational streaming and Gateway architecture.

Support:

- Mixed text and UI output.
- Validated atomic component or document delivery.
- Ordered response content.
- Cancellation and interruption.
- Reconnection.
- Durable publication.
- Idempotent delivery.
- Recovery from malformed output.
- Text fallback when necessary.

Do not render incomplete or invalid structures that could break the conversation.

Do not initiate an unnecessary second model call merely to select or generate a visual layout.

The visual response should be part of the existing model turn whenever possible.

The existing Agent should continue to own reasoning, tool execution, and final response composition.

---

16. Persistence and Reopening Conversations

Generated visual responses must remain valid after:

- Reloading the Web application.
- Closing and reopening Android.
- Navigating between conversations.
- Gateway restart.
- Temporary network interruption.

Persist the validated visual document and its relationship to the original assistant message.

Preserve content ordering and component identity.

Use versioned schemas for future compatibility.

Persist only the interactive state necessary for the expected user experience.

Prevent stale or reused visual components from performing privileged operations without renewed authorization and verification.

Reuse the existing message and attachment infrastructure.

Do not introduce a duplicate conversational artifact platform.

---

17. Relationship to Existing Artifacts

Keep Lonora's existing ability to create and deliver ordinary files.

Examples include:

- PDF reports.
- Spreadsheets.
- Images.
- Documents.
- CSV exports.
- Analysis results.

However, ordinary model-native visual responses must not depend on the creation of these files.

Scope Boundary

The feature requested here is Native Generative UI, not unrestricted executable application generation.

Do not add a new freeform HTML/JavaScript application runtime solely to implement this mandate.

Do not make arbitrary model-generated executable code the default method of displaying rich responses.

The model should freely compose supported trusted native components.

Existing file and analytical workspace capabilities should remain available for legitimate separate tasks.

---

18. Performance Requirements

The feature must preserve natural conversational speed.

In particular:

- Do not add a second LLM call for ordinary visual responses.
- Do not require screenshots before showing components.
- Do not require browser automation to produce a standard card.
- Do not load an enormous design manual in every model turn.
- Do not force every answer into structured UI.
- Do not invoke the Design Skill unnecessarily.
- Do not create background jobs for simple local interactions.

Keep the model-facing component vocabulary compact and expressive.

Use the existing model-provider structured-output capabilities where practical.

Support provider compatibility and graceful fallback when structured UI generation is unavailable.

The normal text conversation must remain fast and reliable.

---

19. Mandatory Acceptance Scenarios

Implement automated and actual interface tests for the following.

Scenario A — Autonomous Account Presentation

User:

"How is my trading account doing?"

Lonora retrieves real available account data.

The model autonomously decides whether a visual interface is appropriate.

If visual presentation is selected, the model composes the appropriate components from verified data.

There must be no hardcoded account-question-to-dashboard rule.

Scenario B — Plain Text Remains Natural

User:

"What does equity mean?"

The system must permit a normal text answer.

No unnecessary visual interface should be forced.

Scenario C — Architecture Diagram

User:

"Explain how Lonora works."

The model can generate an architecture diagram using native components.

The diagram appears directly inside the ordinary chat response.

Scenario D — Interactive Risk Calculator

User:

"Help me understand position sizing."

When the model chooses an interactive explanation, the generated controls must function.

Changing inputs updates results correctly.

Financial calculations must use valid instrument specifications and clearly defined assumptions.

The calculator must not execute trades.

Scenario E — Mixed Visual Response

The model produces:

- Introductory text.
- Visual metrics.
- A chart.
- An explanatory paragraph.
- An expandable section.

All content appears in the intended order inside one conversational response.

Scenario F — Visual Identity Consistency

Generated interfaces must follow Lonora's existing design system.

Test:

- Dark theme.
- Light theme.
- Arabic RTL.
- English LTR.
- Small Android screens.
- Responsive Web layout.
- Accessibility.
- Typography.
- Spacing.
- Component consistency.

Scenario G — Interactive State

The model generates a UI containing selectors, checkboxes, and a preview action.

Controls work correctly.

Local state updates do not unnecessarily invoke the Agent.

Scenario H — Conversation Persistence

Reopen a conversation containing visual components.

The content remains available and displays correctly.

Scenario I — Gateway Recovery

Restart the Gateway and reconnect clients.

Previously published content remains valid.

No duplicate privileged actions are executed.

Scenario J — Security

Reject:

- Unsupported component types.
- Invalid component properties.
- Arbitrary executable code.
- Unauthorized actions.
- Oversized UI documents.
- Excessive component nesting.
- Invalid external references.
- Attempts to bypass financial authorization.

Scenario K — No Hidden Presentation Router

Verify that presentation choices are not being made by hardcoded keywords, category mappings, or a separate model.

The existing language model must compose the response directly.

Scenario L — Real Model Integration

Demonstrate the feature through the actual Lonora conversation path with a configured model provider.

Do not declare success based only on manually constructed JSON fixtures, mocked screenshots, or a standalone development page.

Test the real model-to-renderer integration.

---

20. Implementation Strategy

Proceed in the following order.

Phase 1 — Repository and Design System Audit

Inspect the current architecture and identify reusable components.

Phase 2 — Visual Response Contract

Implement a compact shared schema supporting mixed text and native visual components.

Phase 3 — Model Integration

Expose the visual vocabulary to the existing Agent through its normal response generation path.

Preserve model ownership of presentation decisions.

Phase 4 — Design Skill

Integrate Lonora Design Skill with the existing Skill infrastructure and visual identity.

Phase 5 — Native Web Rendering

Render model-generated visual components directly inside Web conversation messages.

Phase 6 — Android Rendering

Implement functionally equivalent React Native rendering.

Phase 7 — Interaction Layer

Add validated state transitions, local calculations, and typed backend actions.

Phase 8 — Persistence and Streaming

Integrate with message history, Gateway events, reconnection, and schema versioning.

Phase 9 — Verification

Execute unit tests, integration tests, rendering tests, security tests, and real end-to-end conversation tests.

Phase 10 — Production Integration

Integrate with the existing repository architecture.

Do not enable unfinished or unsafe features in production.

Repair any CI failures caused by the changes and report unrelated pre-existing failures separately.

Avoid unrelated architectural refactoring.

---

21. Engineering Deliverables

Provide:

1. A concise summary of the architecture discovered.
2. The implemented visual response contract.
3. The model-facing component vocabulary.
4. The native component registry.
5. The unified design-system integration.
6. The installed Lonora Design Skill.
7. The Web renderer.
8. The React Native renderer.
9. The interaction and state system.
10. The persistence and streaming integration.
11. Security and financial authorization enforcement.
12. Automated test results.
13. Real model-driven end-to-end verification evidence.
14. Relevant screenshots or recordings from actual rendering tests, when available.
15. Remaining limitations and compatibility constraints.
16. Exact commits, changed files, and deployment requirements.

Do not claim completion for features that have only been designed or partially implemented.

Report independently which behaviors were verified by automated tests and which were verified through running applications.

---

22. Final Definition of Done

The task is complete only when all of the following are true:

- Lonora's existing model can autonomously decide whether to use visual components.
- No separate model or keyword classifier makes that decision.
- The model can freely compose supported native UI primitives.
- Visual elements appear directly inside ordinary conversations.
- The same response can combine text and visual components.
- Generated elements follow Lonora's unified visual identity.
- Lonora Design Skill is available through the existing Skills system.
- Interactive controls have real, functional behavior.
- Purely local interactions do not require unnecessary LLM calls.
- Privileged operations use existing authorized services.
- Real trading data is accurately represented.
- Web and Android are supported.
- Conversations preserve visual content across reloads.
- The Gateway and existing Agent architecture remain intact.
- Existing Markdown, files, voice, charting, and trading capabilities continue to work.
- Automated and end-to-end tests demonstrate the implementation.
- No unnecessary duplicate architecture has been introduced.

---

FINAL MANDATE

Lonora must possess native visual intelligence as part of its ordinary conversational ability.

The model must understand when an answer should be textual, visual, interactive, or a natural combination of these forms.

It must not depend on explicit user requests for Artifacts.

It must not depend on hardcoded response templates.

It must not require a separate UI-generation agent.

It must be able to compose diverse interfaces from trusted native visual primitives while automatically respecting Lonora's design identity.

The Design Skill provides visual expertise.

The shared design system guarantees consistency.

The renderer displays the interface.

The interaction layer provides validated behavior.

The Agent remains the sole intelligence deciding what the response should contain.

One Agent. One Conversation. One Visual Identity. Unlimited practical composition within the supported native component vocabulary.

Implement this functionality inside the existing Lonora repository as a working, production-ready capability.

Do not stop at analysis, documentation, mockups, or isolated demonstrations.