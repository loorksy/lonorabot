CODEX IMPLEMENTATION MANDATE

Lonorabot — Unified Agent Delegation & Permission Experience

Mission

Implement a complete, production-ready Agent Delegation and Permission Experience in the existing Lonorabot repository.

Repository:
https://github.com/loorksy/lonorabot

The implementation must combine:

1. Three simple user-facing permission levels.
2. A compact permission selector integrated directly into the chat composer.
3. Advanced financial delegation customization.
4. Responsive interfaces for desktop browsers, mobile browsers, and native mobile applications.
5. Secure owner authorization through the existing AccountAuthority infrastructure.
6. Permission-aware behavior throughout the existing LLM-driven Agent Runtime.
7. Persistent, server-authoritative permission state.
8. Seamless transitions between permission levels.
9. Full integration with existing trading, approval, scheduling, and financial execution capabilities.

Implement the complete working feature. Do not deliver only mockups, architecture proposals, or documentation.

---

1. Fundamental Design Principles

Lonorabot is an LLM-driven autonomous trading agent platform.

The LLM is the primary decision-making intelligence. The platform provides the environment, tools, permissions, execution capabilities, and persistence required for the agent to operate.

The delegation system must follow this principle:

The user defines the objective. The LLM independently determines how to pursue it. The delegation level defines what financial actions the LLM is authorized to execute.

The delegation layer must regulate financial authority without replacing the model's independent reasoning.

Mandatory principles:

- One unified permission experience.
- Exactly three primary user-facing permission levels.
- One compact selector beside the chat input.
- Advanced Customization exclusively associated with Autonomous Management.
- Existing AccountAuthority infrastructure remains authoritative.
- Existing financial approval mechanisms remain authoritative.
- Existing broker execution and validation remain authoritative.
- Each agent maintains its own permission state.
- Desktop and mobile interfaces expose equivalent capabilities.
- Interface complexity remains hidden until the user requests advanced control.
- Financial permissions must never be inferred from conversational instructions.
- No duplicate authorization engine, trading runtime, or account management subsystem.

The user should experience the system as a simple permission selector, not a technical authorization configuration platform.

---

2. Mandatory Three-Level Delegation Model

Implement exactly three primary levels.

Level 1 — Analysis Only

English: "Analysis Only"

Arabic: "تحليل فقط"

Internal semantic identifier: "analysis"

This is the default effective level for newly created agents that have not received a broader owner authorization.

Allowed capabilities

- Market analysis.
- Chart analysis.
- Account information retrieval.
- Position and pending-order inspection.
- Market opportunity discovery.
- Trading recommendations.
- Trading plan development.
- Analytical tool execution.
- Memory and skill usage.
- Analytical task creation.
- Market watch creation.
- Scheduled market reviews.
- Background analytical monitoring.
- Evidence-based reporting.

Financial restrictions

The agent cannot perform any broker financial mutation.

This includes opening, closing, modifying, or canceling trades, positions, and orders.

The restrictions apply equally to foreground and background execution.

Level 2 — With My Approval

English: "With My Approval"

Arabic: "بموافقتي"

Internal semantic identifier: "supervised"

The agent retains independent analytical capabilities.

It may:

- Analyze market conditions.
- Identify entry and exit opportunities.
- Select trading direction.
- Calculate candidate volume.
- Propose stop-loss and take-profit levels.
- Prepare pending orders.
- Propose modifications and closures.
- Monitor multiple positions.
- Continue analytical work while approval is pending.

Every financial mutation must receive the existing trusted, operation-specific owner approval before execution.

The agent may propose an action but cannot execute it until that action is approved.

Selecting this level should be an immediate authenticated permission change.

It must not require a full autonomous-management signature merely to enable the supervised experience.

Level 3 — Autonomous Management

English: "Autonomous Management"

Arabic: "إدارة مستقلة"

Internal semantic identifier: "autonomous"

The agent can independently manage the authorized trading account within its signed financial delegation.

Allowed capabilities include:

- Independent market analysis.
- Selection of trading direction and timing.
- Buy and sell execution.
- Pending-order creation and management.
- Position modification.
- Stop-loss management.
- Take-profit management.
- Position sizing.
- Multiple concurrent position management.
- Partial and full position closure where supported.
- Scheduled market reviews.
- Event-driven account monitoring.
- Continuous account management while the owner is offline.
- Pursuit of owner-defined trading objectives.

