// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright reads explicitly scoped disposable-test configuration.
/* UI phase 6, calls: the call screen, the call strip, the incoming call page, the call button
   with no voice provider (Q58) and the microphone refused. Audio and WebRTC are a fake
   harness and the voice provider is stubbed; auth, agents and conversations are real. */
import { randomUUID } from "node:crypto";
import { test as base, expect } from "@playwright/test";

const harness = ({ deny, locale }) => {
  localStorage.setItem("lonora.locale", locale);
  const state = { streams: [], sink: "" };
  const audio = (volume) => {
    const context = new AudioContext();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    const destination = context.createMediaStreamDestination();
    gain.gain.value = volume;
    oscillator.connect(gain);
    gain.connect(destination);
    oscillator.start();
    void context.resume();
    state.streams.push(destination.stream);
    return destination.stream;
  };
  Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
    configurable: true,
    value: async () => {
      if (deny) throw new DOMException("denied", "NotAllowedError");
      return audio(0.1);
    },
  });
  Object.defineProperty(navigator.mediaDevices, "enumerateDevices", {
    configurable: true,
    value: async () => [
      { kind: "audiooutput", deviceId: "default", label: "Built-in speaker" },
      { kind: "audiooutput", deviceId: "headset-1", label: "Headset" },
    ],
  });
  HTMLMediaElement.prototype.setSinkId = async (id) => {
    state.sink = id;
  };
  class Peer {
    constructor() {
      this.iceGatheringState = "complete";
      this.connectionState = "new";
    }
    addTrack() {}
    createDataChannel() {
      this.channel = {
        readyState: "open",
        send: (value) => {
          if (JSON.parse(value).type === "session.close")
            queueMicrotask(() =>
              this.channel.onmessage?.({ data: JSON.stringify({ type: "session.closed" }) }),
            );
        },
        close() {
          this.readyState = "closed";
        },
      };
      return this.channel;
    }
    async createOffer() {
      return { type: "offer", sdp: "v=0\r\ncalls-fixture-offer" };
    }
    async setLocalDescription(value) {
      this.localDescription = value;
    }
    async setRemoteDescription() {
      this.connectionState = "connected";
      const remote = audio(0);
      this.ontrack?.({ track: remote.getAudioTracks()[0], streams: [remote] });
      this.channel.onmessage?.({ data: JSON.stringify({ type: "session.started" }) });
    }
    addEventListener() {}
    removeEventListener() {}
    close() {
      this.connectionState = "closed";
    }
  }
  window.RTCPeerConnection = Peer;
  window.__calls = state;
};

const test = base.extend({
  owner: async ({ context, page }, use) => {
    const credentials = {
      email: process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com",
      password: process.env.LONORA_UI_TEST_PASSWORD ?? "ci-only-owner-password",
    };
    const status = await (await context.request.get("/api/onboarding")).json();
    if (!status.owner_initialized)
      await context.request.post("/api/onboarding", {
        data: {
          ...credentials,
          bootstrap_token: process.env.LONORA_BOOTSTRAP_TOKEN ?? "lonora-ui-bootstrap-ci-only-2026",
        },
      });
    const login = await context.request.post("/api/auth/login", { data: credentials });
    expect(login.status()).toBe(200);
    const headers = { "X-CSRF-Token": (await login.json()).csrf };
    const agent = await (
      await context.request.post("/api/agents/create", {
        data: {
          template: "general",
          name: `Caller ${randomUUID().slice(0, 8)}`,
          responsibility: "Calls",
        },
        headers,
      })
    ).json();
    const thread = await (
      await context.request.post(`/api/agents/${agent.id}/conversation`, { data: {}, headers })
    ).json();
    const sessions = [];
    const closes = [];
    const voice = { configured: true };
    await page.route("**/api/voice/status", (route) =>
      route.fulfill({
        json: {
          transport: "gpt_live",
          transport_configured: voice.configured,
          model: "calls-test",
        },
      }),
    );
    await page.route("**/api/voice/sessions", async (route) => {
      sessions.push(route.request().postDataJSON());
      await route.fulfill({
        status: 201,
        json: { session_id: `calls-${sessions.length}`, sdp: "v=0\r\ncalls-fixture-answer" },
      });
    });
    await page.route("**/api/voice/sessions/calls-*", async (route) => {
      if (route.request().method() === "DELETE") {
        closes.push(route.request().url());
        return route.fulfill({ json: { closed: true } });
      }
      return route.fulfill({
        json: {
          session_id: "calls-1",
          status: "connected",
          input: [],
          output: [],
          finalized: false,
        },
      });
    });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    try {
      await use({ agent, thread, sessions, closes, voice, errors });
    } finally {
      // Test cleanup only: the UI never deletes agents.
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
    }
  },
});

const phone = { width: 390, height: 844 };

