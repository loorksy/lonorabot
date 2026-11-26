// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: This Playwright scenario runs without Turborepo caching.
import { execFileSync } from "node:child_process";
import { expect, test } from "../ui-test.mjs";

/* P1-05: a request between two agents and its returned result read on the phone as on Web,
   inside the "Agent collaboration" frame: who asked whom, the status and a link to the other
   agent's conversation (tests/web/streaming.spec.mjs draws the same exchange on Web). */
function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_streaming.py", "browser"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

const copy = {
  ar: { kicker: "تعاون الوكلاء", queued: "في الانتظار", completed: "اكتملت" },
  en: { kicker: "Agent collaboration", queued: "Queued", completed: "Completed" },
};

for (const locale of ["ar", "en"])
  test(`Expo ${locale}: a peer request and its result show who asked whom, the status and the link`, async ({
    page,
    context,
    cleanup,
  }) => {
    test.setTimeout(90000);
    const text = copy[locale];
    const data = fixture({ action: "peer_init" });
    cleanup(() => fixture({ ...data, action: "peer_cleanup" }));
    const login = await context.request.post("/api/auth/login", {
      data: {
        email: process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com",
        password: process.env.LONORA_UI_TEST_PASSWORD ?? "ci-only-owner-password",
      },
    });
    expect(login.ok()).toBeTruthy();
    await context.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
    const [sender, recipient] = await Promise.all(
      data.agents.map(
        async (id) => (await (await context.request.get(`/api/agents/${id}`)).json()).name,
      ),
    );
    const cards = page.getByTestId(`peer-card-${data.child.id}`);
    const request = cards.filter({ hasText: "PERSISTED peer request" });
    const answer = cards.filter({ hasText: "PERSISTED peer answer" });
    // Who asked whom, in that order whatever the reading direction.
    const reads = (card, first, second) =>
      expect(card.getByTestId("peer-who")).toHaveText(new RegExp(`${first}.*${second}`));
    // Only the other agent's name is a link, with a full touch target; this conversation's
    // own agent is plain text, so a tap never opens this conversation a second time.
    const links = async (card, other, here) => {
      const link = card.getByRole("link", { name: other, exact: true });
      await expect(link).toHaveCount(1);
      expect((await link.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
      await expect(card.getByRole("link", { name: here, exact: true })).toHaveCount(0);
    };

    await page.goto(`/thread?id=${data.source_thread}`);
    await expect(request).toHaveCount(1);
    await expect(request).toContainText(text.kicker);
    await expect(request).toContainText(text.queued);
    await reads(request, sender, recipient);
    await links(request, recipient, sender);

    // The recipient's name opens its conversation, where the same request is drawn.
    await request.getByRole("link", { name: recipient, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/thread\\?id=${data.target_thread}`));
    await expect(request).toHaveCount(1);
    await reads(request, sender, recipient);
    await links(request, sender, recipient);

    fixture({ ...data, action: "peer_complete" });
    await expect(answer).toHaveCount(1, { timeout: 20000 });
    await expect(answer).toContainText(text.completed);

    // Back in the asker's conversation the returned result reads recipient → sender, without
    // its machine wrapper, and the request now shows the finished status.
    await page.goto(`/thread?id=${data.source_thread}`);
    await expect(answer).toHaveCount(1);
    await reads(answer, recipient, sender);
    await expect(answer).toContainText(text.completed);
    await expect(answer).not.toContainText("peer_outcome");
    await expect(request).toContainText(text.completed);
    await links(answer, recipient, sender);
    await answer.getByRole("link", { name: recipient, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/thread\\?id=${data.target_thread}`));
  });
