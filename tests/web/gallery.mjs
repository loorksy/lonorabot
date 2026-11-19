// Card gallery harness (review/ui-cards only, not a test of behaviour): every card the owner
// sees, shot at desktop 1280 and phone 390, in Arabic and English, light and dark.
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT =
  process.env.LONORA_GALLERY_ROOT ??
  fileURLToPath(new URL("../../review/ui-cards/", import.meta.url));

export const VARIANTS = [];
for (const width of [1280, 390])
  for (const locale of ["ar", "en"])
    for (const theme of ["light", "dark"])
      VARIANTS.push({
        width,
        height: width === 1280 ? 800 : 844,
        locale,
        theme,
        name: `${width === 1280 ? "desktop" : "phone"}-${locale}-${theme}`,
      });

/** Switches the open page to a variant (viewport, locale, theme) and reloads it. */
export async function useVariant(page, variant) {
  await page.setViewportSize({ width: variant.width, height: variant.height });
  await page.evaluate(
    ([locale, theme]) => {
      localStorage.setItem("lonora.locale", locale);
      localStorage.setItem("lonora.theme", JSON.stringify(theme));
    },
    [variant.locale, variant.theme],
  );
  await page.reload();
  // A spec that forces the locale or theme (an init script) would mislabel every shot: fail.
  await page.waitForFunction(
    ([locale, theme]) =>
      document.documentElement.lang === locale && document.documentElement.dataset.theme === theme,
    [variant.locale, variant.theme],
    { timeout: 10_000 },
  );
}

const file = (family, state, variant, suffix = "") =>
  `${ROOT}${family}/${state}__${variant.name}${suffix}.png`;

/** The card itself, scrolled into view. */
export async function shot(locator, family, state, variant) {
  const path = file(family, state, variant);
  mkdirSync(dirname(path), { recursive: true });
  await locator.scrollIntoViewIfNeeded();
  await locator.page().evaluate(() => document.fonts.ready);
  await locator.screenshot({ path, animations: "disabled" });
  return path;
}

/** The whole viewport around it: the card in its conversation. */
export async function view(page, family, state, variant) {
  const path = file(family, state, variant, "__view");
  mkdirSync(dirname(path), { recursive: true });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path, animations: "disabled" });
  return path;
}

/**
 * Every variant in turn: switch, let `ready(page, variant)` wait for the card and return its
 * locator, then shoot the card (and, with `viewport`, the screen around it).
 */
export async function eachVariant(page, family, state, ready, { viewport = true } = {}) {
  const files = [];
  for (const variant of VARIANTS) {
    await useVariant(page, variant);
    const locator = await ready(page, variant);
    files.push(await shot(locator, family, state, variant));
    if (viewport) files.push(await view(page, family, state, variant));
  }
  return files;
}