The agent may execute permitted financial operations without requesting individual approval for each operation.

However, this level requires an active, valid, securely signed AccountAuthority grant.

The signed authorization scope and existing broker controls remain authoritative.

Critical mapping

Do not equate a bounded AccountAuthority grant with the supervised permission level.

A signed "management_mode=full" delegation may contain optional numerical limits and selected actions.

Therefore, a customized autonomous delegation remains Autonomous Management even when the user restricts certain actions, volume, or duration.

The three primary user-facing levels describe approval behavior, while AccountAuthority defines the exact permitted financial scope.

---

3. Chat Composer Permission Selector

Integrate the permission selector directly beside the message input field.

The component must be available in the existing chat experience on desktop, mobile web, and the native mobile application.

Example:

┌───────────────────────────────────────────────┐
│ Gold Trading Agent                            │
│ XAUUSD · Connected Account                    │
│                                               │
│ How can I help you today?                     │
│                                               │
│ [ Autonomous Management ▾ ]  [ + ]     [ ↑ ]  │
└───────────────────────────────────────────────┘

The selector must:

- Display the current effective permission.
- Open with a single interaction.
- Present three clearly labeled options.
- Include a short explanation of each level.
- Identify the currently selected level.
- Support keyboard and touch interaction.
- Support RTL and LTR layouts.
- Show the true authorization state obtained from the server.

Selector structure

Agent Permissions

○ Analysis Only
  Analyze and monitor without trading

○ With My Approval
  Request approval before financial actions

● Autonomous Management
  Independently manage authorized trading

────────────────────────────────

Advanced Customization

Advanced Customization must appear only when Autonomous Management is selected.

Do not show this financial customization entry under Analysis Only or With My Approval.

If the user returns to a lower permission level, previously saved customization preferences may remain available for future review, but the associated autonomous financial authority must not remain active.

Permission status presentation

Support clear representations of:

- Analysis Only
- With My Approval
- Autonomous Management
- Awaiting Secure Authorization
- Authorization Expired
- Authorization Failed
- Autonomous Management Stopped

Pending authorization must not be presented as active autonomy.

Show the effective permission separately from a requested but not-yet-authorized change.

---

4. Adaptive User Experience Across Devices

Implement a unified feature with device-appropriate presentations.

Do not force one identical layout across all screen sizes.

The interaction patterns must adapt to the device while preserving the same underlying settings and authorization logic.

4.1 Desktop Browser

Permission selector

Use a compact popover attached to the chat composer.

The user selects a permission without navigating away from the conversation.

Advanced Customization

Open a centered dialog or appropriate desktop overlay.

Use a two-column layout.

Left column: Configuration

- Account and symbol scope.
- Allowed financial actions.
- Trading limits.
- Authorization duration.
- Manual-position permissions.

Right column: Live Summary

- Agent identity.
- Trading account.
- Authorized symbol scope.
- Number of enabled actions.
- Customized limits.
- Manual-position coverage.
- Authorization duration.
- Financial risk disclosure.

The right column must reflect configuration changes immediately.

Keep the primary Review and Continue action visible.

Use compact cards, grouped controls, consistent spacing, and clear visual hierarchy.

The interface must not resemble a long technical settings form.

4.2 Mobile Browser

Permission selector

Open a compact, touch-friendly bottom sheet or equivalent mobile selection surface.

The selector must remain visually connected to the chat composer.

Advanced Customization

Open a dedicated full-height responsive configuration interface.

Do not squeeze the entire desktop configuration dialog into a narrow viewport.

Requirements:

- Single-column layout.
- Full usable viewport width.
- Scrollable configuration content.
- Compact header with agent identity.
- Four collapsible configuration groups.
- Sticky bottom Review action.
- Safe keyboard behavior.
- No horizontal scrolling.
- Comfortable touch targets.
- Correct handling of mobile browser viewport resizing.
- Correct RTL alignment and text wrapping.

The desktop summary column must not consume permanent horizontal space on mobile.

Instead, show a compact summary near the bottom and present the complete summary during the review step.

4.3 Native Mobile Application

Implement the equivalent experience using the existing native application architecture.

Permission selection

Use a platform-appropriate bottom sheet or compact selection surface.

