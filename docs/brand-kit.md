# Brand Kit — Trading Agent (الهوية البصرية)

The avatar as a glossy 3D sphere, front view: dark visor with four signal bars; the tallest bar is green (the "live signal"). Always on black.

Colors: Background #000000 · Sphere #7776EE (highlight #A7A6FF, shadow #3D3C93) · Visor #0D0D11 · Signal White #F8F8FB · Green #6CF4C4 / #2FD39A

Contents: `logo/` · `web/` (favicon, PWA, manifest, head-snippet.html) · `ios/` (AppIcon.appiconset + Xcode15 Light/Dark/Tinted) · `android/res/` (adaptive + monochrome, notification) · `social/` · `splash/`
Rules: clear space = height of the tallest bar; min size 16 px; don't stretch or recolor the sphere; iOS icons are full-bleed.
Needs your input: app name (wordmark), domain in `head-snippet.html`, name in `site.webmanifest`.

## Lonora integration

Original owner-supplied artwork is used without recolouring or stretching. Web assets
are in `apps/web/public`; native source images are in `apps/mobile/assets/brand`.
Expo generates density-specific Android resources and iOS catalog sizes from these
source images. The iOS light/dark/tinted and Android adaptive/monochrome variants
are configured explicitly. Notification artwork is not enabled because the current
mobile client does not declare an OS notification integration.

Native launcher icons require an installed binary update. Never publish a changed
native fingerprint as an OTA for an older installed runtime. Existing compatible
OTA releases remain available to their own runtimes.
