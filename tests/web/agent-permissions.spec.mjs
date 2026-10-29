// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Explicit disposable Playwright fixtures.
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

function simulation(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

async function setup(context, locale = "en", theme = "dark") {
  const data = simulation({ action: "init", empty: true });
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(
    ({ language, appearance }) => {
      if (!/^https?:$/.test(location.protocol)) return;
      localStorage.setItem("lonora.locale", language);
      localStorage.setItem("lonora.theme", JSON.stringify(appearance));
    },
    { language: locale, appearance: theme },
  );
  const headers = { "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value };
  const created = [];
  async function agent() {
    const response = await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Permission UX ${randomUUID()}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    });
    expect(response.status()).toBe(201);
    const value = await response.json();
    created.push(value.id);
    const conversation = await context.request.post(`/api/agents/${value.id}/conversation`, {
      headers,
      data: {},
    });
    expect(conversation.ok()).toBeTruthy();
    return { agent: value, thread: await conversation.json() };
  }
  const selected = await agent();
  return {
    data,
    headers,
    ...selected,
    createAgent: agent,
    async state(id = selected.agent.id) {
      const response = await context.request.get(`/api/agents/${id}/permissions`);
      expect(response.ok()).toBeTruthy();
      return response.json();
    },
    async open(page, value = selected) {
      await page.goto(`/app/${value.agent.id}?thread=${value.thread.id}`);
      await expect(page.getByTestId("permission-selector")).toBeVisible();
    },
    async cleanup() {
      for (const id of created.reverse())
        await context.request.delete(`/api/agents/${id}`, { headers });
      simulation({ ...data, action: "cleanup" });
    },
  };
}

async function choose(page, level) {
  await page.getByTestId("permission-selector").click();
  await expect(page.getByTestId("permission-options")).toBeVisible();
  await page.getByTestId(`permission-option-${level}`).click();
}

async function editor(page) {
  await choose(page, "autonomous");
  const review = page.getByTestId("permission-review");
  await expect(review).toBeVisible();
  await review.getByTestId("permission-advanced").click();
  const surface = page.getByTestId("permission-editor");
  await expect(surface).toBeVisible();
  return surface;
}

async function noOverflow(page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
    ),
  ).toBeTruthy();
}

const layouts = [
  { label: "desktop EN dark", locale: "en", theme: "dark", width: 1440, height: 900 },
  { label: "mobile AR dark", locale: "ar", theme: "dark", width: 390, height: 844 },
  { label: "small mobile EN light", locale: "en", theme: "light", width: 320, height: 640 },
  { label: "landscape AR light", locale: "ar", theme: "light", width: 844, height: 390 },
  { label: "tablet EN dark", locale: "en", theme: "dark", width: 768, height: 1024 },
];

for (const layout of layouts) {
  test(`${layout.label}: composer permissions preserve draft and unsigned scope without overflow`, async ({
    page,
    context,
  }) => {
    test.setTimeout(60000);
    await page.setViewportSize({ width: layout.width, height: layout.height });
    const state = await setup(context, layout.locale, layout.theme);
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    try {
      await state.open(page);
      expect((await state.state()).effective_level).toBe("analysis");
      await expect(page.getByTestId("permission-effective")).toHaveAttribute(
        "data-level",
        "analysis",
      );
      if (layout.width === 1440) {
        const trigger = page.getByTestId("permission-selector");
        await trigger.focus();
        await trigger.press("Enter");
        await expect(page.getByTestId("permission-options")).toBeVisible();
        await page.keyboard.press("Escape");
        await expect(page.getByTestId("permission-options")).toBeHidden();
        await expect(trigger).toBeFocused();
      }
      const composer = page.getByRole("combobox", {
        name: layout.locale === "ar" ? "الرسالة" : "Message",
        exact: true,
      });
      const draft = "Keep my trading question unsent — احفظ المسودة";
      await composer.fill(draft);
      await page.getByTestId("permission-selector").click();
      const options = page.getByTestId("permission-options");
      for (const level of ["analysis", "supervised", "autonomous"])
        await expect(options.getByTestId(`permission-option-${level}`)).toBeVisible();
      await expect(options.getByTestId("permission-advanced")).toHaveCount(0);
      await options.getByTestId("permission-option-supervised").click();
      await expect.poll(async () => (await state.state()).effective_level).toBe("supervised");
      await expect(composer).toHaveValue(draft);
      await page.reload();
      await expect(composer).toHaveValue(draft);
      await expect(page.getByTestId("permission-effective")).toHaveAttribute(
        "data-level",
        "supervised",
      );
      const surface = await editor(page);
      await expect(surface.getByTestId("permission-header-agent")).toHaveText(state.agent.name);
      await expect(surface.getByTestId("permission-summary-agent")).toHaveText(state.agent.name);
      const pending = await state.state();
      expect(pending.effective_level).toBe("supervised");
      expect(pending.requested_level).toBe("autonomous");
      expect(pending.pending_authority.status).toBe("pending");
      expect(pending.active_authorities).toEqual([]);
      for (const group of ["scope", "actions", "limits", "duration"])
        await expect(surface.getByTestId(`permission-group-${group}`)).toHaveJSProperty(
          "open",
          false,
        );
      await surface.getByTestId("permission-group-scope").locator("summary").click();
      await expect(surface.getByTestId("permission-group-scope")).toContainText(state.data.symbol);
      await surface.getByTestId("permission-group-limits").locator("summary").click();
      const limit = surface.getByTestId("permission-limit-maximum_order_volume");
      await limit.fill("0.05");
      await surface.getByTestId("permission-group-limits").locator("summary").click();
      await surface.getByTestId("permission-group-limits").locator("summary").click();
      await expect(limit).toHaveValue("0.05");
      await noOverflow(page);
      if (layout.width === 1440) {
        await expect(surface.locator(".permission-summary")).toContainText("0.05");
        await page.screenshot({ path: ".runtime/permission-qa-web-desktop-editor.png" });
      }
      const continueButton = surface.getByTestId("permission-review-continue");
      await expect(continueButton).toBeEnabled();
      await continueButton.click();
      await expect(page.getByTestId("permission-review")).toContainText("0.05");
      await expect(
        page.getByTestId("permission-review").getByTestId("permission-header-agent"),
      ).toHaveText(state.agent.name);
      await expect(
        page.getByTestId("permission-review").getByTestId("permission-summary-agent"),
      ).toHaveText(state.agent.name);
      if (layout.locale === "ar" && layout.width === 390)
        await page.screenshot({ path: ".runtime/permission-qa-web-mobile-ar-review.png" });
      await noOverflow(page);
      expect((await state.state()).effective_level).toBe("supervised");
      expect(errors).toEqual([]);
    } finally {
      await state.cleanup();
    }
  });
}

