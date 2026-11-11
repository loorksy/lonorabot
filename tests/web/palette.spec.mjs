import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

/* One palette: the reference's --muted, --accent and --primary mean the same thing on every
   screen, including the old ones still mounted in the shell. */
function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

async function signIn(context, data, theme) {
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript((theme) => {
    localStorage.setItem("lonora.locale", "ar");
    localStorage.setItem("lonora.theme", JSON.stringify(theme));
  }, theme);
}

/** WCAG contrast of each element's text against the first opaque background behind it. */
function contrasts(elements) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 1;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  const rgba = (css) => {
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = css;
    ctx.fillRect(0, 0, 1, 1);
    const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
    return [r, g, b, a / 255];
  };
  const over = (top, bottom) =>
    top.slice(0, 3).map((c, i) => c * top[3] + bottom[i] * (1 - top[3]));
  const background = (node) => {
    const layers = [];
    for (let el = node; el; el = el.parentElement) {
      const color = rgba(getComputedStyle(el).backgroundColor);
      if (color[3] > 0) layers.push(color);
      if (color[3] === 1) break;
    }
    return layers.reduceRight((bottom, top) => over(top, bottom), [255, 255, 255]);
  };
  const luminance = (rgb) => {
    const [r, g, b] = rgb.map((c) => {
      const s = c / 255;
      return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  return elements.map((el) => {
    const bg = background(el);
    const fg = over(rgba(getComputedStyle(el).color), bg);
    const [hi, lo] = [luminance(fg), luminance(bg)].sort((a, b) => b - a);
    return { text: el.textContent.trim(), ratio: (hi + 0.05) / (lo + 0.05) };
  });
}

for (const theme of ["dark", "light"]) {
  test(`the old knowledge screen's tab labels are readable (${theme})`, async ({
    page,
    context,
  }) => {
    const data = fixture({ action: "init", empty: true });
    try {
      await signIn(context, data, theme);
      await page.goto("/app/memory");
      const tabs = page.locator(".tabs button");
      await expect(tabs.first()).toBeVisible();
      for (const { text, ratio } of await tabs.evaluateAll(contrasts))
        expect(ratio, `«${text}»`).toBeGreaterThanOrEqual(4.5);
    } finally {
      fixture({ ...data, action: "cleanup" });
    }
  });
}
