# Lonora facial geometry refinement

The character keeps the original circular head, dark visor, shell shading, user-selected colors, SVG viewBox and eight-stroke animation engine. The Studio's expression IDs, Arabic labels, selection grid and confirmation flow remain compatible.

## Why the previous expressions looked inconsistent

The pre-refinement `facialExpression` function authored its eyes, mouths, eyebrows and accents with unrelated local dimensions. For example, neutral eyes used a 14-unit stroke, curved eyes used 10 units, ordinary mouths used 8–10 units, but laughing/excited mouths used 16 units. Some sparkle details used 4-unit strokes: after the existing 1.1 glyph scale, these were about 0.49 CSS pixels in a 40px avatar. These differences gave secondary features more visual weight than the eyes and made fine accents disappear at thumbnail sizes.

The baseline is the actual Studio implementation immediately before the canonical-geometry pass, not a screenshot recreation. Its source SHA-256 is `733da6f754f1622c7738cfd272303c9d3bddcf94dbf081b43b8e8201cb5c240c`.

## Original dimensions and common definitions

The source of truth remains `packages/core/src/trading-avatar-motion.js`:

- ViewBox: `22 22 356 356`.
- Shell: center `(200, 200)`, radius `177`.
- Visor: `(78, 123)`, size `244 × 155`, corner radius `77.5`.
- Original idle bar width: `26`; existing glyph scale: `1.1`.

`FACIAL_GEOMETRY` derives the facial safe area, eye and eyebrow anchors, mouth anchor and expression bounds from those dimensions. `FACE_TOKENS` supplies common eye shapes, stroke hierarchy, spacing, optical corrections, small breathing/blinking motion and restrained facial glow. Anchor coordinates are stored before the existing glyph projection; the capture script projects them with the same `GLYPH_SCALE` when drawing alignment guides.

The calibrated hierarchy in the existing 400-unit coordinate space is:

| Token | Derived value |
| --- | ---: |
| Primary eye stroke | `26 × 0.68 = 17.68` |
| Curved eye stroke | `17.68 × 0.8 = 14.144` |
| Secondary mouth stroke | `26 × 0.44 = 11.44` |
| Eyebrow stroke | `26 × 0.32 = 8.32` |
| Accent stroke | `26 × 0.29 = 7.54` |
| Minimum separation | `26 × 0.2 = 5.2` |
| Eye height | Original shortest capsule, `39` |
| Eye half spacing | `(260 − 140) × 0.35 = 42` |

The rendered facial-safe rectangle is `(114.6, 136.95, 170.8, 127.1)`. It stays inside the unchanged visor. Curved eyes and mouths use optical corrections so their perceived center aligns with the shared anchors rather than with the center of their construction circles.

Every preset uses the same geometry and renderer. Vertical and curved eyes use shared visual-weight tokens; neutral, laughing and excited mouths use the same secondary stroke hierarchy; eyebrows and emotion marks remain lighter than the eyes. The original four signal bars and the active-work glyphs remain their own existing state definitions.

## Actual rendered evidence

All screenshots below use the production `markup` and `mount` functions in Chromium at a 1× device scale. They do not use a second set of facial SVGs. Guides are evidence-only overlays and are not part of the application.

- [Original default signal avatar at 256px](visual/avatar-refinement/original-default.png)
- [Original signal raster before](visual/avatar-refinement/original-signal-before.png) and [after](visual/avatar-refinement/original-signal-after.png), verified byte-identical
- [Baseline expressions](visual/avatar-refinement/before-grid.png)
- [Before and after at identical size](visual/avatar-refinement/before-after-grid.png)
- [Shared alignment guides](visual/avatar-refinement/alignment-guides.png)
- [All expressions at 32px](visual/avatar-refinement/expressions-32px.png)
- [All expressions at 40px](visual/avatar-refinement/expressions-40px.png)
- [All expressions at 48px](visual/avatar-refinement/expressions-48px.png)
- [All expressions at 64px](visual/avatar-refinement/expressions-64px.png)
- [All expressions at 96px](visual/avatar-refinement/expressions-96px.png)
- [All expressions at 128px](visual/avatar-refinement/expressions-128px.png)
- [All expressions at 256px](visual/avatar-refinement/expressions-256px.png)
- [Large preview and real-size thumbnails](visual/avatar-refinement/preview-thumbnails.png)
- [Multiple selected shell colors](visual/avatar-refinement/shell-colors.png)
- [Expression switch during animation](visual/avatar-refinement/transition-mid-animation.png)

Full-quality previews are also checked at pixel level for visible white facial features inside the canonical safe area. This caught and corrected an intermediate SVG-filter defect: disabling specular intensity alone produced opaque black output in the final merge. Facial specular content now merges a transparent result, while the original signal rendering retains its previous lighting.

The accompanying [validation record](visual/avatar-refinement/validation.json) records the before/after source hashes, browser version, geometry snapshot and executed rendering assertions. Application-level Studio screenshots and persistence tests are verified separately through the existing authenticated Web/native browser tests.

## Reproducing the evidence

Keep a copy of the engine before editing it, then run:

```bash
node scripts/capture-avatar-refinement.mjs --phase before --before /path/to/before-motion.js
node scripts/capture-avatar-refinement.mjs --phase after --before /path/to/before-motion.js
```