test("personal agent explicitly chooses the account-wide scope and cannot activate it unsigned", async ({
  page,
  context,
}) => {
  test.setTimeout(60000);
  const state = await setup(context);
  let personal;
  try {
    const agents = await (await context.request.get("/api/agents")).json();
    personal = agents.find((agent) => agent.role === "personal");
    expect(personal).toBeTruthy();
    const current = await state.state(personal.id);
    const reset = await context.request.put(`/api/agents/${personal.id}/permissions`, {
      headers: state.headers,
      data: { level: "analysis", expected_revision: current.revision },
    });
    expect(reset.ok()).toBeTruthy();
    const thread = await (
      await context.request.post(`/api/agents/${personal.id}/conversation`, {
        headers: state.headers,
        data: {},
      })
    ).json();
    await state.open(page, { agent: personal, thread });
    await choose(page, "autonomous");
    await expect(page.getByTestId("permission-review")).toBeVisible();
    await page.getByTestId("permission-review").getByTestId("permission-advanced").click();
    const surface = page.getByTestId("permission-editor");
    await expect(surface).toBeVisible();
    await expect(surface.getByTestId("permission-review-continue")).toBeDisabled();
    await surface.getByTestId("permission-group-scope").locator("summary").click();
    await surface.getByTestId("permission-account").selectOption(state.data.account);
    await surface.getByTestId("permission-symbol-scope").selectOption("account");
    await surface.getByTestId("permission-review-continue").click();
    await expect(page.getByTestId("permission-review")).toBeVisible();
    const pending = await state.state(personal.id);
    expect(pending.effective_level).toBe("analysis");
    expect(pending.pending_authority.envelope.account_id).toBe(state.data.account);
    expect(pending.pending_authority.envelope.symbol_scope).toBe("account");
    expect(pending.pending_authority.envelope.symbols).toEqual([]);
    expect(pending.pending_authority.envelope.maximum_order_volume).toBeNull();
    expect(pending.pending_authority.envelope.valid_until).toBeNull();
  } finally {
    if (personal) {
      const current = await state.state(personal.id);
      await context.request.put(`/api/agents/${personal.id}/permissions`, {
        headers: state.headers,
        data: { level: "analysis", expected_revision: current.revision },
      });
    }
    await state.cleanup();
  }
});

