import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

const read = (path: string) => readFileSync(new URL(`../../${path}`, import.meta.url), "utf8");

function firstFrame(stored: Record<string, string>) {
  const meta = { content: "#0b0c10" };
  const root = {
    dataset: {} as Record<string, string>,
    classList: { toggle() {} },
    lang: "",
    dir: "",
  };
  runInNewContext(read("apps/web/public/theme-init.js"), {
    document: {
      documentElement: root,
      querySelector: (selector: string) =>
        selector === 'meta[name="theme-color"]'
          ? {
              setAttribute: (_name: string, value: string) =>
                Object.assign(meta, { content: value }),
            }
          : null,
    },
    localStorage: { getItem: (key: string) => stored[key] ?? null },
  });
  return { theme: root.dataset.theme, bar: meta.content };
}

test("the browser bar takes the page colour before the app loads", () => {
  assert.deepEqual(firstFrame({ "lonora.theme": '"light"' }), { theme: "light", bar: "#f7f5ef" });
  assert.deepEqual(firstFrame({ "lonora.theme": '"dark"' }), { theme: "dark", bar: "#0b0c10" });
  assert.deepEqual(firstFrame({}), { theme: "dark", bar: "#0b0c10" });
});

test("the page and the installed app start on the charcoal, with the mint mark", () => {
  const html = read("apps/web/index.html");
  assert.match(html, /<meta name="theme-color" content="#0b0c10" \/>/);
  assert.match(html, /rel="mask-icon"[^>]*color="#22e3a8"/);
  const manifest = JSON.parse(read("apps/web/public/site.webmanifest"));
  assert.equal(manifest.background_color, "#0b0c10");
  assert.equal(manifest.theme_color, "#0b0c10");
});

test("high contrast is defined once, on the selector the accessibility switch sets", () => {
  const tokens = read("packages/ui-tokens/src/reference.css");
  assert.match(tokens, /^body\.hc \{\n {2}--muted: #c9cdd5;/m);
  assert.match(tokens, /^\[data-theme="light"\] body\.hc \{\n {2}--muted: #3b3f48;/m);
  assert.doesNotMatch(tokens, /data-contrast/);
  assert.doesNotMatch(read("apps/web/src/shell/settings/settings.css"), /body\.hc \{\s*--muted/);
});