Advanced Customization

Use a dedicated full-screen configuration flow or platform-appropriate full-height sheet.

Requirements:

- Native navigation behavior.
- Platform safe-area handling.
- Keyboard avoidance.
- Smooth vertical scrolling.
- Predictable Back behavior.
- Persistent footer action.
- Correct disabled and loading states.
- Native accessibility semantics.
- Device-supported secure signing.
- Consistent RTL and LTR layouts.

Use existing native components and styling conventions.

Do not introduce a separate web application inside the native application merely to implement permission customization.

4.4 Responsive Behavior

The implementation must work across:

- Narrow mobile screens.
- Standard mobile screens.
- Large smartphones.
- Tablet-sized screens.
- Desktop windows.
- Resized desktop windows.
- Portrait and landscape orientations.

Use appropriate responsive layout rules.

Avoid brittle device detection based solely on user-agent strings.

---

5. Advanced Customization Architecture

The existing Lonorabot AccountAuthority advanced customization capability must be preserved and integrated.

Advanced Customization is an extension of Autonomous Management, not a fourth primary permission level.

The user chooses:

Autonomous Management → Advanced Customization

The customization interface must contain four collapsible configuration groups.

Group A — Trading Account and Market Scope

Display:

- Agent identity.
- Connected trading account.
- Broker identity, if available.
- Authorized instrument scope.

For specialist agents, respect their existing immutable account and symbol binding.

For eligible Personal Agents, support explicitly selected account-wide scope when permitted by the current AccountAuthority contract.

No agent may silently expand its scope.

The account and symbol values must come from authoritative application data.

Group B — Allowed Financial Operations

Reuse the existing AccountAuthority action definitions.

Expose all currently supported actions:

buy
sell
buy_limit
sell_limit
buy_stop
sell_stop
close_position
modify_position
cancel_order
modify_order

Use understandable user-facing labels.

Examples:

- Open Buy
- Open Sell
- Buy Limit
- Sell Limit
- Buy Stop
- Sell Stop
- Close Position
- Modify Position
- Cancel Pending Order
- Modify Pending Order

Display the actions as compact selectable controls.

Provide:

- Select All.
- Deselect All.
- Individual action selection.
- Immediate selected-action count.
- Correct validation of the resulting scope.

Do not allow a proposal with an invalid or empty action set to advance to signing.

The interface must map exactly to the existing contract, not invented financial capabilities.

Group C — Trading Limits

Reuse the existing optional AccountAuthority limits:

maximum_order_volume
maximum_symbol_volume
maximum_positions
maximum_pending_orders
maximum_actions
minimum_equity

Provide understandable labels and appropriate input validation.

Allow optional limits under full management.

An empty optional limit must correctly map to the corresponding absence of a numerical restriction.

Do not silently invent maximum position sizes, trade counts, or monetary loss ceilings.

Use the existing contract's validation rules.

Present volume in the correct trading unit.

Present minimum equity in the actual account currency.

Do not describe "minimum_equity" as a guaranteed maximum-loss limit.

If the current contract does not support a particular financial limit, do not silently simulate it as an enforceable server control.

Group D — Authorization Duration and Manual Positions

Expose:

valid_until
allow_manual_positions

Offer simple authorization-duration choices such as:

- Until I Stop It.
- 12 Hours.
- 24 Hours.
- 7 Days.

Convert duration presets into the correct absolute expiration timestamp when constructing the actual authorization proposal.

Use timezone-aware timestamps.

The signed duration must be explicit during review.

Do not silently refresh or extend an expiring grant.

Allow the user to decide whether autonomous management includes positions opened manually or outside Lonorabot.

Preserve all existing server-side checks governing these positions.

---

6. Progressive Disclosure and Minimal Interface Complexity

The user must never be forced to navigate a long form merely to select a permission level.

Use progressive disclosure.

Default interaction

The user sees only:

Analysis Only
With My Approval
Autonomous Management

When Autonomous Management is selected

Display a simple authorization path and an optional:

Advanced Customization

When Advanced Customization is opened

Show four collapsed groups:

Account & Market Scope
Allowed Operations
Trading Limits
Duration & Manual Positions

Each group displays a concise summary of its current settings.

Expanding one group reveals its controls.

The user should understand the effective configuration without opening every group.

Configuration usability

