// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright reads explicitly scoped disposable-test configuration.
// Negotiation is a deterministic harness; auth, agents and selected conversation APIs remain real.
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

test("compact call survives navigation with its origin, real track mute and ordered logout", async ({
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
    const response = await context.request.post(`/api${path}`, { data, headers });
    expect(response.ok()).toBeTruthy();
    return response.json();
  };
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
      page.locator(".tpl-chat-header").getByRole("button", { name: "Call", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Call", exact: true }).dblclick();
    await expect(page.getByTestId("call-view")).toBeVisible();
    await expect.poll(() => calls.length).toBe(1);
    expect(calls[0].agent_id).toBe(first.id);
    expect(calls[0].thread_id).toBe(history.id);
    expect(calls[0].thread_id).not.toBe(canonical.id);
    await expect.poll(() => page.evaluate(() => window.__voiceHarness.micCalls)).toBe(1);
    await expect(page.locator(".call-status")).toHaveText("Listening");
    await page.evaluate(() => {
      window.__voiceHarness.remoteGain.gain.value = 0.25;
    });
    await expect(page.locator(".call-status")).toHaveText("Speaking");
    await expect
      .poll(() =>
        page
          .locator(".call-waveform > span")
          .evaluateAll((bars) => bars.some((bar) => Number.parseFloat(bar.style.height) > 5)),
      )
      .toBeTruthy();
    await page.getByRole("button", { name: "Mute microphone", exact: true }).click();
    expect(
      await page.evaluate(() => window.__voiceHarness.streams[0].getAudioTracks()[0].enabled),
    ).toBe(false);
    await page.getByRole("button", { name: "Unmute microphone", exact: true }).click();
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
    await page.screenshot({ path: ".runtime/rakazo-parity/voice-floating-card.png" });
    await page.getByRole("button", { name: "Voice settings", exact: true }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByRole("button", { name: "Close", exact: true }).click();
    await expect(page.getByTestId("active-call-pill")).toBeVisible();
    await expect(page.locator(".tpl-chat-header").getByTestId("active-call-pill")).toBeVisible();
    await page.getByTestId("active-call-pill").click();
    await expect(page.getByTestId("call-view")).toBeVisible();
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.getByRole("button", { name: "Minimize call", exact: true }).click();
    await page.locator(".tpl-account-trigger").click();
    await page.getByRole("menuitem", { name: "Artifacts", exact: true }).click();
    await expect(page).toHaveURL(/\/app\/artifacts$/);
    await expect(page.getByTestId("active-call-pill")).toBeVisible();
    await page.getByRole("button", { name: other.name, exact: true }).click();
    await page.getByRole("button", { name: "Open active call", exact: true }).click();
    await expect(
      page.getByRole("region", { name: `Call with ${first.name}`, exact: true }),
    ).toBeVisible();
    expect(calls).toHaveLength(1);
    expect(closes).toHaveLength(0);
    await page
      .getByRole("button", { name: `Open conversation with ${first.name}`, exact: true })
      .click();
    await expect(page).toHaveURL(`/app/${first.id}?thread=${history.id}`);
    await page.getByRole("button", { name: "End call", exact: true }).click();
    await expect(page.getByTestId("call-view")).not.toBeVisible();
    await expect.poll(() => closes.length).toBe(1);
    expect(
      await page.evaluate(() =>
        window.__voiceHarness.streams
          .slice(0, 2)
          .every((stream) => stream.getTracks().every((track) => track.readyState === "ended")),
      ),
    ).toBe(true);
    await page.getByRole("button", { name: "Call", exact: true }).click();
    await expect.poll(() => calls.length).toBe(2);
    await page.locator(".tpl-account-trigger").click();
    await page.getByRole("menuitem", { name: "Sign out", exact: true }).click();
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
