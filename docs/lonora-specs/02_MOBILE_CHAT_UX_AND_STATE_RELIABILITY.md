TITLE:
Fix Lonora Mobile Chat UX, Voice Crash, Conversation Continuity, Inbox Loading, and Approval Timeline

CONTEXT:
We are working on the Lonora project.

This task is based on real problems observed while using the current Android mobile application and the responsive Web application.

This is NOT a request for a UX report.

Inspect the current implementation, reproduce the problems, identify their actual causes, and implement the fixes.

Required workflow:

REPRODUCE
→ TRACE
→ UNDERSTAND
→ FIX
→ INTEGRATE
→ TEST
→ VERIFY ON MOBILE
→ VERIFY ON WEB

Do not stop at an implementation plan.

==================================================
IMPORTANT
==================================================

Several of these problems are related to chat state, scrolling, asynchronous hydration, mobile keyboard behavior, event ordering, and conversation timeline projection.

Do not fix them with isolated hacks.

Inspect the full flow first.

Relevant current areas include, but are not limited to:

apps/mobile/app/thread.tsx
apps/mobile/app/index.tsx
apps/mobile/components/thread-composer.tsx
apps/mobile/components/conversation-row.tsx
apps/mobile/components/trade-approval.tsx
apps/mobile/components/voice-overlay.tsx
apps/mobile/lib/voice-session.tsx

apps/web/src/pages/Shell.tsx
apps/web/src/pages/shell/chat-context.tsx
apps/web/src/hooks/useThreads.ts
apps/web/src/components/trading/TradeApprovals.tsx
apps/web/src/providers/ClientProvider.tsx
apps/web/src/lib/user_error.ts

Also inspect any lower-level APIs, contracts, events, message pagination, voice transport, native audio/WebRTC code, database queries, and thread projections involved.

Do not assume the listed files are the only files that need changes.

==================================================
ISSUE 1 — MOBILE CALL BUTTON CRASHES THE APPLICATION
==================================================

CURRENT BEHAVIOR:

On Android mobile:

1. Open an Agent conversation.
2. Press the phone/call icon in the conversation header.
3. The Lonora application immediately exits/crashes.

This is not an acceptable handled error screen.

The application process appears to terminate or the app closes immediately.

EXPECTED BEHAVIOR:

Pressing the call button must never crash the application.

Expected flow:

Tap Call
 ↓
Validate voice availability
 ↓
Validate microphone permission
 ↓
Validate transport/runtime readiness
 ↓
Start connection
 ↓
Show connecting state
 ↓
Connected call

If voice is unavailable:

Tap Call
 ↓
Show localized recoverable error
 ↓
Application remains alive

Examples:

- microphone permission denied
- voice transport not configured
- WebRTC unavailable
- native audio module unavailable
- server unavailable
- unsupported device/runtime
- connection timeout

All must fail gracefully.

==================================================
VOICE CRASH INVESTIGATION REQUIREMENT
==================================================

Do not guess the cause.

The current mobile conversation calls approximately:

voice.start(agent, thread.id)

through the mobile VoiceSessionProvider.

Because VoiceSession already catches ordinary JavaScript/API errors, an immediate application exit may indicate a lower-level native crash, permission problem, WebRTC/audio initialization issue, or another uncaught lifecycle failure.

Reproduce it on Android.

Inspect:

- JavaScript exception output
- Expo/native logs
- adb logcat when available
- WebRTC initialization
- microphone permission handling
- createVoiceDevice()
- MobileVoiceJoin
- native audio session initialization
- app configuration/plugins
- required Android permissions
- lifecycle teardown
- duplicate connection creation
- race conditions during startup
- background/foreground transitions

Do not hide the crash behind a generic try/catch if the native cause still exists.

Fix the underlying cause.

Add a safe capability check before entering native voice functionality when necessary.

==================================================
ISSUE 2 — OPENING A BOT STARTS AT THE OLDEST MESSAGE
==================================================

CURRENT BEHAVIOR:

When I select a bot and enter its conversation, I often see the beginning/oldest part of the conversation.

I have to manually scroll all the way down to reach the latest message.

This happens repeatedly when reopening conversations.