- Preserve unsaved edits while navigating between groups.
- Provide clear validation messages.
- Show changes immediately in the summary.
- Disable Review when the proposal is invalid.
- Avoid excessive animations.
- Avoid nested scrolling where possible.
- Avoid oversized interactive elements.
- Avoid unnecessary technical terminology.

The interface should feel like a modern consumer financial application rather than an administrative console.

---

7. Simple Authorization and Advanced Authorization

Provide two paths under Autonomous Management.

Path A — Simple Autonomous Management

The user selects Autonomous Management and proceeds directly to review.

Construct the existing full-management proposal using the authorized agent/account scope and the corresponding existing defaults.

The review must clearly disclose the permitted actions, included manual positions, authorization duration, and whether numerical limits are absent.

Do not silently interpret an unrestricted numerical field as safe or low risk.

Path B — Customized Autonomous Management

The user opens Advanced Customization.

The user may restrict:

- Allowed financial operations.
- Position and order volume.
- Number of positions.
- Number of pending orders.
- Number of financial actions.
- Minimum account equity.
- Authorization duration.
- Management of manually opened positions.

Both paths must use the same AccountAuthority proposal, review, signature verification, and activation infrastructure.

Do not create separate simple-mode and advanced-mode financial authorization engines.

---

8. Secure Authorization Flow

Use the existing AccountAuthority proposal and secure signing workflow.

The complete flow is:

Select Autonomous Management
            ↓
Optional Advanced Customization
            ↓
Construct Valid AccountAuthority Proposal
            ↓
Server Creates Pending Proposal
            ↓
Review Exact Financial Scope
            ↓
Owner Confirms Using Existing Secure Device Authentication
            ↓
Server Verifies Signed Authorization
            ↓
Grant Becomes Active
            ↓
Existing Account Management Runtime Starts

The real authorization must use the current secure device-verification system.

Reuse existing Passkey/WebAuthn support and the corresponding native mechanisms.

The authorization review must show the exact financial scope being signed.

The final active scope must match the verified signed proposal.

Any change requiring a replacement financial authorization must follow the existing review and signing process.

The interface must not activate autonomy from an unsigned local state.

Review screen

The review must summarize:

- Agent.
- Trading account.
- Broker symbol scope.
- Allowed actions.
- Numerical restrictions.
- Authorization duration.
- Manual-position management.
- Whether individual trade approvals will be required.

Display a concise financial-risk disclosure.

The user must understand that autonomous execution can generate losses and does not guarantee a profit target.

Signing states

Support:

- Preparing authorization.
- Awaiting owner confirmation.
- Verifying signature.
- Activated.
- Canceled.
- Expired.
- Failed.

Canceling or failing the signing process must not activate the requested authority.

---

9. Permission State and Transitions

Maintain a single authoritative effective permission for each agent.

Required transitions:

From| To| Behavior
Analysis Only| With My Approval| Authenticated immediate change
Analysis Only| Autonomous Management| Secure authorization required
With My Approval| Analysis Only| Immediate restriction
With My Approval| Autonomous Management| Secure authorization required
Autonomous Management| With My Approval| Revoke autonomy; retain supervised behavior
Autonomous Management| Analysis Only| Revoke autonomy; restrict financial mutations

Pending state

When a user requests Autonomous Management but has not completed signing:

- Preserve the previous effective permission.
- Display Awaiting Authorization.
- Permit only actions allowed by the current effective permission.
- Activate autonomy only after successful server verification.

Permission downgrade

When autonomy is reduced:

- Revoke the corresponding autonomous authority.
- Stop grant-bound autonomous-management work.
- Prevent queued or resumed work from using revoked authority.
- Preserve broker journal records.
- Preserve unrelated authorized analytical work.
- Do not automatically close open positions.
- Update the effective permission shown in connected clients.

Already submitted broker operations must continue through existing reconciliation procedures.

Previously customized settings

Store reusable customization preferences separately from active financial authority where the existing architecture permits.

When the user leaves Autonomous Management:

- Revoke financial authority as required.
- Preserve the user's customization draft.
- Never preserve it as executable permission.

When the user returns to Autonomous Management:

- Restore the previous customization for review.
- Display the current account and symbol scope.
- Require a new valid signed authorization.
- Never silently reactivate an old grant.

---

