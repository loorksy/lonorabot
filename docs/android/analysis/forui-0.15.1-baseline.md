# forui 0.15.1 baseline

Target: Lonora Android (`apps/android`, pinned `forui: 0.15.1`).

This document records what forui 0.15.1 does when nothing is overridden. The values come from
reading the package source. It then lists how Lonora's theme (`apps/android/lib/design/theme.dart`)
changes those defaults (§6). Every value not on that list stays at the forui default (§7).

forui is MIT-licensed and is a declared dependency of the Lonora app.

## 0. Labels, sources and method

| Label | Meaning in this document |
|---|---|
| **VERIFIED** | Read from forui/Flutter source (path:line given) or from Lonora's theme code. |
| **INFERRED** | Derived from verified facts: arithmetic on forui defaults or a layout reconstruction. The reasoning is stated. |

| Source | Path |
|---|---|
| forui 0.15.1 (the baseline) | `~/.pub-cache/hosted/pub.dev/forui-0.15.1/` (written `F/` below; `F/…` means `…/forui-0.15.1/lib/src/…`) |
| forui_assets 0.15.0 | `~/.pub-cache/hosted/pub.dev/forui_assets-0.15.0/` (`assets/lucide.ttf`, MD5 `0b880b53…`) |
| Flutter SDK used for Cupertino/Material internals | `/opt/flutter` 3.47.9 (Lonora's toolchain) |
| Lonora theme | `apps/android/lib/design/theme.dart`, `tokens.dart` and `components/` |

Method: I stripped doc comments and read each widget's `*Style.inherit(...)` constructor, its
`build` method and any animation or gesture code. Sizes marked "intrinsic" are arithmetic on those
defaults (INFERRED, exact up to Flutter text-layout rounding).

## 1. Summary

1. **Some 0.15.1 defaults are recent (§2).** The press curves, the popover and tooltip scale, the
   hover formula and the text-field padding differ in earlier releases. Re-read §3–5 after any
   change of the forui pin.
2. **forui has no haptics on press (VERIFIED).** `FTappable` never calls `HapticFeedback`. The only
   haptics in forui are `HapticFeedback.selectionClick()` on each `FPicker` wheel step
   (`F/widgets/picker/picker_wheel.dart:165`) and `CupertinoSwitch`'s `lightImpact`, which fires on
   iOS only (`/opt/flutter/.../cupertino/switch.dart:657-667`). A dismiss attempt on a
   non-dismissible barrier plays `SystemSound.alert` (`F/foundation/barrier.dart:174`). Lonora adds
   none by default: `LnTappable` fires `selectionClick` / `mediumImpact` only with `haptic: true`.
3. **Lonora's floating tab bar is a custom widget, not `FBottomNavigationBar` (VERIFIED).** forui's
   bar is full-width, has a top border and no radius, uses `Expanded` items with 10 dp labels, and
   has no selected indicator. In `FScaffold.footer` it also reserves height, so content cannot
   scroll under it (`F/widgets/scaffold.dart:268`). Lonora's bar
   (`lib/design/components/floating_tab_bar.dart`) is a 62 dp stadium with a sliding highlight pill
   and a detached 62 dp action circle, overlaid in a `Stack`.
4. **The global radius is a lerped 8 (VERIFIED).** `FStyle.borderRadius` is
   `FLerpBorderRadius.all(8, min: 24)`. It scales the radius down on elements smaller than 24 dp, so
   a 16 dp checkbox gets 2.7 dp. Lonora replaces it with a plain 24, which every forui widget that
   reads `style.borderRadius` inherits (§6 row 13).
5. **`FStyle.shadow` only reaches `FPopover` (VERIFIED by grep).** `FCard` paints no shadow at all.
   Lonora's card and chrome shadows are set on its own decorations (`LnThemeData.cardShadow` /
   `chromeShadow`).
6. **Lonora's overrides are few (§6).**
   - Colour roles from Lonora's palette: neutral ink `#1F1F1F`, secondary text at 60 % of the ink,
     hairline borders at black 6 %.
   - The platform font instead of Inter, with Lonora's line heights and tracking on `xs`–`xl`.
   - Page gutter 16, 24 dp ambient icons, global radius 24, the card shadow on `FStyle.shadow`.
   - 48 dp stadium block buttons whose disabled look is a 6 % fill with a 30 % ink label.
   - Translucent dividers and field borders, a visible dark off switch, top-centred inverse toasts.

   Everything else stays at the forui default (§7).

## 2. Version notes

Lonora pins 0.15.1. These defaults are recent, so they move with the pin (VERIFIED against the
pub.dev archives of 0.12.0–0.15.1):

| Item | 0.15.1 | Since |
|---|---|---|
| `FTappable` bounce | 1.0→0.97, down 100 ms `easeOutQuart`, up 120 ms `easeOutCubic` | 0.13.0 (0.12.0: 100 ms linear both ways) |
| Hover/pressed colour of filled buttons | HSL lightness shift (`hoverLighten` 0.075 / `hoverDarken` 0.05, `F/theme/colors.dart:155-183`) | 0.15.0 (earlier: c @ `enabledHoveredOpacity` 0.9 over background) |
| `FPopover` animation | 150 ms, scale 0.80→1, `easeOutCubic` / `easeInCubic` | 0.13.0 (0.12.0: 100 ms, 0.95→1) |
| `FTooltip` animation | 100 ms, scale 0.80→1 | 0.13.0 (0.12.0: 0.95→1) |
| `FTextField.contentPadding` | 10 × 10 | 0.15.0 (0.14.x: h 14, v 10; earlier: 14 × 14) |
| `showFDialog` / `FDialog` entrance animation, `FItem` / `FItemGroup`, toast swipe-to-dismiss | present | 0.13.0 |