EXPECTED BEHAVIOR:

Opening an existing conversation should land on the latest conversation state.

Normal behavior:

Bot list
 ↓
Tap bot
 ↓
Load thread
 ↓
Load latest messages
 ↓
Render
 ↓
Position viewport at latest message

The user should immediately see the most recent message.

Do not briefly display message #1 and then slowly jump through the conversation.

==================================================
SCROLL INITIALIZATION
==================================================

The current mobile implementation attempts to call scrollToEnd after message snapshots.

Do not rely on a single requestAnimationFrame or timing assumption.

The initial scroll must happen only when:

- the thread is known
- the initial message batch is loaded
- the FlatList has completed the relevant layout/content-size update

Handle:

- long conversations
- variable message height
- Markdown
- images
- cards
- approvals
- artifacts
- RTL text
- streaming messages

The result must be deterministic.

==================================================
ISSUE 3 — NEW AGENT MESSAGES MUST FOLLOW THE CONVERSATION
==================================================

CURRENT BEHAVIOR:

When the Agent sends a new message, the conversation does not reliably move with the new content.

The user repeatedly has to manually scroll down to see new Agent output.

EXPECTED BEHAVIOR:

If the user is already at or near the bottom:

new message
 ↓
streaming update
 ↓
tool/result update
 ↓
Agent final response

should automatically remain visible.

The chat should follow the live conversation naturally.

However, do NOT forcibly pull the user to the bottom if they intentionally scrolled upward to read old messages.

Implement proper bottom-follow semantics.

==================================================
BOTTOM-FOLLOW STATE
==================================================

Track whether the user is:

AT_BOTTOM

or:

READING_HISTORY

Use an appropriate distance threshold.

For example conceptually:

distanceFromBottom <= threshold
→ pinned to bottom

distanceFromBottom > threshold
→ user is reading history

Do not hardcode a poor value without testing real mobile layouts.

When AT_BOTTOM:

- follow new user messages
- follow Agent streaming
- follow new Agent messages
- follow new relevant cards
- follow WorkingIndicator transitions where appropriate

When READING_HISTORY:

- preserve the current reading position
- do not yank the user downward
- indicate that newer content exists

==================================================
ISSUE 4 — ADD A SCROLL-TO-LATEST BUTTON
==================================================

When the user scrolls upward away from the latest conversation content, show a floating down-arrow button.

Expected behavior:

User scrolls upward
 ↓
distance from bottom exceeds threshold
 ↓
show floating ↓ button

Tap ↓
 ↓
scroll to latest content
 ↓
hide button

The button should also be useful when new messages arrive while the user is reading older messages.

Preferably, if appropriate to the existing design, indicate unseen/new content without making the UI noisy.

The button must not cover:

- the composer
- message actions
- the keyboard
- approval controls

It must work correctly in RTL and LTR.

==================================================
ISSUE 5 — MOBILE KEYBOARD HIDES THE MESSAGE COMPOSER
==================================================

CURRENT BEHAVIOR:

When attempting to type on mobile, the message input/composer can remain below the visible area.

The keyboard appears but the composer is not correctly lifted/resized into view.

The user cannot comfortably see what they are typing.

EXPECTED BEHAVIOR:

The composer must remain visible directly above the system keyboard.

Expected:

Conversation
────────────────────

latest messages

────────────────────
message composer
────────────────────
Android keyboard

The composer should never become trapped behind the keyboard.

==================================================
KEYBOARD REQUIREMENTS
==================================================

Inspect the current:

KeyboardAvoidingView

behavior and Android native window configuration.

The current code has platform-specific behavior that must be verified on real Android behavior rather than assumed correct.

Check:

- Android windowSoftInputMode / adjustResize
- Expo configuration
- SafeAreaView
- keyboard insets
- navigation bars
- gesture navigation
- RTL
- multiline composer growth
- attachment chips
- reply preview
- mention suggestions
- landscape mode if practical

Do not solve this by adding arbitrary fixed bottom padding.

The layout must respond to real keyboard insets.

==================================================
ISSUE 6 — FALSE EMPTY INBOX DURING APPLICATION STARTUP
==================================================

