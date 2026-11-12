// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright reads explicitly scoped disposable-test configuration.
// Negotiation is a deterministic harness; auth, agents and selected conversation APIs remain real.
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { brokerFixture } from "./broker-fixture.mjs";

test("the call screen survives navigation with its origin, real track mute and ordered logout", async ({
  page,
  context,
}) => {
  test.setTimeout(90_000);
  const credentials = {
    email: process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com",
    password: process.env.LONORA_UI_TEST_PASSWORD ?? "ci-only-owner-password",
  };
  const status = await (await context.request.get("/api/onboarding")).json();
  if (!status.owner_initialized)
    expect(
      (
        await context.request.post("/api/onboarding", {
          data: {
            ...credentials,
            bootstrap_token:
              process.env.LONORA_BOOTSTRAP_TOKEN ?? "lonora-ui-bootstrap-ci-only-2026",
          },
        })
      ).status(),
    ).toBe(201);
  const login = await context.request.post("/api/auth/login", { data: credentials });
  expect(login.status()).toBe(200);
  const headers = { "X-CSRF-Token": (await login.json()).csrf };
  const ids = [];
  const post = async (path, data) => {
    if (path === "/agents") data = { ...data, ...broker.binding };
    const response = await context.request.post(`/api${path}`, { data, headers });
    expect(response.ok()).toBeTruthy();
    return response.json();
  };
  const broker = await brokerFixture(context, headers);
  const calls = [],
    closes = [],
    ordering = [],
    snapshots = { input: [], output: [] };
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  try {
    const first = await post("/agents", { name: `Voice UI ${randomUUID()}`, color: "#3B82F6" });
    ids.push(first.id);
    const other = await post("/agents", { name: `Other voice UI ${randomUUID()}` });
    ids.push(other.id);
    const canonical = await post(`/agents/${first.id}/conversation`, {});
    const history = await post("/threads", {
      agent_id: first.id,
      title: "Selected historical conversation",
    });
    await post(`/threads/${history.id}/messages`, {
      content: "This is the originating historical chat.",
      client_nonce: randomUUID(),
    });
    await page.addInitScript(() => {
      localStorage.setItem("lonora.locale", "en");
      const harness = {
        peers: [],
        streams: [],
        micCalls: 0,
        pending: false,
        release: null,
        remoteGain: null,
      };
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
        harness.streams.push(destination.stream);
        return { stream: destination.stream, gain, context };
      };
      Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
        configurable: true,
        value: async () => {
          harness.micCalls += 1;
          if (harness.pending)
            await new Promise((resolve) => {
              harness.release = resolve;
            });
          return audio(0.1).stream;
        },
      });
      class Peer {
        constructor() {
          this.iceGatheringState = "complete";
          this.connectionState = "new";
          this.channel = null;
          this.remote = null;
          harness.peers.push(this);
        }
        addTrack() {}
        createDataChannel() {
          this.channel = {
            readyState: "open",
            onmessage: null,
            onclose: null,
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
          return { type: "offer", sdp: "v=0\r\nvoice-ui-fixture-offer" };
        }
        async setLocalDescription(value) {
          this.localDescription = value;
        }
        async setRemoteDescription() {
          this.connectionState = "connected";
          const remote = audio(0);
          this.remote = remote.stream;
          harness.remoteGain = remote.gain;
          this.ontrack?.({ track: remote.stream.getAudioTracks()[0], streams: [remote.stream] });
          this.channel.onmessage?.({ data: JSON.stringify({ type: "session.started" }) });
        }
        addEventListener() {}
        removeEventListener() {}
        close() {
          this.connectionState = "closed";
          this.remote?.getTracks().forEach((track) => {
            track.stop();
          });
        }
      }
      window.RTCPeerConnection = Peer;
      window.__voiceHarness = harness;
    });
    await page.route("**/api/voice/status", (route) =>
      route.fulfill({
        json: { transport: "gpt_live", transport_configured: true, model: "voice-ui-test-only" },
      }),
    );
    await page.route("**/api/voice/sessions", async (route) => {
      calls.push(route.request().postDataJSON());
      await route.fulfill({
        status: 201,
        json: { session_id: `voice-ui-${calls.length}`, sdp: "v=0\r\nvoice-ui-fixture-answer" },
      });
    });
    await page.route("**/api/voice/sessions/voice-ui-*", async (route) => {
      if (route.request().method() === "DELETE") {
        closes.push(route.request().url());
        ordering.push("voice-close");
        return route.fulfill({ json: { closed: true } });
      }
      return route.fulfill({
        json: {
          session_id: `voice-ui-${calls.length}`,
          status: "connected",
          input: snapshots.input,
          output: snapshots.output,
          finalized: false,
        },
      });
    });
    page.on("request", (request) => {
      if (request.method() === "POST" && request.url().endsWith("/api/auth/logout"))
        ordering.push("owner-logout");
    });
    await page.goto(`/app/${first.id}?thread=${history.id}`);
    await expect(
      page.getByText("This is the originating historical chat.", { exact: true }),
    ).toBeVisible();
    expect(await page.locator('[aria-label="Message composer"] [aria-label="Voice"]').count()).toBe(
      0,
    );
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(
      page.locator(".chat-head").getByRole("button", { name: "Voice call", exact: true }),
    ).toBeVisible();
    const approval = {
      id: randomUUID(),
      thread_id: history.id,
      created_at: new Date().toISOString(),
      status: "pending",
      requests: [
        {
          action: "buy",
          symbol: broker.symbol,
          volume: "0.01",
          operation_id: "voice-approved-operation",
        },
      ],
      results: [],
    };
    const rejectable = {
      ...approval,
      id: randomUUID(),
      requests: [
        {
          action: "sell",
          symbol: broker.symbol,
          volume: "0.01",
          operation_id: "voice-rejected-operation",
        },
      ],
      results: [],
    };
    await page.route(`**/api/trading/approvals/${rejectable.id}/decision`, async (route) => {
      expect(route.request().postDataJSON()).toEqual({ decision: "reject" });
      rejectable.status = "rejected";
      await route.fulfill({ json: rejectable });
    });
    await page.route("**/api/trading/approvals?*", (route) =>
      route.fulfill({
        json:
          new URL(route.request().url()).searchParams.get("thread_id") === history.id
            ? [approval, rejectable]
            : [],
      }),
    );
    let decisions = 0;
    await page.route(`**/api/trading/approvals/${approval.id}/decision`, async (route) => {
      expect(route.request().postDataJSON()).toEqual({ decision: "approve" });
      decisions++;
      approval.status = "completed";
      approval.results = [
        {
          operation_id: "voice-approved-operation",
          status: "confirmed",
          broker_id: "voice-native-ticket",
          details: { price: "1.23456" },
        },
      ];
      await route.fulfill({ json: approval });
    });
    await page.getByRole("button", { name: "Voice call", exact: true }).dblclick();
    // The call screen is its own route (the reference's «المكالمة»).
    await expect(page).toHaveURL(/\/app\/call$/);
    await expect(page.getByTestId("call-view")).toBeVisible();
    await expect.poll(() => calls.length).toBe(1);
    const call = page.getByTestId("call-view");
    const approvedCard = call.locator(`[data-trade-approval="${approval.id}"]`);
    await expect(approvedCard.getByRole("button", { name: "Reject", exact: true })).toBeVisible();
    await approvedCard.getByRole("button", { name: "Approve", exact: true }).click();
    await expect(call.getByText("voice-native-ticket", { exact: true })).toBeVisible();
    await expect(approvedCard.getByRole("button", { name: "Approve", exact: true })).toHaveCount(0);
    const rejectedCard = call.locator(`[data-trade-approval="${rejectable.id}"]`);
    await rejectedCard.getByRole("button", { name: "Reject", exact: true }).click();
    await expect(rejectedCard.getByText("Rejected", { exact: true })).toBeVisible();
    await expect(rejectedCard.getByRole("button", { name: "Approve", exact: true })).toHaveCount(0);
    expect(decisions).toBe(1);

    expect(calls[0].agent_id).toBe(first.id);
    expect(calls[0].thread_id).toBe(history.id);
    expect(calls[0].thread_id).not.toBe(canonical.id);
    await expect.poll(() => page.evaluate(() => window.__voiceHarness.micCalls)).toBe(1);
    await expect(page.locator(".call-status")).toHaveText("Listening to you");
    await page.evaluate(() => {
      window.__voiceHarness.remoteGain.gain.value = 0.25;
    });
    await expect(page.locator(".call-status")).toHaveText("Speaking");
    // The wave follows the call's real levels.
    await expect
      .poll(() =>
        page
          .locator(".call-page .wave i")
          .evaluateAll((bars) =>
            bars.some(
              (bar) =>
                Number.parseFloat(/scaleY\(([\d.]+)\)/.exec(bar.style.transform)?.[1] ?? "0") > 0.4,
            ),
          ),
      )
      .toBeTruthy();
    await call.getByRole("button", { name: "Mute", exact: true }).click();
    await expect(page.locator(".call-status")).toHaveText("Microphone muted");
    expect(
      await page.evaluate(() => window.__voiceHarness.streams[0].getAudioTracks()[0].enabled),
    ).toBe(false);
    await call.getByRole("button", { name: "Unmute", exact: true }).click();
    expect(
      await page.evaluate(() => window.__voiceHarness.streams[0].getAudioTracks()[0].enabled),
    ).toBe(true);
    const fragment = {
      event_id: "heard-once",
      start_ms: 0,
      end_ms: 500,
      delta: "A unique spoken phrase.",
    };
    snapshots.input.push(fragment);
    await page.evaluate((fragment) => {
      const channel = window.__voiceHarness.peers[0].channel;
      const event = { type: "session.input_transcript.delta", ...fragment };
      channel.onmessage({ data: JSON.stringify(event) });
      channel.onmessage({ data: JSON.stringify(event) });
    }, fragment);
    await expect(
      page.getByRole("button", { name: "Conversation transcript", exact: true }),
    ).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Interrupt", exact: true })).toHaveCount(0);
    await expect(page.locator(".call-name, .call-duration, .call-transcript")).toHaveCount(0);
    await page.waitForTimeout(2200);
    await expect(page.getByText("A unique spoken phrase.", { exact: true })).toHaveCount(0);
    await page.screenshot({ path: ".runtime/rakazo-parity/voice-call-screen.png" });
    // ⌄ folds the call back to the conversation it was opened from; its header keeps the pill.
    await page.getByRole("button", { name: "Fold the call", exact: true }).click();
    await expect(page).toHaveURL(`/app/${first.id}?thread=${history.id}`);
    await expect(page.locator(".chat-head").getByTestId("active-call-pill")).toBeVisible();
    // The call's own chat has no strip.
    await expect(page.locator(".call-strip")).toHaveCount(0);
    await page.getByTestId("active-call-pill").click();
    await expect(page).toHaveURL(/\/app\/call$/);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.getByRole("button", { name: "Fold the call", exact: true }).click();
    await page.getByRole("button", { name: "Chat menu", exact: true }).click();
    await page.getByRole("menuitem", { name: "Agent files" }).click();
    // «الملفات» of this agent (UI phase 4b), with the call strip under the top bar.
    await expect(page).toHaveURL(/\/app\/artifacts\?agent=[^&]+$/);
    const strip = page.locator(".call-strip");
    await expect(strip).toContainText(first.name);
    await expect(strip).toContainText("In progress");
    await strip.getByRole("button", { name: "Mute", exact: true }).click();
    await expect(strip).toContainText("Muted");
    expect(
      await page.evaluate(() => window.__voiceHarness.streams[0].getAudioTracks()[0].enabled),
    ).toBe(false);
    await strip.getByRole("button", { name: "Unmute", exact: true }).click();
    // Another agent's chat keeps the strip; its header opens the running call.
    await page.locator(`.desktop-list [data-inbox-agent-id="${other.id}"]`).click();
    await expect(page.locator(".call-strip")).toContainText(first.name);
    await page.getByRole("button", { name: "Open active call", exact: true }).click();
    await expect(
      page.getByRole("region", { name: `Call with ${first.name}`, exact: true }),
    ).toBeVisible();
    expect(calls).toHaveLength(1);
    expect(closes).toHaveLength(0);
    // The strip returns to the call; ending it on its screen returns to where it was opened.
    await page.getByRole("button", { name: "Fold the call", exact: true }).click();
    await expect(page).toHaveURL(`/app/${other.id}`);
    await page
      .getByRole("button", { name: `Return to the call with ${first.name}`, exact: true })
      .click();
    await expect(page).toHaveURL(/\/app\/call$/);
    await page.getByTestId("call-view").getByRole("button", { name: "End", exact: true }).click();
    await expect(page).toHaveURL(`/app/${other.id}`);
    await expect(page.locator("#toast")).toContainText("The call ended.");
    await expect(page.locator(".call-strip")).toHaveCount(0);
    await expect.poll(() => closes.length).toBe(1);
    expect(
      await page.evaluate(() =>
        window.__voiceHarness.streams
          .slice(0, 2)
          .every((stream) => stream.getTracks().every((track) => track.readyState === "ended")),
      ),
    ).toBe(true);
    await page.goto(`/app/${first.id}?thread=${history.id}`);
    await page.getByRole("button", { name: "Voice call", exact: true }).click();
    await expect.poll(() => calls.length).toBe(2);
    await page
      .locator(".desktop-rail")
      .getByRole("button", { name: "Settings", exact: true })
      .click();
    await page.getByRole("button", { name: /^Sign out/ }).click();
    // «تسجيل الخروج» asks once in a sheet.
    await page.locator("dialog").getByRole("button", { name: "Sign out", exact: true }).click();
    // Signing out reopens the intro (the reference's signOut); skip to the sign-in step.
    await page.getByRole("button", { name: "Skip", exact: true }).click();
    await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeVisible();
    expect(closes).toHaveLength(2);
    expect(ordering.slice(-2)).toEqual(["voice-close", "owner-logout"]);
    expect(
      await page.evaluate(() =>
        window.__voiceHarness.streams.every((stream) =>
          stream.getTracks().every((track) => track.readyState === "ended"),
        ),
      ),
    ).toBe(true);
    expect(errors).toEqual([]);
  } finally {
    await broker.close();
    const renewed = await context.request.post("/api/auth/login", { data: credentials });
    if (renewed.ok())
      for (const id of ids)
        expect([200, 404]).toContain(
          (
            await context.request.delete(`/api/agents/${id}`, {
              headers: { "X-CSRF-Token": (await renewed.json()).csrf },
            })
          ).status(),
        );
  }
});
