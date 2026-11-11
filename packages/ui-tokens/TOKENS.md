# Design tokens

`@lonora/ui-tokens` is the single source of design tokens. It holds two sets:

| Set | TypeScript | CSS (generated) | Used by |
| --- | --- | --- | --- |
| Reference (canonical) | `src/reference.ts` → `reference` | `src/reference.css` (`@lonora/ui-tokens/reference.css`) | the UI ported from `docs/ui-reference/Lonora-Desktop-37.html` |
| Legacy (shadcn names) | `src/appearance.ts` → `appearance` | `src/tokens.css` (`@lonora/ui-tokens/tokens.css`, `/css`) | the current Web screens (Tailwind `@theme` in `packages/ui-web/src/styles.css`) and `apps/mobile` |

Both CSS files are written by `pnpm --filter @lonora/ui-tokens generate` (`src/generate-css.ts`) and
must never be edited by hand; `pnpm lint` checks them, so the generator emits Biome's canonical CSS
notation (lower-case hex, `rgba(255, 255, 255, 0.07)`, `cubic-bezier(0.22, 1, 0.36, 1)`). The values
are the reference's values exactly; only the spelling is normalised.

## Reference set

Source: the reference's `:root` (dark, the default) and `body.light` blocks, `body.hc` (high
contrast) and the opaque-glass fallbacks (`@supports not (backdrop-filter)` and
`prefers-reduced-transparency: reduce`). Names are the reference's CSS custom properties. Selectors
follow Lonora's theme root (`apps/web/src/hooks/useTheme.ts` sets `document.documentElement.dataset.theme`):

| Reference selector | Lonora selector |
| --- | --- |
| `:root` | `:root, [data-theme="dark"]` |
| `body.light` | `[data-theme="light"]` |
| `body.hc` / `body.light.hc` | `[data-contrast="high"]` / `[data-theme="light"][data-contrast="high"]` |

Names the reference states as literals and this package names (everything else is 1:1):

| Token | Value | Reference |
| --- | --- | --- |
| `--r-bar` | 33px | the floating tab bar (`nav{border-radius:33px}`) |
| `--r-composer` | 26px | the composer card (`.composer-card{border-radius:26px}`) |
| `--fw-regular` / `--fw-semibold` / `--fw-bold` | 400 / 600 / 700 | "weights 400/600/700" |
| `reference.textScale` (TS only) | 0.9, 1, 1.1, 1.2, 1.32 | accessibility text sizes 0–4 × the `--fs-*` tokens |

Runtime variables the reference sets from JavaScript (`--kb`, `--edge`, `--top-h`, `--bd`, `--on`,
`--p`, `--lvl`, `--mp-*`, `--pair-ring`) are component state, not tokens; only `--app-height` has an
initial value and is included.

## Legacy screens inside the ported shell

Three legacy names collide with reference names that mean something else (`--primary`,
`--accent`, `--muted`). The plain names belong to the reference everywhere; `tokens.css` emits the
legacy values as `--legacy-primary`, `--legacy-accent` and `--legacy-muted`, and the Tailwind
`@theme` (`bg-primary`, `bg-accent`, `bg-muted`) and the old screens' CSS read those. Nothing
re-declares a reference name inside `.legacy-surface`.

## Mapping to the legacy set