The comparison deliberately requires the actual baseline source. It does not silently substitute the current engine for the old version. `--output` selects an alternative artifact directory. The script checks that the fundamental geometry remains identical, expression changes begin from the displayed shape, transitions animate, the shell and visor stay unchanged, paths remain finite and reduced motion stays still.

## Limits

The screenshots are browser rasterizations at known CSS sizes. At 40px and 64px, manual inspection found readable eyes and mouths, separated eyebrows, balanced laughing/excited mouths and no visible clipping. At 32px, primary expression silhouettes remain visible, but small teal dots and accents naturally lose detail; no browser screenshot can guarantee that every subtle emotion is equally distinct at that size. The token hierarchy keeps primary features dominant without scaling individual features with CSS. Browser captures do not establish physical Android display quality or GPU-specific antialiasing behavior. Existing preference handling still suppresses animation for reduced motion.


## Application integration and changed files

| Area | Files |
| --- | --- |
| Shared geometry, face catalog, motion and contracts | `packages/core/src/trading-avatar-motion.js`, `packages/core/src/trading-avatar-motion.d.ts`, `packages/core/src/avatar-motion.ts` |
| Shared Web renderer | `packages/ui-web/src/trading-avatar.tsx`, `packages/ui-web/src/agent-avatar.tsx` |
| Web Studio and profile/create forms | `apps/web/src/components/ai/AvatarStudio.tsx`, `apps/web/src/components/ai/avatar-studio.css`, `apps/web/src/pages/shell/bot-panel.tsx`, `apps/web/src/pages/shell/bot-settings.tsx` |
| Native Studio and renderer | `apps/mobile/components/avatar-picker.tsx`, `apps/mobile/components/bot-avatar.tsx`, `apps/mobile/app/new.tsx` |
| Existing-language labels | `apps/web/src/i18n/locales/ar/messages.po`, `apps/web/src/i18n/locales/en/messages.po`, `apps/mobile/lib/i18n.ts` |
| Automated regression and visual capture | `tests/web/avatar-motion.test.ts`, `tests/web/avatar-studio.spec.mjs`, `tests/mobile/avatar.spec.mjs`, `scripts/capture-avatar-refinement.mjs` |
| Review artifacts | This report and `docs/visual/avatar-refinement/` |

The pencil-triggered editor supports the existing face/color selection flow, local previews, confirmation and cancellation. Reset restores the original signal face and default violet color. New bot creation also exposes the same editor. Legacy avatar identifiers continue to resolve to signal bars. The original Arabic labels and all sixteen expression IDs remain available. No backend, database, financial-permission or trading-execution source files were changed.

Actual application captures: [Arabic Web Studio](visual/avatar-refinement/web-studio-ar.png), [English Web Studio](visual/avatar-refinement/web-studio-en.png), and [native component at mobile viewport](visual/avatar-refinement/mobile-studio.png). The latter exercises Expo Web; it is not evidence from a physical Android screen. Finite modal opening animations are completed for the settled layout capture, while SVG motion remains the production implementation.

## Verification results

- `bash scripts/build.sh`: passed, including Python checks, resource validation, lint, TypeScript, Web and Expo exports.
- Motion/activity unit tests: **25 passed**. Geometry coverage includes all 256 face-to-face transitions before clipping, gaze extremes, original-shell/visor invariance, original state poses, canonical anchors and stroke weights.
- Web face workflows: both Arabic and English creation, selection, Reset/Cancel/Save, independent appearance persistence, dirty profile preservation, failed-save retry, reload and narrow layout passed. Existing avatar/motion browser checks also passed.
- Native component workflow: selection, cancellation, reset, independent profile appearance persistence/reload, failed-save retry, dirty profile preservation and new bot creation passed through the actual API in an isolated test database.
- Existing general-agent creation and chat/streaming regression checks passed. One 30-second streaming scenario initially timed out during concurrent builds; its isolated rerun passed without application changes.
- The visual capture script verified the original signal avatar raster is byte-identical and all sixteen full-quality previews contain visible white facial pixels inside the canonical safe area.

No live trading or real account operations were used for verification.


## Independent saving, expression reactions and home toolbar

For an existing agent, the Studio **Save** action persists only `avatar` and `color` through the existing update endpoint. It does not submit unsaved profile fields, and the separate profile Save excludes appearance fields so it cannot restore stale values. Failed appearance saves retain the selection and show a retryable error; pending saves reject duplicate submissions and dismissal. New-agent selections are saved into the creation draft until the agent itself is created.

Angry and worried labels/IDs remain stable. Their eyebrow slopes were corrected: angry eyebrows angle down toward the center, while worried eyebrows lift toward the center. Face-specific `idleAvatarPose` and `faceReaction` now give each preset a calm visual temperament, including different gaze, blink, mouth, nod, tilt and recoil behavior. The signal face retains its original full turn. These are local presentation effects, independent of actual agent execution states; active-work glyphs and reduced-motion handling remain intact.

The home view now places search and creation actions in its top toolbar, with no visible Conversations heading or home Settings shortcut. Settings remain available through existing secondary menus. Web and native tests exercise both Arabic and English search and creation entry points. Settled mobile-viewport captures show the [Web home](visual/avatar-refinement/home-web-ar.png) and [native home rendered through Expo Web](visual/avatar-refinement/home-native-ar.png).