10. Multi-Agent Isolation

Permission settings are agent-specific.

Each agent must have independent:

- Effective permission level.
- Pending authorization state.
- Authorized account and symbol scope.
- Advanced customization draft.
- Active signed financial delegation.
- Revocation state.

Switching between agents must immediately display the selected agent's actual permission.

No other agent's permissions may be changed implicitly.

Preserve the existing specialist-agent account/symbol binding.

Delegated subagents and research agents must not gain independent financial authority merely through task delegation.

---

11. Agent Awareness and LLM-Driven Behavior

Integrate the permission layer into the existing LLM-driven Agent Loop.

The agent must receive accurate, trusted information about its effective capabilities.

This should include:

- Current permission level.
- Whether financial mutations are prohibited.
- Whether owner approval is required.
- Whether valid autonomous authorization is active.
- Permitted account and symbol scope.
- Permitted financial actions.
- Relevant active limits.

The agent must continue reasoning independently.

Do not introduce rigid keyword-triggered behavior that replaces the LLM's understanding of user intent.

Scenario A — Analysis Only

User:

«I'm going to sleep. I want you to make $100 profit by tomorrow morning.»

Expected behavior:

- Understand the desired overnight trading objective.
- Recognize that the current permission is Analysis Only.
- Perform useful permitted analytical preparation.
- Explain that trade execution requires broader authority.
- Offer a contextual Autonomous Management authorization control.
- Continue permitted monitoring if an actual background task is created.
- Do not execute financial mutations.
- Do not guarantee profit.

The model should avoid unnecessarily refusing the entire task when useful permitted work remains possible.

Scenario B — With My Approval

The same user sends the same instruction.

Expected behavior:

- Understand the objective.
- Analyze potential opportunities.
- Prepare financial actions when appropriate.
- Request approval for each financial mutation.
- Never execute an unapproved operation.
- Continue authorized analytical work while waiting.

Scenario C — Autonomous Management

The same user sends the same instruction.

Expected behavior:

- Understand the objective.
- Inspect current account and market state.
- Select appropriate analysis tools.
- Evaluate opportunities.
- Decide independently whether and when to trade.
- Manage permitted positions.
- Schedule or maintain meaningful market monitoring.
- Continue account-management work while the user is away.
- Verify actual broker outcomes.
- Report confirmed results.

Treat $100 as a target, not a guarantee.

Do not force transactions solely to reach the target.

The model remains responsible for trading decisions within the owner's signed delegation.

---

12. Unified Financial Enforcement

Enforce financial authority within the existing trusted server-side execution boundaries.

Do not rely only on:

- Frontend selection.
- Chat messages.
- Model instructions.
- Generated UI actions.
- Cached client permission state.

Enforcement must apply to:

- Ordinary agent runs.
- Financial tool calls.
- Background tasks.
- Scheduled workflows.
- Market-watch wakeups.
- Resumed runs.
- Collaborating agents.
- Subagent execution.
- Retried operations.
- Concurrent financial operations.

Continue using existing:

- AccountAuthority validation.
- Device signature verification.
- Agent binding.
- Financial approval mechanisms.
- Trade preflight.
- Broker execution controls.
- Idempotency.
- Execution journaling.
- Broker reconciliation.
- Global Trading ON/OFF.
- Emergency Stop.

Permission selection must not implicitly switch global trading controls.

No new financial executor or risk engine is authorized by this task.

---

13. Integration With Existing Lonorabot Code

Inspect the repository and identify the current implementations before editing.

Reuse the appropriate existing modules, including where applicable:

packages/contracts/src/lonora_contracts/account_authority.py
packages/core/src/account-authority.ts
packages/core/src/account-authority-labels.ts

packages/db/src/lonora_db/account_authority.py
packages/db/src/lonora_db/agent_binding.py

packages/auth/src/lonora_auth/account_authority.py

packages/trading/src/lonora_trading/account_authority.py

packages/tools/src/lonora_tools/trade.py
packages/tools/src/lonora_tools/registry.py

packages/agent-runtime/src/lonora_agent/tool_loop.py

apps/api/src/lonora_api/routes/account_authority.py

apps/web/src/components/trading/AccountAuthoritySettings.tsx

apps/mobile/components/account-authority-settings.tsx

Treat these paths as references to inspect, not as permission to assume the implementation has remained unchanged.