The `FThemes` colours, `FStyle` literals, `FTypography` scale, `FButtonContentStyle`, header, card,
bottom-nav and sheet timings are identical from 0.12.0 to 0.15.1 (0.15.1 only moves a constant in
`typography.dart`). `FTappable`'s pressed-state delay is 200 ms throughout.

## 3. Theme layer

### 3.1 `FColors` (`F/theme/colors.dart`)

Roles: `brightness`, `systemOverlayStyle`, `barrier`, `background`, `foreground`, `primary`,
`primaryForeground`, `secondary`, `secondaryForeground`, `muted`, `mutedForeground`, `destructive`,
`destructiveForeground`, `error`, `errorForeground`, `border`. Factors: `hoverLighten = 0.075`,
`hoverDarken = 0.05`, `disabledOpacity = 0.5` (`:155-157`). VERIFIED.

| Formula | Definition (VERIFIED) |
|---|---|
| `disable(fg, [bg])` (`:184`) | `alphaBlend(fg @ disabledOpacity, bg ?? background)` |
| `hover(c)` (`:168`) | HSL. If L > 0.5, darken by `hoverDarken × (1 + (0.5 − (1−L))/0.5)`; otherwise lighten by `hoverLighten × (1 + (0.5 − L)/0.5)`. Colours near black or white move more. |

Derived values for zinc light (INFERRED by exact arithmetic on the formulas above):

| Derived value | Result |
|---|---|
| `disable(primary)` | `#8C8C8D` |
| Label of a disabled primary button | `#C3C3C3` |
| `hover(primary)` | `#38383F` |
| `disable(secondary)` | `#FAFAFA` |
| Label of a disabled secondary button | `#89898A` |
| `hover(secondary)` | `#DADADE` |
| `disable(foreground)` (unselected bottom-nav item, disabled header action) | `#848485` |
| `disable(border)` | `#F2F2F3` |

### 3.2 `FThemes` presets (`F/theme/themes.dart`)

All 9 presets are VERIFIED. In every light preset `barrier` = `0x33000000` and `background` = `#FFFFFF`.
In every dark preset `barrier` = `0x7A000000`.

| Preset | foreground | primary / on | secondary / on | muted / mutedFg | destructive / on | error / on | border |
|---|---|---|---|---|---|---|---|
| zinc light | `09090B` | `18181B` / `FAFAFA` | `F4F4F5` / `18181B` | `F4F4F5` / `71717A` | `EF4444` / `FAFAFA` | `EF4444` / `FAFAFA` | `E4E4E7` |
| zinc dark (bg `09090B`) | `FAFAFA` | `FAFAFA` / `18181B` | `27272A` / `FAFAFA` | `27272A` / `A1A1AA` | `7F1D1D` / `FAFAFA` | `7F1D1D` / `FAFAFA` | `27272A` |
| slate light | `020817` | `0F172A` / `F8FAFC` | `F1F5F9` / `0F172A` | `F1F5F9` / `64748B` | `EF4444` / `F8FAFC` | `EF4444` / `F8FAFC` | `E2E8F0` |
| slate dark (bg `020817`) | `F8FAFC` | `F8FAFC` / `0F172A` | `1E293B` / `F8FAFC` | `1E293B` / `94A3B8` | `7F1D1D` / `F8FAFC` | `7F1D1D` / `F8FAFC` | `1E293B` |
| **red light** | `09090B` | `DC2626` / `FEF2F2` | **`F5F5F5` / `171717`** | **`F5F5F5`** / `71717A` | `EF4444` / `FAFAFA` | `EF4444` / `FAFAFA` | **`E5E5E5`** |
| red dark (bg `0A0A0A`) | `FAFAFA` | `DC2626` / `FEF2F2` | `262626` / `FAFAFA` | `262626` / `A3A3A3` | `7F1D1D` / `FEF2F2` | `7F1D1D` / `FEF2F2` | `262626` |
| rose light | `09090B` | `E11D48` / `FFF1F2` | `F4F4F5` / `18181B` | `F4F4F5` / `71717A` | `EF4444` / `FAFAFA` | `EF4444` / `FAFAFA` | `E4E4E7` |
| rose dark (bg `0C0A09`) | `F2F2F2` | `E11D48` / `FFF1F2` | `27272A` / `FAFAFA` | `262626` / `A1A1AA` | `7F1D1D` / `FEF2F2` | `7F1D1D` / `FEF2F2` | `27272A` |
| orange light | `0C0A09` | `F97316` / `FFF1F2` | `F5F5F4` / `1C1917` | `F5F5F4` / `78716C` | `EF4444` / `FAFAF9` | `EF4444` / `FAFAF9` | `E4E4E7` |
| orange dark (bg `0C0A09`) | `FAFAF9` | `EA580C` / `FAFAF9` | `292524` / `FAFAF9` | `292524` / `A8A29E` | `DC2626` / `FAFAF9` | `7F1D1D` / `FAFAF9` | `292524` |
| green light | `09090B` | `16A34A` / `FFF1F2` | `F4F4F5` / `18181B` | `F4F4F5` / `71717A` | `EF4444` / `FAFAFA` | `EF4444` / `FAFAFA` | `E4E4E7` |
| green dark (bg `0C0A09`) | `F2F2F2` | `22C55E` / `052E16` | `27272A` / `FAFAFA` | `262626` / `A1A1AA` | `7F1D1D` / `FEF2F2` | `7F1D1D` / `FEF2F2` | `27272A` |
| blue light | `020817` | `2563EB` / `F8FAFC` | `F1F5F9` / `0F172A` | `F1F5F9` / `64748B` | `EF4444` / `F8FAFC` | `EF4444` / `F8FAFC` | `E2E8F0` |
| blue dark (bg `020817`) | `F8FAFC` | `3B82F6` / `0F172A` | `1E293B` / `F8FAFC` | `1E293B` / `94A3B8` | `7F1D1D` / `F8FAFC` | `7F1D1D` / `F8FAFC` | `1E293B` |
| yellow light | `0C0A09` | `FACC15` / `422006` | `F5F5F4` / `1C1917` | `F5F5F4` / `78716C` | `EF4444` / `FAFAF9` | `EF4444` / `FAFAF9` | `E7E5E4` |
| yellow dark (bg `0C0A09`) | `FAFAF9` | `FACC15` / `422006` | `292524` / `FAFAF9` | `292524` / `A8A29E` | `7F1D1D` / `FAFAF9` | `7F1D1D` / `FAFAF9` | `292524` |
| violet light | `030712` | `7C3AED` / `F9FAFB` | `F3F4F6` / `111827` | `F3F4F6` / `6B7280` | `EF4444` / `F9FAFB` | `EF4444` / `F9FAFB` | `E5E7EB` |
| violet dark (bg `030712`) | `F9FAFB` | `6D28D9` / `F9FAFB` | `1F2937` / `F9FAFB` | `1F2937` / `9CA3AF` | `7F1D1D` / `F9FAFB` | `7F1D1D` / `F9FAFB` | `1F2937` |

