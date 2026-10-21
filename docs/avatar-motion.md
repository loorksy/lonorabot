# Trading avatar integration

The owner-supplied Liquid Candles v6 engine and React component replace the previous
robot/shape avatars. The original standalone gallery is a design reference, not an
application page. No remote images, analytics or services are required.

- `packages/core/src/trading-avatar-motion.js`: supplied dependency-free geometry,
  state choreography and browser controller. Adaptations add complete shared pointer
  cleanup and suspend work while the document is hidden.
- `packages/ui-web/src/trading-avatar.tsx`: supplied React/SVG component, adapted for
  effect cleanup/replay and current prop values. Small avatars use lite rendering;
  the expanded call uses the full liquid/gloss filter.
- `apps/mobile/components/bot-avatar.tsx`: native SVG shell/visor/gloss using the same
  geometry and morph planner. No per-avatar WebView or new native dependency. Native
  rendering omits expensive specular lighting and uses a 30fps ceiling. Small resting
  avatars are still posters; work/call states and larger previews animate.
- `packages/core/src/avatar-motion.ts`: native sampler preserves the current pose
  when interrupted mid-morph. It does not replace the supplied state choreography.

Saved avatar shape values remain readable and are preserved on profile edits. The
new visual is always the trading sphere; obsolete shape selectors were removed.
Saved colours, names, personal-agent badge, and verified Super Bot crown are retained.

## Runtime truth

`avatarState` maps observed work to working, unanswered requests to reviewing, and
voice transport to connecting/listening/speaking/muted/ending/error. Call views use
this mapping on both clients, including the minimized call. General busy indicators
do not pretend to search, execute a trade or succeed. All twenty supplied states
remain available to explicit callers, without playing a fabricated job sequence.
The candles are the avatar's decorative glyph, not broker prices or a price chart.

The browser engine respects reduced motion, off-screen intersection and document
visibility. Native rendering respects reduced motion and application foreground
state. Pointer gaze/tap on web and touch feedback on native do not consume parent
navigation or call actions. The avatar has no financial authority.

## Verification

`pnpm exec tsx --test tests/web/avatar-motion.test.ts` checks all states, finite
geometry, native morph continuity, reduced motion and actual state projection.
Browser coverage checks the installed UI and browser controller lifecycle.
Native Android/iOS smoothness still needs a physical device check; Expo web checks
and TypeScript do not establish physical-device performance.