test("customized scope signs through actual virtual WebAuthn, then downgrade revokes it and retains the draft", async ({
  page,
  context,
}) => {
  test.setTimeout(90000);
  const state = await setup(context);
  const originalControls = await (await context.request.get("/api/trading/controls")).json();
  const devices = await (await context.request.get("/api/auth/devices")).json();
  for (const device of devices)
    expect(
      (
        await context.request.delete(`/api/auth/devices/${device.id}`, { headers: state.headers })
      ).ok(),
    ).toBeTruthy();
  const cdp = await context.newCDPSession(page);
  await cdp.send("WebAuthn.enable");
  await cdp.send("WebAuthn.addVirtualAuthenticator", {
    options: {
      protocol: "ctap2",
      transport: "internal",
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });
  try {
    await state.open(page);
    const observer = await context.newPage();
    await state.open(observer);
    await expect(observer.getByTestId("permission-effective")).toHaveAttribute(
      "data-level",
      "analysis",
    );
    // WebAuthn requires the signing document to be the active tab. Keep the
    // second tab as an observer without moving the signing flow to the background.
    await page.bringToFront();
    const surface = await editor(page);
    await surface.getByTestId("permission-group-actions").locator("summary").click();
    const actions = [
      "buy",
      "sell",
      "buy_limit",
      "sell_limit",
      "buy_stop",
      "sell_stop",
      "close_position",
      "modify_position",
      "cancel_order",
      "modify_order",
    ];
    for (const action of actions)
      await expect(surface.getByTestId(`permission-action-${action}`)).toBeChecked();
    await surface.getByTestId("permission-deselect-all").click();
    await expect(surface.getByTestId("permission-review-continue")).toBeDisabled();
    await surface.getByTestId("permission-action-buy").check();
    await surface.getByTestId("permission-action-modify_position").check();
    await surface.getByTestId("permission-group-limits").locator("summary").click();
    const limits = {
      maximum_order_volume: "0.05",
      maximum_symbol_volume: "0.20",
      maximum_positions: "3",
      maximum_pending_orders: "0",
      maximum_actions: "7",
      minimum_equity: "9000",
    };
    for (const [field, value] of Object.entries(limits))
      await surface.getByTestId(`permission-limit-${field}`).fill(value);
    await surface.getByTestId("permission-limit-maximum_positions").fill("1.5");
    await expect(surface.getByTestId("permission-review-continue")).toBeDisabled();
    await surface.getByTestId("permission-limit-maximum_positions").fill("3");
    await surface.getByTestId("permission-group-duration").locator("summary").click();
    await surface.getByTestId("permission-duration").selectOption("12h");
    await surface.getByTestId("permission-manual").uncheck();
    await surface.getByTestId("permission-review-continue").click();
    const review = page.getByTestId("permission-review");
    await expect(review).toBeVisible();
    const pending = await state.state();
    const envelope = pending.pending_authority.envelope;
    expect(pending.effective_level).toBe("analysis");
    expect(envelope.management_mode).toBe("full");
    expect(envelope.symbols).toEqual([state.data.symbol]);
    expect(envelope.actions).toEqual(["buy", "modify_position"]);
    expect(envelope.maximum_order_volume).toBe("0.05");
    expect(envelope.maximum_symbol_volume).toBe("0.20");
    expect(envelope.maximum_positions).toBe(3);
    expect(envelope.maximum_pending_orders).toBe(0);
    expect(envelope.maximum_actions).toBe(7);
    expect(envelope.minimum_equity).toBe("9000");
    expect(envelope.allow_manual_positions).toBe(false);
    expect(Math.abs(Date.parse(envelope.valid_until) - Date.now() - 12 * 3600000)).toBeLessThan(
      60000,
    );
    await review.getByTestId("permission-sign").click();
    await review
      .getByLabel("Confirm account password", { exact: true })
      .fill("ci-only-owner-password");
    await review.getByRole("button", { name: "Register this device", exact: true }).click();
    await expect(review.getByLabel("Confirm account password", { exact: true })).toHaveCount(0);
    const verification = page.waitForResponse(
      (r) => r.url().endsWith("/account-authorities/verify") && r.request().method() === "POST",
    );
    await review.getByTestId("permission-sign").click();
    expect((await verification).ok()).toBeTruthy();
    await expect.poll(async () => (await state.state()).effective_level).toBe("autonomous");
    await expect(page.getByTestId("permission-effective")).toHaveAttribute(
      "data-level",
      "autonomous",
    );
    await expect(observer.getByTestId("permission-effective")).toHaveAttribute(
      "data-level",
      "autonomous",
    );
    await choose(page, "supervised");
    await expect.poll(async () => (await state.state()).effective_level).toBe("supervised");
    const downgraded = await state.state();
    expect(downgraded.active_authorities).toEqual([]);
    expect(downgraded.pending_authority).toBeNull();
    expect(downgraded.customization.limits.maximum_order_volume).toBe("0.05");
    expect(downgraded.customization.duration).toBe("12h");
    await expect(observer.getByTestId("permission-effective")).toHaveAttribute(
      "data-level",
      "supervised",
    );
    await observer.close();
    expect(await (await context.request.get("/api/trading/controls")).json()).toEqual(
      originalControls,
    );
    const other = await state.createAgent();
    await state.open(page, other);
    await expect(page.getByTestId("permission-effective")).toHaveAttribute(
      "data-level",
      "analysis",
    );
    await state.open(page);
    await expect(page.getByTestId("permission-effective")).toHaveAttribute(
      "data-level",
      "supervised",
    );
    await choose(page, "autonomous");
    await expect(page.getByTestId("permission-review")).toBeVisible();
    await expect.poll(async () => (await state.state()).pending_authority?.status).toBe("pending");
    expect((await state.state()).effective_level).toBe("supervised");
  } finally {
    await state.cleanup();
  }
});