In light presets `systemOverlayStyle` is `SystemUiOverlayStyle.dark` and in dark presets `.light`.
The fallback when no `FTheme` ancestor exists is `FThemes.zinc.light` (`F/theme/theme.dart` doc and
lookup). All VERIFIED.

### 3.3 `FTypography` (`F/theme/typography.dart:107-120`, VERIFIED)

The default family is `packages/forui/Inter`. `inherit` sets `color: colors.foreground`. `height` is a
multiplier. No weight or letter-spacing is set on any step.

| Step | xs | sm | base | lg | xl | xl2 | xl3 | xl4 | xl5 | xl6 | xl7 | xl8 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| size | 12 | 14 | 16 | 18 | 20 | 22 | 30 | 36 | 48 | 60 | 72 | 96 |
| height | 1.0 | 1.25 | 1.5 | 1.75 | 1.75 | 2.0 | 2.25 | 2.5 | 1.0 | 1.0 | 1.0 | 1.0 |
| line (dp) | 12 | 17.5 | 24 | 31.5 | 35 | 44 | 67.5 | 90 | 48 | 60 | 72 | 96 |

`FTheme.build` wraps its subtree in `DefaultTextStyle(typography.base, color: foreground)`
(`F/theme/theme.dart`, VERIFIED). `scale(sizeScalar)` multiplies sizes only.

### 3.4 `FStyle` (`F/theme/style.dart:52-74`, VERIFIED)

| Field | Default | Consumed by (grep, VERIFIED) |
|---|---|---|
| `borderRadius` | `FLerpBorderRadius.all(Radius.circular(8), min: 24)` (`:57`) | most decorated widgets |
| `borderWidth` | 1 | text-field border, tile group, divider width, badge outline, popover, sidebar |
| `pagePadding` | `EdgeInsets.symmetric(vertical: 8, horizontal: 12)` (`:59`) | `FHeader` (both styles, `bottom: 15`), `FScaffold.childPadding` (`top/bottom 0`) only |
| `shadow` | `[BoxShadow(0x0D000000, offset (0,1), blur 2)]` (`:60`) | `FPopoverStyle.decoration` only (`F/widgets/popover.dart:554`) |
| `iconStyle` | `IconThemeData(color: primary, size: 20)` (`:71`) | applied as ambient `IconTheme` by `FScaffold` |
| `focusedOutlineStyle` | colour `primary`, radius 8, width 1, spacing 3 (`F/foundation/focused_outline.dart:101`) | all focusable widgets |
| `formFieldStyle` | label `sm w600 primary` (error: `error`; disabled: `disable(primary)`); description `sm mutedForeground`; error `sm w600 error` (`F/theme/form_field_style.dart`) | labels of all fields |
| `tappableStyle` | `FTappableStyle()` (§4.1) | all tappables |

`FLerpBorderRadius` (`F/foundation/border_radius.dart`, VERIFIED). For a rect whose shorter side `d` is at
least 24 the radius is 8. For `d < 24` the radius is `8 × (1 − d/24)`. Examples (INFERRED arithmetic):
16 dp checkbox → 2.67, 10 dp linear progress → 4.67. The radius jumps from ≈0 to 8 at d = 24. A plain
`BorderRadius` loses this behaviour.