Also inspect the actual Web and Mobile chat-composer implementations.

Use the existing contracts and services.

Extend the existing architecture minimally.

Keep implementation identifiers and source-code documentation in English.

Provide Arabic and English user-facing strings through the existing localization approach.

---

14. Reference HTML and Visual Fidelity

A standalone interactive HTML reference may be supplied with this task:

"lonorabot-delegation-interactive.html"

Use it as the primary visual and interaction reference for:

- Overall layout.
- Dark interface styling.
- Permission selector behavior.
- Three-level selection.
- Advanced customization.
- Collapsible configuration sections.
- Live authorization summary.
- Review and signature steps.
- Desktop presentation.
- Mobile browser presentation.
- Native-style mobile presentation.
- Agent switching behavior.

Study the supplied reference carefully when it is available.

Recreate the intended user experience using the existing production UI architecture.

Do not merely embed the HTML page.

Do not copy its simulated authorization or chat behavior into production.

Replace every simulated interaction with the actual application state, APIs, and security mechanisms.

If the reference file is not available in the workspace, implement the documented layout and interactions without blocking the task.

---

15. Consistent Web and Native Mobile Behavior

Both interfaces must use the same effective delegation semantics.

They must display the same server-authoritative financial authorization state.

Required experience:

Desktop

- Compact composer selector.
- Attached selection popover.
- Centered advanced configuration dialog.
- Two-column advanced editor and live summary.
- Clear review and signing flow.

Mobile Web

- Compact composer selector.
- Touch-friendly permission selection.
- Full-height advanced customization.
- Single-column collapsible groups.
- Persistent bottom review action.
- Complete review on a separate step.

Native Mobile

- Compact composer selector.
- Native-friendly selection sheet.
- Full-screen advanced editor.
- Keyboard and safe-area support.
- Native accessibility behavior.
- Secure platform signing where configured.

No device should receive a reduced set of authorization capabilities merely because its screen is smaller.

---

16. Performance and User Experience

The permission selector must behave like a lightweight native part of the chat interface.

Requirements:

- Fast open and close interactions.
- Responsive selection feedback.
- No unnecessary navigation.
- No full chat-page reload after permission changes.
- No blocking the chat composer while advanced settings are being edited.
- No loss of entered chat text.
- No loss of unrelated conversation state.
- Efficient data fetching.
- Avoid duplicate authorization requests.
- Debounce or otherwise control high-frequency draft updates.
- Preserve edits while moving between customization groups.
- Synchronize confirmed permission changes across connected sessions.

The permission interface must remain compact and polished.

Avoid creating a large, permanently visible configuration panel inside the conversation.

---

17. Accessibility and Localization

Implement complete English and Arabic support.

Requirements:

- Correct RTL/LTR layouts.
- Proper direction for symbols, numeric values, and account identifiers.
- Accessible labels.
- Keyboard operation.
- Visible focus states.
- Screen-reader descriptions.
- Clear validation errors.
- Appropriate touch target dimensions.
- Reduced-motion compatibility.
- Light and dark theme support where the application supports both.

Financial confirmation screens must prioritize clarity over visual decoration.

---

18. Verification and Automated Tests

Implement meaningful automated coverage.

Permission State

Verify:

- Default Analysis Only behavior.
- Supervised-mode selection.
- Autonomous-mode authorization requirements.
- Server-authoritative state.
- Per-agent isolation.
- Persistence after reload.
- Persistence across Web and Mobile sessions.
- Correct pending and failed authorization states.

Advanced Customization

Verify:

- Every existing AccountAuthority action.
- Every supported optional numerical limit.
- Valid and invalid numerical input.
- Authorization duration conversion.
- Manual-position permission.
- Specialist-agent symbol scope.
- Personal-Agent account scope.
- Simple and customized full-management proposals.
- Correct proposal review.
- Customization preservation after downgrades.
- Fresh signing when reactivating autonomy.

Security

Verify:

- Unsigned autonomy cannot become active.
- Chat instructions cannot grant permissions.
- Model tool calls cannot escalate authority.
- Invalid signatures are rejected.
- Expired authorization is rejected.
- Revoked grants cannot be reused.
- Concurrent permission changes are handled safely.
- Financial mutations obey effective permissions.
- Subagents cannot inherit unauthorized broker execution.