Where a legacy token plays the same role, the reference name is canonical and the legacy name
becomes an alias (`--background: var(--bg)`) **when the screen that uses it is ported**; legacy names
nobody references any more are removed then. Aliasing now would recolour the current screens
(e.g. `--foreground` #ececee → #f7f5ef), which phase 1 must not do, so in phase 1 the two sets stay
side by side and `reference.css` is not yet imported by `apps/web`.

| Reference | Dark | Light | Legacy name(s) with the same role |
| --- | --- | --- | --- |
| `--bg` | #0b0c10 | #f7f5ef | `--background` |
| `--surface` | #15161b | #ffffff | `--card`, `--popover`, `--sidebar` |
| `--raised` | #1b1d23 | #ffffff | — |
| `--fill` | #23252c | #ece9e1 | `--secondary`, `--input` |
| `--fill-2` | #2c2f37 | #e2ded4 | — |
| `--line` | #23252c | #e3dfd5 | `--border`, `--sidebar-border` |
| `--line-strong` | #343741 | #cfcac0 | — |
| `--text` | #f7f5ef | #0b0c10 | `--foreground` and every legacy `*-foreground` on a neutral surface |
| `--muted` | #8b919e | #5d6270 | `--muted-foreground` (legacy `--legacy-muted` is a background, #141518) |
| `--faint` | #6a707c | #868b97 | — |
| `--primary` | #f7f5ef | #0b0c10 | `--legacy-primary` (same role, different value: #f1f1ef / #1a1a1a) |
| `--on-primary` | #0b0c10 | #f7f5ef | `--primary-foreground` |
| `--primary-hi`, `--primary-lo` | | | — (primary button gradient ends) |
| `--accent` | #22e3a8 | #22e3a8 | — (legacy `--legacy-accent` is the neutral hover fill, #1a1b20, whose role is the reference's `--hover`) |
| `--accent-ink` | #22e3a8 | #087a57 | — (accent as ink: text, caret, selection) |
| `--on-accent`, `--wave-accent`, `--mint` | | | — |
| `--bubble-in` | #15161b | #ffffff | — (agent bubble) |
| `--bubble-out` | #23262e | #eae7df | `--chat-user` |
| `--red` | #ff8a91 | #c0392b | — (danger as ink) |
| `--danger-fill` | #e5484d | #e5484d | `--destructive` |
| `--amber` | #f2c46b | #9a6a00 | `--warning` |
| `--violet` | #a99aff | #6c55ba | — |
| `--hover` | rgba(255,255,255,.05) | rgba(11,12,16,.05) | `--legacy-accent`, `--sidebar-accent` |
| `--lens` | | | — |
| `--glass`, `--glass-bar`, `--glass-card`, `--glass-pop`, `--glass-line`, `--blur` | | | — |
| `--stage`, `--thumb`, `--viz-dim`, `--viz-ink`, `--wall-ink`, `--add-card`, `--add-ic`, `--add-press` | | | — |
| `--hi`, `--raise`, `--float-shadow` | | | — |
| `--r-sm` 10 · `--r-md` 16 · `--r-lg` 24 · `--r-pill` · `--r-tail` 6 · `--r-bar` 33 · `--r-composer` 26 | | | `--radius` (0.75rem) and the derived Tailwind `--radius-*` scale have no equal step |
| `--fs-xs` 12 · `--fs-sm` 14 · `--fs-md` 16 · `--fs-lg` 20 · `--fs-xl` 28 | | | — (Tailwind `text-*`) |
| `--fw-*`, `--ease`, `--spring`, `--app-height` | | | — |
| `--font` | system stack | | — (`apps/web` `body` uses it) |

Legacy tokens with no reference counterpart, to retire or decide when their screens are ported:
`--ring`, `--link`, `--success` (the reference uses the accent for success states), `--status-working`,
`--favicon-plate`, `--overlay` (scrim; the reference dims through `::backdrop` and `--bd`),
`--scrollbar`, `--scrollbar-hover`, the `--sidebar-*` family, `--card-foreground`,
`--popover-foreground`, `--secondary-foreground`, `--accent-foreground`, `--destructive-foreground`,
`--chat-user-foreground`. `visual` (`src/visual.ts`) and `brand` are unchanged.

## Open owner questions (recorded, not decided)

1. **Aliasing time.** Pointing the legacy names at the reference values restyles the current screens;
   phase 1 keeps the sets apart (above). Confirm that the aliases land per ported screen.
2. **Pair icon licence.** github.com/nvstly/icons publishes no licence file (THIRD_PARTY_NOTICES.md,
   "Pair icons"). The eleven marks are embedded as in the reference; their terms of use need the
   owner's confirmation or a replacement source.