`FBreakpoints`: sm 640, md 768, lg 1024, xl 1280, xl2 1536. `toApproximateMaterialTheme()` is
`@experimental`. It maps the colour roles to a Material `ColorScheme`, sets `NoSplash`, and gives
cards, chips, pickers and nav indicators the forui radius. VERIFIED.

## 4. Interaction primitives

### 4.1 `FTappable` (`F/foundation/tappable.dart`, VERIFIED)

| Aspect | 0.15.1 behaviour |
|---|---|
| Press scale | `ScaleTransition` with `bounceTween` 1.0→**0.97** (`:517`). It starts on **pointer-down**, not on tap acceptance (`:323`). It reverses on pointer-up, or when the pointer moves outside the box (`:334`). |
| Curves / durations | Down **100 ms `easeOutQuart`**. Up **120 ms `easeOutCubic`** (`:561-564`). |
| `WidgetState.pressed` | Set **200 ms** after pointer-down, only if still pressed (`pressedEnterDuration`, `:559`). Cleared 0 ms after pointer-up (`pressedExitDuration` zero). A quick tap therefore bounces without any pressed colour. |
| Gesture | `GestureDetector` for tap, long-press, secondary tap and secondary long-press. A separate `Listener` drives the bounce so it never competes in the gesture arena. Default `HitTestBehavior.translucent`. Enter activates when `onPress` is set. |
| Semantics | `button: true`, `container: true`, `enabled` = has any callback, `selected`. |
| Cursor | `MouseCursor.defer` (0.15 change). |
| Haptics / sound | **None.** |
| Variants | `FTappable.static` (no bounce). Widgets that disable the bounce with `noBounceTween`: checkbox, radio, accordion, breadcrumb, tile and item (tile and item also use `pressedEnter 0`, `pressedExit 25 ms`). |

### 4.2 Focus outline

Painted only while focused: inflated by `spacing` 3, width 1, colour primary, radius 8. The checkbox
uses radius 4 and the radio is circular. VERIFIED. This is not relevant on touch unless a hardware
keyboard is attached.

## 5. Widget baselines (0.15.1)

"Intrinsic" sizes are INFERRED arithmetic on the VERIFIED defaults. Colours are `FColors` roles.

### 5.1 Layout chrome

| Widget | Defaults (VERIFIED, file) | Intrinsic (INFERRED) |
|---|---|---|
| `FScaffold` (`widgets/scaffold.dart`) | bg `background`, `childPad: true` → padding h 12 (pagePadding without vertical), `footerDecoration` top border `border`/1, `resizeToAvoidBottomInset: true`. It wraps `FSheets` + `FToaster` + `IconTheme(style.iconStyle)`. **Layout: the footer reserves height. The body gets `maxHeight − max(viewInsets.bottom, footerHeight)` (`:268`), so content never scrolls under the footer.** | — |
| `FHeader` (root) (`widgets/header/header.dart:107-120`, `root_header.dart`) | title `xl3` 30 **w700 height 1**, `foreground`, 1 line, fade overflow; padding `L12 T8 R12 B15`; suffix actions with `actionSpacing` 10; `SafeArea(bottom: false)`; optional `backgroundFilter`; no decoration | 8 + 30 + 15 = **53** + top inset |
| `FHeader.nested` | title `xl` 20 **w600 height 1**, centred (`titleAlignment = center`) with 10 h padding; prefixes/suffixes in a `Stack`; same padding | 8 + max(20, 25) + 15 = **48** + inset |
| `FHeaderAction` (`header_action.dart`) | `FTappable` (with bounce) around a **bare icon**: `IconTheme` size **30** (root) / **25** (nested), colour `foreground`, disabled `disable(foreground)`. No container, fill, border or circle. `.back` = `FIcons.arrowLeft`, `.x` = `FIcons.x`. | icon box only |
| `FBottomNavigationBar` (`bottom_navigation_bar.dart:45-80,185-200`) | decoration: top border `border` (1), colour `background`, no radius, no shadow; `padding` all **5**, bottom + **⅔ × viewPadding.bottom**; `Row(spaceAround)` of **`Expanded`** items; optional `backgroundFilter` (`BackdropFilter` behind) | — |
| `FBottomNavigationBarItem` (`bottom_navigation_bar_item.dart:135-160`) | `FTappable` (bounce, opaque hit-test); padding all **5**; `Column` spacing **2**; icon **24**, selected `primary` / unselected `disable(foreground)`; **label required**, `base` with fontSize **10** (line 15), same colours, ellipsis; no selected indicator | item 5+24+2+15+5 = **51**; bar 5+51+5 = **61** + ⅔ inset |
| `FSidebar` (`widgets/sidebar/*`) | a **static** side panel in `FScaffold.sidebar` (no slide or drawer motion); width 250; header pad T16, content V12, footer B16; end border. Items: padding h12 v10, icon 16, text `base`, selected/hover bg `hover(secondary)`, radius 8, icon spacing 8, expand 200 ms `easeOutCubic` / collapse 150 ms `easeInCubic`, children indent L26 T2 | — |
| `FResizable` (`widgets/resizable/*`) | divider width 0.5 with a grip thumb (`FIcons.gripVertical/Horizontal`, height 20); hit region **60** on touch / 10 elsewhere; resize step 0.5 % | — |

### 5.2 Buttons and taps