Agent Behavior

Verify the same user objective under all three levels.

Ensure the agent's analytical freedom remains intact while its financial execution rights differ correctly.

UI

Test:

- Desktop browser.
- Mobile browser.
- Native mobile interface.
- Small screens.
- Landscape orientation.
- RTL and LTR.
- Permission selector placement.
- Advanced Customization visibility.
- Collapsible groups.
- Live summaries.
- Review and signature states.
- Responsive layout without horizontal overflow.

End-to-End

Validate the complete experience:

Open Agent Chat
    ↓
Choose Permission
    ↓
Open Advanced Customization (if Autonomous)
    ↓
Configure Financial Scope
    ↓
Review Exact Authorization
    ↓
Complete Secure Signing
    ↓
Server Confirms Effective Permission
    ↓
Agent Operates Within Granted Authority
    ↓
Owner Downgrades Permission
    ↓
Autonomous Authority Is Revoked

Use the existing test infrastructure and simulated broker environment.

Do not execute real-money trades during testing.

---

19. Final Acceptance Criteria

Implementation is accepted only when:

1. All three permission levels work end to end.
2. The selector is integrated beside the actual chat composer.
3. Advanced Customization appears only under Autonomous Management.
4. Existing AccountAuthority customization remains available.
5. All supported trading actions and limits are configurable.
6. Simple and customized autonomous permission use the same signed authorization infrastructure.
7. Desktop, mobile web, and native mobile provide responsive, professional interfaces.
8. The desktop editor includes a live summary.
9. Mobile customization uses collapsible groups and a persistent review action.
10. Permission state is authoritative and isolated per agent.
11. Permission downgrades invalidate autonomous authority correctly.
12. Previously customized settings can be reviewed again without silently restoring financial authority.
13. The LLM remains independently responsible for reasoning and decision-making.
14. Financial execution respects the effective permission everywhere.
15. Actual authorization requires the existing secure signing mechanism.
16. No new financial execution engine or duplicate permission subsystem is introduced.
17. Open positions are not automatically closed merely because permission changes.
18. The existing global trading controls remain authoritative.
19. Arabic and English localization work.
20. Relevant automated tests pass.

---

20. Execution Instructions for Codex

Implement this feature directly in the existing Lonorabot repository.

Follow this order:

Phase 1 — Inspect

Read the existing delegation contracts, AccountAuthority implementation, approval mechanisms, chat composers, and Web/Mobile UI components.

Phase 2 — Define Integration

Map the three user-facing permission levels to the existing financial authorization and approval infrastructure.

Phase 3 — Implement Shared Logic

Implement the authoritative permission state, transitions, proposal construction, and configuration validation.

Phase 4 — Implement Desktop UI

Integrate the composer selector, popover, advanced configuration dialog, and live summary.

Phase 5 — Implement Mobile Web UI

Adapt the same experience into compact sheets and full-height configuration views.

Phase 6 — Implement Native Mobile UI

Use the native application components and secure device signing workflow.

Phase 7 — Integrate Agent Runtime

Ensure the LLM receives accurate permission context and every financial tool honors the effective authorization.

Phase 8 — Verify

Run the relevant unit, integration, browser, and mobile tests. Validate complete authorization and downgrade flows using simulated financial operations.

Deliver production code, not placeholders.

Preserve the existing financial authority infrastructure and avoid unrelated architectural changes.

Required Final Report

At completion, provide:

1. Implementation summary.
2. Files created and modified.
3. Three-level permission mapping.
4. Advanced customization integration.
5. Desktop UI implementation.
6. Mobile browser implementation.
7. Native mobile implementation.
8. AccountAuthority signing and enforcement integration.
9. Tests executed with actual results.
10. Remaining feature-specific limitations, if any.

Do not claim tests passed unless they were executed successfully.

Do not claim native hardware signing has been verified unless it was tested on the required hardware.

Do not merge or deploy without explicit owner authorization.

Non-Negotiable Final Principle

Build one simple, secure, responsive delegation experience on top of Lonorabot's existing AccountAuthority system.

The user chooses the level of autonomy. Advanced Customization defines the exact financial scope. The LLM independently decides how to work within that scope.

Deliver the complete working implementation across Desktop, Mobile Web, Native Mobile, Agent Runtime, and Financial Authorization.