CURRENT BEHAVIOR:

When Lonora starts, the inbox initially appears as if there are no bots.

After a few seconds, the existing bots suddenly appear.

This creates a false state:

"No bots"

when the actual state is:

"Existing bots have not finished loading yet."

EXPECTED BEHAVIOR:

Never render an empty-state conclusion before the first inbox load has completed.

Use explicit states such as:

BOOTSTRAPPING
 ↓
LOADING_INBOX
 ↓
READY_WITH_DATA

or:

READY_EMPTY

The UI must distinguish:

loading

from:

actually empty

==================================================
FIRST-LOAD EXPERIENCE
==================================================

On application startup:

Session bootstrap
 ↓
owner known
 ↓
load inbox data
 ↓
show existing conversations

During loading, use the product's appropriate loading/skeleton state.

Do not flash:

"Create your first agent"

for a user who already has six agents.

If existing architecture supports cached/bootstrap conversation data safely, reuse it.

Do not invent fake local agents just to hide latency.

==================================================
ISSUE 7 — INBOX SHOULD SHOW THE LAST CONVERSATION MESSAGE
==================================================

CURRENT BEHAVIOR:

The mobile inbox primarily shows:

- Agent name
- date
- Agent description/title
- run status
- group member names

It does not consistently behave like a useful conversation inbox.

EXPECTED BEHAVIOR:

Each Agent conversation row should show the latest meaningful message preview.

Example:

Lonora
"تم تنفيذ الصفقة بنجاح..."
3:42

Gold
"ما زلت أراقب مستوى 4095..."
3:39

The row should communicate what happened last in that conversation.

==================================================
LAST MESSAGE PREVIEW REQUIREMENTS
==================================================

For each persistent Agent conversation show:

- Agent name
- avatar
- working state if applicable
- latest meaningful conversation preview
- timestamp of that latest activity

Do not issue an N+1 API request for every Agent if avoidable.

Prefer a proper inbox/conversation projection from the backend if needed.

For example the server may expose enough information to return:

thread_id
agent_id
last_message
last_message_role
last_message_at
unread state if supported
current run state

Use the current architecture rather than blindly adding this exact contract.

==================================================
INBOX ORDERING
==================================================

The inbox should represent conversations, not merely an Agent registry.

Normally, the most recently active conversation should appear toward the top unless there is an existing explicit ordering/pinning system that must be preserved.

Inspect Rakazo-style semantics already present in Lonora before changing ordering rules.

Do not destroy intentional manual ordering if one exists.

==================================================
ISSUE 8 — WEB SHOWS STALE GENERIC REQUEST ERRORS AFTER RETURNING
==================================================

CURRENT BEHAVIOR:

On responsive Web:

1. Use Lonora.
2. Leave the website/browser.
3. Return later.
4. The conversation may show one or multiple copies of:

"The request could not be completed. Try again."

Arabic:

"تعذر إكمال الطلب. أعد المحاولة."

Sometimes multiple retry/error blocks appear even though durable conversation state still exists.

EXPECTED BEHAVIOR:

Returning to the website should reconcile with the durable backend state.

A temporary disconnect while the browser was away must not automatically become a permanent conversation error.

Expected reconnect flow:

Browser becomes active
 ↓
restore session
 ↓
reconnect event stream
 ↓
fetch durable thread state
 ↓
fetch Runs
 ↓
reconcile transient local state
 ↓
render canonical current state

==================================================
WEB ERROR INVESTIGATION
==================================================

Identify the actual request producing the generic error.

Do not simply suppress all errors.

Inspect:

- session restoration
- event-stream reconnect
- visibility changes
- stale fetches
- useThreads
- ClientProvider revisions
- response streaming
- run recovery
- archived/finished Runs
- duplicated error state
- refresh races
- expired transient request state

A real unresolved failure should remain visible.

A stale network error that has already recovered should clear automatically.

==================================================
ERROR DEDUPLICATION
==================================================

Do not render the same underlying failure three times.

Error presentation should have identity.

For example, conceptually:

error source
+
thread
+
run/request identity

should prevent duplicate banners for the same problem.

Do not implement this exact schema if the runtime already provides event/run IDs suitable for the job.