| Widget | Defaults (VERIFIED) | Intrinsic (INFERRED) |
|---|---|---|
| `FButton` (`widgets/button/*`) | Variants: **primary** (default), **secondary**, **destructive**, **outline**, **ghost**. There are **no size variants in 0.15.1** (`FButtonStyles` has exactly these 5 fields). Filled variants: bg = role colour, hovered or pressed → `hover(c)`, disabled → `disable(c)`. Outline: 1 dp `border` and transparent; hovered or pressed → `secondary` fill. Ghost: no border; hovered or pressed → `secondary`. Radius `style.borderRadius` (8). Content: padding **h16 v12.5**, spacing **10**, text `base` **w500 height 1**, prefix/suffix icons **20**. `mainAxisSize: max` (fills the width). | height 12.5+16+12.5 = **41** |
| `FButton.icon` | default style **outline**; padding **7.5**; icon **20** | **35 × 35**, radius 8 |
| `FButton.raw` | decoration only, child unstyled | — |

### 5.3 Surfaces and lists

| Widget | Defaults (VERIFIED) | Intrinsic (INFERRED) |
|---|---|---|
| `FCard` (`widgets/card/*`) | `DecoratedBox`: 1 dp `border`, radius 8, `background`. **No shadow and no clip.** `FCard.content`: padding **16**, title `xl2` 22 **w600 h1.5** (first-ascent/last-descent height off), subtitle `sm` `mutedForeground`, image spacing 10 (image clipped to the theme radius), subtitle spacing 8 | — |
| `FDivider` (`widgets/divider.dart:70-96`) | colour **`secondary`**, width = `borderWidth` 1, margin **vertical 20** (horizontal axis) / horizontal 20 (vertical axis) | 41 dp row |
| `FTile` (`widgets/tile/tile.dart`) | bg `background`; decoration 1 dp `border` + radius 8; pressed or hovered bg `secondary`; disabled `disable(secondary)`. Content padding **S15 T13 E10 B13**; prefix icon **18** `primary`; title `base` (16/24, no weight); subtitle `xs` 12/12 `mutedForeground`; details `base` `mutedForeground`; suffix icon **18** `mutedForeground`; spacings prefix 10, title 3, middle 4, suffix 5. **No bounce**, pressed 0 ms / exit 25 ms | title only 13+24+13 = **50**; + subtitle 3+12 → **65** |
| `FTileGroup` | outer 1 dp `border` + radius 8; tiles lose their own border; divider **indented** (from the title start), colour `border`, width 1; label `base w600 primary`, label padding v 7.7; description `xs`; error `xs`; `ClampingScrollPhysics` | — |
| `FSelectTile` | an `FTile` with `FIcons.check` as **prefix** (unchecked = transparent check). `FSelectTile.suffix` puts it at the end. | — |
| `FItem` / `FItemGroup` (used by popover menus) | margin v2 h4; padding S11 T7.5 E6 B7.5; icons 15; title `sm`; subtitle/details `xs` muted; pressed bg `secondary`; no bounce; group spacing 4 | — |
| `FAccordion` | title padding v15, child bottom 15; title `base w500` (underlined on hover/press); child `sm`; `FIcons.chevronDown` 20 `mutedForeground` rotating 0→½ turn; expand **200 ms `easeOutCubic`**, collapse **150 ms `easeInCubic`**; divider `border`; no bounce | — |
| `FAlert` | padding **16 / 12**; icon `FIcons.circleAlert` 20; title `base w500 h1.2`; subtitle `sm`; 1 dp border + radius 8; destructive variant tints everything `destructive` | — |
| `FBadge` | variants primary/secondary/outline/destructive; radius **100** (pill); padding **h14 v2**; label `sm` **w600** | 17.5+4 = **21.5** tall |
| `FAvatar` | size **40**, circle, bg `muted`, fallback text `base` `mutedForeground`, image fade-in **500 ms** | 40 × 40 |
| `FBreadcrumb` | text `sm w400 mutedForeground` (current: `foreground`; hover underline), divider `FIcons.chevronRight` 16, padding h5, collapsed `FIcons.ellipsis`, no bounce | — |

### 5.4 Form controls

