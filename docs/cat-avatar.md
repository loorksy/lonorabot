# Shared cat avatar and observed activity

The default avatar on Web and native mobile now uses the supplied `index-13.html` matte cat artwork. Old saved shape/color values remain compatible metadata; the old spherical renderer is removed. Financial permissions and verified Super Bot badges are unchanged.

`packages/core/src/cat-avatar.ts` projects all 20 existing signal states onto the original visor. The transparent shell is rendered once from the supplied WebGL geometry and embedded for both clients. `scripts/import-cat-avatar.mjs` reproduces the artwork from the exact source attachment (SHA-256 checked). This avoids creating GPU contexts or WebViews for every chat avatar. It preserves the frontal appearance and animated signals; the demo's free 360-degree rotation and independent ear interactions are not included.

Web supports dark/light shells. Native follows the application's existing dark palette. Small idle/terminal avatars stay still; active avatars animate at up to 30 frames per second. Reduced motion and background visibility stop animation. Artwork needs no network requests.

Turn status displays the agent name, actual observed phase, and a semantic indicator. Existing `turnActivity` projections determine thinking, searching, analyzing, executing, writing, waits, completion and errors. Reconnecting is shown explicitly. No synthetic phase sequence or progress percentage is introduced, and presentation does not gate message submission or SSE consumption.

Validation uses the existing avatar, streaming, native chat-runtime tests and `bash scripts/build.sh`. Native browser tests exercise Expo Web, not a physical Android device. Releases require signed OTA verification against the installed runtime.