==================================================
ISSUE 9 — TRADE APPROVAL CARDS BREAK CHAT CHRONOLOGY
==================================================

CURRENT BEHAVIOR:

When the Agent sends a trading approval card:

User sees approval card
 ↓
Approve / Reject
 ↓
card remains permanently at the bottom of the chat

Then when new Agent messages arrive, they appear ABOVE the approval card.

This breaks conversation chronology.

The approval card effectively becomes a permanent footer.

This happens because the current UI architecture renders approvals separately from ordinary timeline messages.

The mobile thread currently places TradeApprovalCard content in the FlatList footer.

The Web conversation also renders TradeApprovals as trailing conversation content.

This architecture causes:

new message
 ↓
message appears
 ↓
old approval card still remains after it

which is visually incorrect.

==================================================
EXPECTED APPROVAL TIMELINE
==================================================

Trade approval is part of the conversation timeline.

It must appear at the point where the approval was requested.

Example:

Agent:
"I am ready to execute."

Trading Approval Card
[Approve] [Reject]

User presses Approve.

Trading Approval Card
✓ Approved
or
✓ Executed / confirmed result

Agent:
"The position was opened successfully."

The new Agent message MUST appear after the resolved card.

Not above it.

==================================================
APPROVAL CARD LIFECYCLE
==================================================

PENDING:

Show actionable approval card in timeline.

APPROVED:

Replace/update the same timeline item.

Example:

✓ Approved — awaiting broker result

COMPLETED:

Update/collapse the same item to a resolved state.

Example:

✓ Executed
XAUUSDm
Buy 1.00
Broker ticket ...

REJECTED:

Update/collapse the card:

✕ Rejected

CANCELLED:

Update/collapse appropriately.

The card should not be duplicated.

==================================================
CHRONOLOGICAL TIMELINE
==================================================

Do not keep approvals as an unconditional conversation footer.

Create a unified chronological projection for conversation items.

Possible timeline item types include:

Message
Streaming response
Trade approval
Trade result
System/recovery item
Tool activity where product design requires it

Do not blindly adopt this exact type hierarchy if the existing event model provides a better abstraction.

The important invariant is:

Conversation items must preserve causal chronological order.

==================================================
APPROVAL ANCHORING
==================================================

Investigate whether current TradeApproval records contain enough information to determine their correct location.

Inspect:

- thread_id
- run_id if available
- created_at
- request creation event
- message sequence
- durable event sequence

If created_at alone is insufficient for deterministic ordering, add a proper durable anchor such as:

message_seq
event_seq
run/turn anchor

or another equivalent mechanism consistent with the existing database/event architecture.

Do not create fragile client-only ordering based purely on fetch arrival time.

==================================================
MOBILE AND WEB MUST AGREE
==================================================

Conversation chronology semantics should be shared.

Do not implement:

Mobile ordering model A

and:

Web ordering model B

Both clients should derive the same logical timeline from the same server contracts/state.

==================================================
ISSUE 10 — LIVE STREAMING MUST PARTICIPATE IN THE SAME SCROLL MODEL
==================================================

The Agent may stream partial text while working.

Streaming content should behave as the current end of the conversation.

If the user is pinned to the bottom:

stream token
 ↓
viewport follows naturally

If the user is reading history:

stream continues
 ↓
viewport remains stable
 ↓
scroll-to-latest indicator appears

When the stream becomes a durable Message, replacing the streaming projection must not:

- jump the screen
- duplicate the content
- reset scroll position
- create two messages

==================================================
SCROLL POSITION WHEN LOADING OLDER MESSAGES
==================================================

When the user requests older history:

Current visible message
 ↓
prepend older messages
 ↓
Current visible message remains visually anchored

Do not jump to the oldest newly loaded message.

Do not automatically return to bottom merely because old history was fetched.

This behavior is important for long-lived persistent Agents.

==================================================
NAVIGATION CONTINUITY
==================================================

When:

Conversation A
 ↓
Back
 ↓
Inbox
 ↓
Conversation A again

the user should return to a sensible latest/current position.

At minimum, reopening should show the latest conversation.