| Widget | Defaults (VERIFIED) | Intrinsic (INFERRED) |
|---|---|---|
| `FTextField` (`widgets/text_field/*`) | Material `TextField`, `isDense`. Text **`sm` 14/1.25 `primary`**; hint `sm` `mutedForeground` (disabled `disable(border)`). `OutlineInputBorder` 1 dp radius 8: idle `border`, focused **`primary`**, error `error`, disabled `disable(border)`. Content padding **10 × 10**. **Cursor `CupertinoColors.activeBlue` (`#007AFF`)**, selection `#007AFF` @ 0.4, handles `#007AFF`. Clear button: ghost, icon 17 `mutedForeground`, end padding 4. `scrollPadding` 20; `maxLines` 1 (`.multiline`: minLines 4). Label via vertical `FLabel`. | ≈ 10+17.5+10 = **37.5** |
| `FLabel` | horizontal: description/error top 2, child h-padding 8. Vertical: label bottom 5, description/error top 5 | — |
| `FSwitch` (`widgets/switch.dart:121`) | **`CupertinoSwitch`** (`applyTheme: false`). Track: selected `primary`, off `border`, disabled `disable(...)`. Thumb `background`. Focus colour `primary`. Flutter 3.47.9 internals: track **51 × 31**, thumb Ø**28**, widget 59 × 39, toggle **200 ms** (`Curves.ease`), reaction 300 ms, drag-commit 0.7, thumb shadows `0x26000000 (0,3) b8` + `0x0F000000 (0,3) b1`, `lightImpact` **iOS only** | 59 × 39 |
| `FCheckbox` (`widgets/checkbox.dart:270-330`) | size **16**; check icon 14 `primaryForeground` on `primary`; unchecked 0.6 dp `primary` border on `background`; radius lerped (≈2.7); `AnimatedSwitcher` **100 ms linear**; no bounce | 16 × 16 |
| `FRadio` (`widgets/radio.dart`) | outer: padding 2 + 1 dp border `primary` + 10 core (circle); indicator Ø9 `primary`, `AnimatedSize` **100 ms `easeOutCirc`**; no bounce | 16 × 16 |
| `FSlider` (`widgets/slider/*`) | track 8 thick, radius 4, active `primary`, inactive `secondary`; thumb **25 on touch** / 20 elsewhere, 2 dp `primary` border on `primaryForeground`; tick 3 `mutedForeground`; labels `xs`; tooltip above the thumb on touch | — |
| `FSelect` (`widgets/select/*`) | field = `FTextFieldStyle`; suffix `FIcons.chevronDown` 18 `mutedForeground`; popover (§5.5) max height 300, spacing 4, flip; content padding v5; items like `FItem` (selected `sm w600`); empty text `sm`; popover animation 100 ms | 37.5 field |
| `FSelectMenuTile` | `FTile` + `FPopoverMenu`; suffix `FIcons.chevronsUpDown`; menu anchored top-right to tile bottom-right; `autoHide` true | 50 |
| `FTabs` (`widgets/tabs/*`) | Material `TabBar` inside a `muted` container with radius 8, padding 4; tab height **35**; indicator = `background` with radius 8, size `tab`; labels `sm w500` (`foreground` / `mutedForeground`); content gap 10; indicator motion = `TabController` (300 ms `kTabScrollDuration`, `Curves.ease`) | container 43 |
| `FPicker` (`widgets/picker/*`) | `ListWheelScrollView` with `FixedExtentScrollPhysics`; diameterRatio 1.07, squeeze 1, magnification 1, off-centre opacity 0.25, spacing 5; text `base w500`; selection band `muted` with radius 8; **`HapticFeedback.selectionClick()` on every item change** | — |
| `FTimeField` / `FTimePicker` | text-field style + popover + picker; prefix `FIcons.clock4` 18 `mutedForeground`; 12 h by default (`hour24: false`); popover 100 ms; picker animates 100 ms `decelerate` | — |
| `FCalendar` | day tile **42**; padding h12 v16; container 1 dp border + radius 8; day radius 4; month/year entries radius 8, `base w500`; page change **200 ms `Curves.ease`**; header chevrons 17 | 7 × 42 = 294 wide |

### 5.5 Overlays