test("call screen in Arabic: clock, listening, live wave, mute, speaker, pull-down fold and the strip", async ({
  page,
  owner,
}) => {
  const { agent, sessions, closes, errors } = owner;
  await page.setViewportSize(phone);
  await page.addInitScript(harness, { deny: false, locale: "ar" });
  await page.goto(`/app/${agent.id}`);
  await page.locator(".chat-head").getByRole("button", { name: "اتصال صوتي", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/call$/);
  const screen = page.getByTestId("call-view");
  await expect(screen.locator("p.muted")).toHaveText(/^مكالمة · \d\d:\d\d$/);
  await expect(screen.getByRole("heading", { name: agent.name })).toBeVisible();
  await expect(screen.locator(".call-status")).toHaveText("أستمع إليك");
  await expect(screen.locator(".wave i")).toHaveCount(4);
  await page.screenshot({ path: ".runtime/calls/call-screen-ar.png" });
  expect(sessions).toHaveLength(1);
  expect(sessions[0].agent_id).toBe(agent.id);
  // The clock ticks.
  const first = await screen.locator("[data-clock]").textContent();
  await expect(screen.locator("[data-clock]")).not.toHaveText(first ?? "", { timeout: 3000 });
  // «كتم» mutes the real track and the status says so.
  await screen.getByRole("button", { name: "كتم", exact: true }).click();
  await expect(screen.locator(".call-status")).toHaveText("الميكروفون مكتوم");
  await expect(screen.locator(".wave")).toHaveClass(/muted/);
  expect(await page.evaluate(() => window.__calls.streams[0].getAudioTracks()[0].enabled)).toBe(
    false,
  );
  await screen.getByRole("button", { name: "إلغاء الكتم", exact: true }).click();
  // «السماعة» chooses the audio output.
  await screen.getByRole("button", { name: "السماعة", exact: true }).click();
  const outputs = page.locator("dialog");
  await outputs.getByRole("button", { name: "Headset" }).click();
  await expect.poll(() => page.evaluate(() => window.__calls.sink)).toBe("headset-1");
  await expect(screen.getByRole("button", { name: "مفعلة", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  // No back arrow: ⌄ only. Pulling the screen down folds it back to the conversation.
  await expect(page.getByRole("button", { name: "رجوع", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "طي المكالمة", exact: true })).toBeVisible();
  const box = await screen.boundingBox();
  const x = (box?.x ?? 0) + (box?.width ?? 0) / 2;
  const y = (box?.y ?? 0) + 200;
  await screen.dispatchEvent("pointerdown", {
    pointerId: 7,
    pointerType: "touch",
    clientX: x,
    clientY: y,
  });
  await screen.dispatchEvent("pointermove", {
    pointerId: 7,
    pointerType: "touch",
    clientX: x,
    clientY: y + 260,
  });
  await screen.dispatchEvent("pointerup", {
    pointerId: 7,
    pointerType: "touch",
    clientX: x,
    clientY: y + 260,
  });
  await expect(page).toHaveURL(`/app/${agent.id}`);
  // The call's own chat has no strip; any other screen does, and it returns to the call.
  await expect(page.locator(".call-strip")).toHaveCount(0);
  // In-app navigation only: a reload ends a call.
  await page.locator(".chat-head").getByRole("button", { name: "رجوع", exact: true }).click();
  await page.locator("nav.tabbar").getByRole("button", { name: "المهام" }).click();
  await expect(page).toHaveURL(/\/app\/tasks$/);
  const strip = page.locator(".call-strip");
  await expect(strip.locator(".label")).toHaveText(
    new RegExp(`^${agent.name} · جارية · \\d\\d:\\d\\d$`),
  );
  await page.screenshot({ path: ".runtime/calls/call-strip-ar.png" });
  await strip.getByRole("button", { name: "كتم", exact: true }).click();
  await expect(strip.locator(".label")).toContainText("مكتومة");
  await strip
    .getByRole("button", { name: `العودة إلى المكالمة مع ${agent.name}`, exact: true })
    .click();
  await expect(page).toHaveURL(/\/app\/call$/);
  await expect(screen.locator(".call-status")).toHaveText("الميكروفون مكتوم");
  await page.getByRole("button", { name: "طي المكالمة", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/tasks$/);
  // «إنهاء» on the strip ends the call there.
  await strip.getByRole("button", { name: "إنهاء", exact: true }).click();
  await expect(strip).toHaveCount(0);
  await expect.poll(() => closes.length).toBe(1);
  expect(sessions).toHaveLength(1);
  expect(errors).toEqual([]);
});

test("Q58: with no voice provider the call button warns and opens the provider settings", async ({
  page,
  owner,
}) => {
  const { agent, sessions, voice, errors } = owner;
  voice.configured = false;
  await page.setViewportSize(phone);
  await page.addInitScript(harness, { deny: false, locale: "en" });
  await page.goto(`/app/${agent.id}`);
  // aria-disabled marks the missing provider, and a tap still opens the sheet (Q58).
  await page
    .locator(".chat-head")
    .getByRole("button", { name: "Voice call", exact: true })
    .click({ force: true });
  const sheet = page.locator("dialog");
  await expect(sheet).toContainText("Calls are not set up");
  await expect(sheet).toContainText("No voice provider is configured yet.");
  await expect(page).toHaveURL(`/app/${agent.id}`);
  await sheet.getByRole("button", { name: "Set up the voice provider", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/provider\/openai$/);
  // Nothing was dialled and no microphone was asked for.
  expect(sessions).toHaveLength(0);
  expect(await page.evaluate(() => window.__calls.streams.length)).toBe(0);
  expect(errors).toEqual([]);
});

test("microphone refused: the permission sheet opens and the call screen offers a retry", async ({
  page,
  owner,
}) => {
  const { agent, errors } = owner;
  await page.setViewportSize(phone);
  await page.addInitScript(harness, { deny: true, locale: "en" });
  await page.goto(`/app/${agent.id}`);
  await page.locator(".chat-head").getByRole("button", { name: "Voice call", exact: true }).click();
  const sheet = page.locator("dialog");
  await expect(sheet).toContainText("Microphone not allowed");
  await expect(sheet).toContainText("Tap the lock icon next to the site address.");
  await sheet.getByRole("button", { name: "OK", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/call$/);
  await expect(page.getByTestId("call-view").getByRole("button", { name: "Retry" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("incoming call: the page rings for the agent, Decline opens the chat, Answer starts the call", async ({
  page,
  owner,
}) => {
  const { agent, thread, sessions, errors } = owner;
  const call = (id, status = "ringing") => ({
    id,
    agent_id: agent.id,
    thread_id: thread.id,
    status,
    reason: "Gold reached the level you asked about.",
    attention_id: `attention-${id}`,
    expires_at: new Date(Date.now() + 60_000).toISOString(),
    version: 1,
    execution_authorized: false,
  });
  const ringing = [call("ring-1")];
  const responses = [];
  await page.route("**/api/voice/incoming/policy", (route) =>
    route.fulfill({ json: { channel: "call", enabled: true, device_id: "device-1" } }),
  );
  await page.route("**/api/voice/incoming", (route) => route.fulfill({ json: ringing }));
  await page.route("**/api/voice/incoming/*/respond", async (route) => {
    const body = route.request().postDataJSON();
    const id = route.request().url().split("/").at(-2);
    responses.push({ id, ...body });
    ringing.splice(0, ringing.length);
    await route.fulfill({
      json: call(id, body.action === "accept" ? "accepted" : "rejected"),
    });
  });
  await page.setViewportSize(phone);
  await page.addInitScript(harness, { deny: false, locale: "ar" });
  await page.goto("/app/updates");
  // The watcher opens «مكالمة واردة» for the ringing call.
  await expect(page).toHaveURL(/\/app\/incoming\/ring-1$/);
  const incoming = page.locator(".call-page");
  await expect(incoming.getByRole("heading", { name: agent.name })).toBeVisible();
  await expect(incoming).toContainText("مكالمة واردة");
  await expect(incoming).toContainText("Gold reached the level you asked about.");
  await expect(incoming.getByRole("button", { name: "الرد برسالة", exact: true })).toBeVisible();
  await page.screenshot({ path: ".runtime/calls/incoming-ar.png" });
  await incoming.getByRole("button", { name: "رفض", exact: true }).click();
  await expect(page).toHaveURL(`/app/${agent.id}`);
  expect(responses).toEqual([{ id: "ring-1", action: "reject", device_id: "device-1" }]);
  expect(sessions).toHaveLength(0);
  // A second call: «رد» answers it and starts the call in the agent's conversation.
  ringing.push(call("ring-2"));
  await expect(page).toHaveURL(/\/app\/incoming\/ring-2$/, { timeout: 10_000 });
  await incoming.getByRole("button", { name: "رد", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/call$/);
  await expect(page.getByTestId("call-view").locator(".call-status")).toHaveText("أستمع إليك");
  expect(responses.at(-1)).toEqual({ id: "ring-2", action: "accept", device_id: "device-1" });
  expect(sessions).toHaveLength(1);
  expect(sessions[0].agent_id).toBe(agent.id);
  // ⌄ folds it into the agent's chat (the reference's returnView for an answered call).
  await page.getByRole("button", { name: "طي المكالمة", exact: true }).click();
  await expect(page).toHaveURL(`/app/${agent.id}`);
  await page.getByTestId("active-call-pill").click();
  await expect(page).toHaveURL(/\/app\/call$/);
  await page.getByTestId("call-view").getByRole("button", { name: "إنهاء", exact: true }).click();
  await expect(page).toHaveURL(`/app/${agent.id}`);
  expect(errors).toEqual([]);
});