If preserving recent scroll position for deliberate history reading is already supported cleanly, preserve it only when it does not conflict with the user's expectation that normal conversation opening goes to the latest message.

==================================================
DO NOT CREATE CLIENT-ONLY SOURCE OF TRUTH
==================================================

The backend remains the durable source of truth.

Mobile/Web may keep UI state such as:

- scroll position
- isNearBottom
- keyboard state
- temporary error display
- animation state

But they must not invent durable conversation ordering independently from server data.

==================================================
PERFORMANCE REQUIREMENTS
==================================================

Do not fix the inbox by making:

1 request for agents
+
1 request per agent for thread
+
1 request per agent for last message

if a backend projection can provide the information efficiently.

Avoid N+1 behavior.

Long conversation rendering should remain performant.

Use FlatList virtualization correctly on native mobile.

Do not disable virtualization simply to make scrolling easier.

==================================================
RTL REQUIREMENTS
==================================================

All fixes must work correctly in Arabic RTL.

Verify:

- latest-message preview
- timestamps
- down-arrow
- composer
- keyboard
- approval cards
- symbol strings
- broker IDs
- mixed Arabic + XAUUSDm
- errors

Technical identifiers should remain directionally isolated where necessary.

==================================================
ACCESSIBILITY
==================================================

The new scroll-to-latest button and all call/error/approval controls need accessibility labels.

Do not rely on icon shape alone.

==================================================
ERROR HANDLING RULE
==================================================

Do not convert every error into:

"The request could not be completed. Try again."

Preserve stable backend error codes and map known errors to useful localized messages.

Unknown errors may use the generic fallback.

==================================================
TESTING REQUIREMENTS
==================================================

Add automated coverage where practical for:

1. Inbox does not show false empty state before initial load.

2. Inbox row uses last meaningful message preview.

3. Opening a populated thread reaches latest message.

4. New message autoscrolls while user is near bottom.

5. New message does NOT force-scroll while user is reading history.

6. Scroll-to-latest control appears when away from bottom.

7. Scroll-to-latest control returns to newest content.

8. Streaming follows bottom correctly.

9. Loading older history preserves viewport.

10. Approval card is positioned chronologically.

11. Resolved approval remains in its timeline position.

12. New messages appear after the resolved approval.

13. Duplicate approval rendering does not occur.

14. Keyboard/composer layout does not regress.

15. Web recovered connection clears stale transient errors.

16. Repeated equivalent Web errors are not duplicated.

17. Call startup failure is handled without terminating the app.

18. Permission denial is recoverable.

19. Voice unavailable state is recoverable.

==================================================
REAL DEVICE / EMULATOR VERIFICATION
==================================================

The call crash and keyboard issue cannot be considered fixed by TypeScript compilation alone.

Verify on Android runtime.

At minimum test:

- open app
- inbox load
- open long conversation
- initial latest position
- scroll upward
- receive/send new message
- use down arrow
- open keyboard
- type multiline Arabic
- dismiss keyboard
- press call
- deny microphone permission
- allow microphone permission
- start voice if runtime is configured
- background/foreground behavior
- approve/reject trade card
- receive subsequent Agent message

Capture native crash logs if voice still exits the process.

==================================================
VISUAL ACCEPTANCE FLOW
==================================================

The final mobile experience should feel approximately like:

Launch Lonora
 ↓
Loading state only if necessary
 ↓
Inbox immediately resolves to existing Agents
 ↓
Each Agent shows latest message preview
 ↓
Tap Agent
 ↓
Latest conversation visible
 ↓
Composer visible
 ↓
Keyboard opens
 ↓
Composer remains above keyboard
 ↓
Agent replies
 ↓
Chat follows automatically
 ↓
User scrolls upward
 ↓
Chat stops auto-following
 ↓
Floating ↓ appears
 ↓
Tap ↓
 ↓
Return to latest message

And for trading:

Agent requests execution
 ↓
Approval Card appears in timeline
 ↓
Approve
 ↓
Same card becomes Approved / Processing
 ↓
Broker result arrives
 ↓
Same card becomes resolved
 ↓
Agent's next message appears BELOW it

And for Web reconnect:

Leave website
 ↓