| Widget | Defaults (VERIFIED) |
|---|---|
| `showFDialog` / `FDialogRoute` (`widgets/dialog/dialog.dart`) | `RawDialogRoute` with a transparent `barrierColor`. Barrier = `FAnimatedModalBarrier` with a `ColorFilter` lerped from transparent to **`colors.barrier`** (0x33000000 light / 0x7A000000 dark), driven by the route's `barrierCurve` (Flutter default **`Curves.ease`**, `routes.dart:1869`). Route duration **150 ms**. `barrierDismissible: true`, `useSafeArea: false`. `buildTransitions` returns the child unchanged. |
| `FDialog` | Animation runs only when the route `animation` is passed in: fade 0→1 + **scale 0.95→1**, **150 ms**, `easeOutCubic` in / `easeInCubic` out. Decoration radius 8, `background`, **no border, no shadow**. `insetPadding` **h40 v24** (+ `AnimatedPadding` for view insets, 100 ms `decelerate`). Constraints **min 280 / max 560** wide. Default `direction: Axis.vertical`: centred text, padding **h30 v25**, actions in a `Column` with spacing **8**. Horizontal variant: start-aligned, padding 25, actions in a `Row` (end) with spacing **7**. Title `lg` 18 **w600** `foreground`; body `sm` `mutedForeground`; 4 dp under each, + 8 before the actions. |
| `showFSheet` / `FModalSheetRoute` (`widgets/sheet/*`) | Side `FLayout` (`btt` for a bottom sheet). **No surface decoration**: the builder paints the sheet itself. Height capped at **9/16** of the screen (`mainAxisMaxRatio`). Enter and exit **200 ms** with the position passed through **`easeOutCubic`**; linear while dragging, then `Split` from the release point. Barrier: `ColorFilter` to `colors.barrier`, `easeOutCubic`, tap dismisses. `draggable: true`; drag recognizer with `onlyAcceptDragOnThreshold` (Flutter `kTouchSlop` **18**). Release: fling if velocity > **700**/s; else close if progress < **0.5**, otherwise snap open. `useSafeArea: false`. |
| `showFPersistentSheet` | same `Sheet` mechanics, **no barrier**, `keepAliveOffstage: false`, controller-driven |
| `FPopover` (`widgets/popover.dart`) | **150 ms**, fade 0→1 + **scale 0.80→1**, `easeOutCubic` / `easeInCubic`. Decoration `background`, radius 8, 1 dp `border`, **`style.shadow`**. `viewInsets` 5; spacing **4**; `FPortalShift.flip`. On touch platforms the popover opens **above** the child (`popoverAnchor bottomCenter` to `childAnchor topCenter`); elsewhere below. Hides on tap outside (`excludeChild`). |
| `FPopoverMenu` | `FPopoverStyle` + item/tile group (1 dp border, radius 8); **maxWidth 250**; menu `topCenter` to child `bottomCenter`; hides on tap anywhere; full dividers |
| `FTooltip` | **100 ms** fade + scale 0.80→1, `easeOutCubic` both ways. Padding **h14 v10**; text `sm`; `background`, 1 dp border, radius 8, shadow `0x1A000000 (0,4) b6 s−1` + `0x1A000000 (0,2) b4 s−2`. Tip above the child, spacing 4. Hover delay 500 ms. **Long-press shows it and hides it 1500 ms after release.** |
| `FToaster` (`widgets/toast/toaster_style.dart:80-100`) | alignment **`bottomEnd`**; padding **h20 v15** inside `SafeArea`; **max 3** visible. Collapsed stack: each older toast scaled **0.9^i** and protruding **12·log2(i+1)**. Expands on hover or press (`hoverOrPress`; hover enter 200 / exit 300 ms) to spacing 10 (start spacing 16) over **500 ms `easeInOutCubic`**. |
| `FToast` (`toaster_style.dart:210-235`, `animated_toast.dart`) | Decoration 1 dp `border`, radius 8, `background`, **no shadow**. Padding 16; icon **18** `primary`; title `sm w500 primary`; description `sm` `mutedForeground` ellipsis; icon spacing 10, title spacing 5, suffix spacing 12; max **400 × 250**. **Enter/exit 400 ms `easeOutCubic` (both)**: slides one full toast height from the screen edge (from below for bottom alignments, from above for top) and fades from opacity 0. Re-stack transition 400 ms `easeOutCubic`. Auto-dismiss **5 s**; stacked toasts dismiss staggered by **300 ms** per index. Swipe-to-dismiss: right for end/right alignments, left otherwise. Commit at **0.5** of the width, finish 150 ms `easeInCubic`, opacity falls with the swipe distance. |
| `FProgress` | linear: height **10**, track `secondary`, bar `primary`, radius lerped (≈4.7). Indeterminate loop **1500 ms**, determinate **500 ms**, `Curves.ease`. `FProgress.circularIcon`: `FIcons.loaderCircle` **20** `mutedForeground`, rotated linearly once per **1 s**. There is no `FCircularProgress` class in 0.15.1. |

## 6. How Lonora themes forui 0.15.1

`lnForuiTheme` (`apps/android/lib/design/theme.dart`) builds forui's defaults from `lnForuiColors`
and `lnForuiTypography`, then overrides only the styles below. Token names are `LnPalette`,
`LnSpace`, `LnSize`, `LnRadius` and `LnShadow` fields in `apps/android/lib/design/tokens.dart`. Hex
values are light mode unless marked; translucent tokens are given with their result over the page.
All rows VERIFIED.

