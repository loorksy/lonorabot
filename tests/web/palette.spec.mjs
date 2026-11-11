import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
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
  test(`the old knowledge screen reads the reference palette (${theme})`, async ({
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
      // An old screen's switch turns the reference's mint when on, like the shell's.
      const [on, accent] = await page.locator(".legacy-surface").evaluate((surface) => {
        const input = Object.assign(document.createElement("input"), {
          type: "checkbox",
          checked: true,
        });
        input.dataset.lonoraSwitch = "true";
        const probe = document.createElement("i");
        probe.style.background = "var(--accent)";
        surface.append(input, probe);
        return [input, probe].map((el) => getComputedStyle(el).backgroundColor);
      });
      expect(on).toBe(accent);
    } finally {
      fixture({ ...data, action: "cleanup" });
    }
  });
}

for (const theme of ["dark", "light"]) {
  test(`markdown in an agent's reply reads the reference palette (${theme})`, async ({
    page,
    context,
  }) => {
    const data = fixture({ action: "init", empty: true });
    const headers = {
      "X-CSRF-Token": data.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
    };
    try {
      await signIn(context, data, theme);
      const response = await context.request.post("/api/agents", {
        headers,
        data: {
          name: `Palette ${randomUUID()}`,
          trading_account_id: data.account,
          trading_symbol: data.symbol,
        },
      });
      expect(response.status()).toBe(201);
      await page.goto(`/app/${(await response.json()).id}`);
      await expect(page.locator(".composer")).toBeVisible();
      // The reply markup RichResponse renders for a text part (ChatMarkdown in .ui-lead).
      const styles = await page.evaluate(() => {
        const lead = document.createElement("div");
        lead.className = "ui-lead";
        lead.innerHTML = `<div class="rk-chat-markdown"><p><a href="#x">link</a> <code>code</code></p>
          <table><thead><tr><th>head</th></tr></thead></table></div>
          <i data-probe="ink" style="color: var(--accent-ink)"></i>
          <i data-probe="chip" style="background: color-mix(in srgb, var(--text) 10%, transparent)"></i>
          <i data-probe="head" style="background: color-mix(in srgb, var(--text) 6%, transparent)"></i>`;
        document.querySelector(".composer").before(lead);
        const css = (selector) => getComputedStyle(lead.querySelector(selector));
        return {
          link: css("a").color,
          ink: css('[data-probe="ink"]').color,
          code: css("code").backgroundColor,
          codeBorder: css("code").borderTopStyle,
          chip: css('[data-probe="chip"]').backgroundColor,
          th: css("th").backgroundColor,
          head: css('[data-probe="head"]').backgroundColor,
        };
      });
      expect(styles.link).toBe(styles.ink);
      expect(styles.code).toBe(styles.chip);
      expect(styles.codeBorder).toBe("none");
      expect(styles.th).toBe(styles.head);
    } finally {
      fixture({ ...data, action: "cleanup" });
    }
  });
}