Return later
 ↓
Reconnect
 ↓
Reconcile durable state
 ↓
No stale duplicated generic errors

==================================================
DO NOT PAPER OVER THE ISSUES
==================================================

Do not:

- add arbitrary setTimeout calls until scroll "usually works"
- always force scrollToEnd regardless of user position
- hide all errors
- remove approval cards after approval without preserving meaningful audit state
- use fake last-message previews
- hardcode keyboard offsets for one Android device
- catch native voice failure without fixing its cause
- introduce one API call per Agent if avoidable
- duplicate separate timeline rules for Mobile and Web

==================================================
IMPLEMENTATION ORDER
==================================================

A sensible dependency order is:

1. Reproduce and diagnose voice crash.
2. Define canonical conversation timeline behavior.
3. Fix approval/event chronological projection.
4. Fix initial thread positioning.
5. Implement bottom-follow state.
6. Implement scroll-to-latest control.
7. Fix keyboard/composer behavior.
8. Fix inbox initial-loading state.
9. Add last-message inbox projection.
10. Fix Web reconnect/stale error reconciliation.
11. Verify RTL/mobile behavior.
12. Run full tests and builds.

If investigation reveals a better dependency order, use it.

==================================================
QUALITY GATES
==================================================

Run all relevant repository checks.

At minimum, where applicable:

pytest
ruff
pyright

pnpm lint
pnpm typecheck
pnpm build

Mobile:

Expo/React Native type checks
Android bundle/export checks
existing mobile tests

Also run any repository-specific checks already configured.

Do not claim the mobile crash is fixed without runtime verification.

==================================================
DEFINITION OF DONE
==================================================

This task is complete only when:

- Pressing the mobile call button no longer crashes/exits the app.
- Voice startup failures are recoverable UI states.
- Existing conversations open at the latest message.
- New messages auto-follow when the user is at the bottom.
- User scrolling upward disables forced auto-follow.
- A scroll-to-latest arrow appears when appropriate.
- The composer remains visible above the Android keyboard.
- Startup no longer flashes a false "no agents" state.
- Inbox rows show the latest conversation message.
- Inbox activity timestamps reflect the latest conversation activity.
- Web returning/reconnecting does not show stale generic request errors.
- Equivalent Web errors are not duplicated.
- Trade approval cards are part of chronological chat history.
- Approved/rejected/completed cards update in place.
- New messages appear below older approval cards.
- Streaming and durable messages do not duplicate or jump.
- Loading older messages preserves viewport position.
- RTL remains correct.
- Mobile and Web use consistent timeline semantics.
- Relevant tests pass.
- Android runtime verification passes.

==================================================
GIT WORKFLOW
==================================================

Work on a dedicated branch.

Do not merge into main.

Use logical commits.

Possible themes:

fix(mobile): prevent voice startup crash
fix(chat): implement deterministic bottom-follow behavior
feat(chat): add scroll-to-latest control
fix(mobile): keep composer above Android keyboard
fix(inbox): distinguish loading from empty state
feat(inbox): show latest conversation preview
fix(chat): project approvals chronologically
fix(web): reconcile stale reconnect errors
test(chat): cover timeline and scrolling behavior

Use commit names appropriate to the actual repository.

==================================================
FINAL RESPONSE
==================================================

Do not return a long design report before implementing.

Implement first.

When finished, return a concise completion report containing only:

- Branch
- Commits
- Root cause of the mobile call crash
- Main files changed
- Chat scrolling behavior implemented
- Keyboard fix implemented
- Inbox loading/preview changes
- Approval timeline fix
- Web reconnect/error fix
- Android verification performed
- Tests/build checks that passed
- Any real remaining blocker

If any issue is not actually fixed, state that explicitly.

Do not mark the task complete based only on static analysis.

==================================================
FINAL PRINCIPLE
==================================================

Lonora is a persistent conversational Agent product.

The user should never have to fight the conversation UI.

The experience should behave as a continuous conversation:

latest state
+
stable scrolling
+
visible composer
+
correct chronological events
+
reliable reconnect
+
no false empty states
+
no application crashes

Fix the underlying state and lifecycle architecture, not only the visible symptoms.