| # | Setting | forui 0.15.1 default (§3–5) | Lonora | Notes |
|---|---|---|---|---|
| 1 | `background` | `#FFFFFF` (zinc dark `#09090B`) | `bg` `#FFFFFF` (dark `#141414`) | |
| 2 | `foreground` | `#09090B` | `fg` `#1F1F1F`, neutral (dark `#FFFFFF`) | |
| 3 | `primary` / `primaryForeground` | `#18181B` / `#FAFAFA` | `fgStrong` `#141414` / white (dark: white / black) | |
| 4 | `secondary` / `secondaryForeground` | `#F4F4F5` / `#18181B` | `fill3` (black 6 %) made solid over `bg` → `#F0F0F0` / `fg` | forui derives `disable(secondary)`, the outline and ghost pressed fills and the tile pressed fill from it. |
| 5 | `muted` / `mutedForeground` | `#F4F4F5` / `#71717A` | `fill1` (black 4 %) solid → `#F5F5F5` / `fgMuted`, 60 % of the ink | |
| 6 | `border` | `#E4E4E7` | `border` (black 6 %) solid → `#F0F0F0` | Solid because forui derives disabled colours by replacing alpha; rows 16, 18 and 19 draw with the translucent token. |
| 7 | `destructive` / `error` | `#EF4444` / on `#FAFAFA` | `error` `#FA3D43` (dark `#EA454A`) / on white (`onAccent`) | |
| 8 | `barrier` | `0x33000000` (dark `0x7A000000`) | `scrim`, the same values | |
| 9 | `systemOverlayStyle` | `SystemUiOverlayStyle.dark` (dark: `.light`) | `lnSystemOverlayStyle`: transparent status and navigation bars, icon brightness from the theme, no contrast enforcement | Edge-to-edge. |
| 10 | Font family | `packages/forui/Inter` | none, so the platform default applies (`sans-serif`, Roboto on Android); tests pass a family | forui needs a non-empty family, hence `defaultFontFamily: 'sans-serif'`. |
| 11 | `xs` / `sm` / `base` / `lg` / `xl` | 12/12, 14/17.5, 16/24, 18/31.5, 20/35, no tracking | 12/16 +0.4, 14/20 +0.25, 16/24 +0.5, 18/22, 20/24 | Even leading distribution; `xl2`–`xl8` keep forui's metrics. |
| 12 | `pagePadding` | h 12, v 8 | h 16 (`LnSpace.pageGutter`), v 8 | Reaches `FHeader` and `FScaffold` only. |
| 13 | `borderRadius` | `FLerpBorderRadius.all(8, min: 24)` | `BorderRadius.all(24)` (`LnRadius.card`) | Text fields, tiles, popovers, dialogs, toasts and tabs all get 24; a 16 dp checkbox becomes a circle. |
| 14 | `shadow` | `0x0D000000 (0,1) b2` | `LnShadow.card` (black 4 %, blur 10, y 4); dark `darkCard` | Only `FPopover` reads it (§1 item 5). |
| 15 | `iconStyle` | 20, `primary` | 24 (`LnSize.chromeIcon`), `fg` | Ambient inside `FScaffold`. Composer icons are sized explicitly (20, `LnSize.composerIcon`). |
| 16 | `FButtonStyles` primary, secondary, destructive, outline | 41 dp, radius 8, padding h 16 v 12.5, disabled `disable(c)` | padding h 20 v 16 → 48 dp, a stadium at radius 24; disabled: fill `fill3` (6 %) with a `fgSubtle` label (30 % of the ink); hovered and pressed keep forui's pressed decoration | Secondary's enabled fill is the translucent `fill3`, so it also reads on a raised card. Ghost is unchanged. |
| 17 | Button content | text `base` w500 h1, spacing 10, icon 20 | unchanged apart from padding | |
| 18 | `FDividerStyles` | colour `secondary`, margin v 20 | colour translucent `border` (6 %); margins unchanged | |
| 19 | `FTextFieldStyle` | idle border `border` | idle border translucent `border`; focused (`primary`), error and disabled unchanged | Cursor and selection colours stay forui's. |
| 20 | `FSwitchStyle` | off track `border`, thumb `background` | light unchanged; dark: off track `fgSubtle`, thumb `fg` (disabled or selected: `background`) | a11y: with Lonora's dark colours forui's off switch is a `#141414` thumb on a `#222222` track, ≈1.15:1 on the page. |
| 21 | `FToasterStyle` | `bottomEnd`; toast 1 dp `border`, radius 8, `background`, no shadow | `topCenter`; toast `inverseSurface` (`#141414` @ 95 %; dark `#3A3A3C`), radius 24, `LnShadow.darkChrome`; icon 18 `onInverse`; title `sm` w500 `onInverse`; description `sm` `onInverseMuted` (white 70 %) | |

Lonora components that wrap forui:

- **`LnTappable`** (`components/tappable.dart`) is an `FTappable` with `noBounceTween` by default
  and `pressedEnterDuration` zero. Pressing fades the child to 0.4 opacity (`LnMotion`: 120 ms
  `easeInOutCubicEmphasized` down, 180 ms `easeOutCubic` up). `pressScale` restores a bounce where
  an element should shrink instead.
- **`showLnSheet`** (`components/sheets.dart`) calls `showFSheet(side: FLayout.btt)` with forui's
  motion and `mainAxisMaxRatio` 0.9 instead of 9/16; its builder draws Lonora's sheet surface.
- **`showLnConfirm`** uses `showFDialog` and the horizontal `FDialog` with forui's style and motion.

Custom widgets with no forui counterpart: the floating tab bar (62 dp stadium 21 dp from the edges,
sliding `tabHighlight` pill, detached 62 dp action circle 8 dp away, backdrop blur σ 16 when the
surface is translucent), the Ø44 header circles with 24 dp icons, the 48 dp composer, message
bubbles, the agent avatar, chat-list rows and inline event rows.

## 7. forui defaults Lonora keeps

All VERIFIED as forui defaults (§3–5) and not overridden in `theme.dart`.

- **Motion:**
  - `FTappableStyle` for forui's own tappables (`FButton` and the other §5 widgets): 0.97 bounce,
    100 ms `easeOutQuart` / 120 ms `easeOutCubic`, pressed after 200 ms.
  - Dialog: 150 ms, scale 0.95, barrier `Curves.ease`.
  - Sheet: 200 ms `easeOutCubic`, fling 700, close threshold 0.5.
  - Popover: 150 ms, 0.80. Tooltip: 100 ms, 0.80.
  - Toast: 400 ms slide and fade, 5 s, max 3, stack scale 0.9.
  - Accordion: 200/150 ms. Checkbox: 100 ms linear. Radio: 100 ms `easeOutCirc`.
- **Haptics:** forui's only built-ins (picker `selectionClick`, the iOS-only switch impact).
- **Colours:** `hoverLighten` / `hoverDarken` / `disabledOpacity` (0.5).
- **Typography:** sizes 12/14/16/18/20/22/30…; `xl2`–`xl8` heights; weights left to the widgets.
- **`FStyle`:** `borderWidth` 1, `focusedOutlineStyle`, `formFieldStyle`, `tappableStyle`, vertical
  `pagePadding` 8.
- **Shared widget metrics:** `FCardContentStyle.padding` 16, header `actionSpacing` 10, `FTextField`
  cursor and selection colours.

## 8. Reproduction

```bash
F=~/.pub-cache/hosted/pub.dev/forui-0.15.1
grep -rn 'HapticFeedback\|SystemSound' $F/lib                                       # §1 item 2
grep -rn 'style\.shadow' $F/lib/src/widgets                                         # §3.4
```
