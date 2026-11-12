import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

/* The mobile chat list on Expo web (phase 2 port): rows from seeded conversations with their
   ticks, counts and the tab badge, the pin limit, the selection toolbar, archive with undo and the
   archived page, custom lists with the emoji panel, the unified search with its jump to a hit,
   «حذف»/«مسح» hiding history only (Q1, Q44) and the network strip with the offline outbox (Q6). */
function seed(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/chat_lists_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}
let seeded = null;
test.afterEach(async ({ context }) => {
  if (!seeded) return;
  const { fixture, headers } = seeded;
  seeded = null;
  await context.request.delete(`/api/groups/${fixture.group.id}`, { headers });
  for (const agent of fixture.agents)
    await context.request.delete(`/api/agents/${agent.id}`, { headers });
});
async function signIn(context, fixture, locale = "en", theme = "dark") {
  await context.addCookies(
    fixture.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(
    ([language, mode]) => {
      localStorage.setItem("lonora.locale", language);
      localStorage.setItem("lonora.theme", mode);
    },
    [locale, theme],
  );
  const headers = {
    "X-CSRF-Token": fixture.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
  };
  seeded = { fixture, headers };
  return headers;
}
const key = (agent) => `agent:${agent.id}`;
const row = (page, rowKey) => page.locator(`[data-key="${rowKey}"]`);
const toolbar = (page, name = "Selected chats") => page.getByRole("toolbar", { name });
const toast = (page) => page.getByRole("status").filter({ hasNotText: /^$/ });
/** A long press: hold the pointer on the row for 520ms. */
async function hold(page, locator) {
  // Centre the row first: the floating tab bar covers the bottom of a long list.
  await locator.evaluate((element) => element.scrollIntoView({ block: "center" }));
  const box = await locator.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.waitForTimeout(520);
  await page.mouse.up();
}
/** The pull-down filters rest hidden above the first row: bring them into view. */
const showFilters = (page) =>
  page.getByRole("toolbar", { name: /Filter chats|تصفية/ }).scrollIntoViewIfNeeded();

for (const theme of ["dark", "light"])
  test(`${theme}: rows show the server's state: previews, ticks, counts and the tab badge`, async ({
    page,
    context,
  }) => {
    const fixture = seed({ action: "init" });
    const headers = await signIn(context, fixture, "en", theme);
    const [alpha, beta, gamma, delta] = fixture.agents;
    // Muted and paused marks come from the server's state.
    await context.request.post("/api/threads/prefs", {
      headers,
      data: { thread_ids: [fixture.threads[2].id], muted: true },
    });
    await context.request.patch(`/api/agents/${delta.id}`, { headers, data: { paused: true } });
    await page.goto("/");
    await expect(row(page, key(alpha))).toContainText("Yes, it opened.");
    await expect(row(page, key(alpha)).getByLabel("1 unread")).toBeVisible();
    await expect(row(page, key(beta)).getByLabel("2 unread")).toBeVisible();
    await expect(row(page, key(beta))).toContainText("Second update");
    await expect(row(page, key(gamma))).toContainText("You: Accepted only");
    await expect(row(page, key(delta))).toContainText(/\d\d:\d\d/);
    // Q2: one grey tick when the server accepted it; two accent ticks once the run started.
    await expect(
      row(page, key(gamma)).getByRole("img", { name: "Received by the server" }),
    ).toHaveCount(1);
    await expect(row(page, key(gamma)).getByTestId("tick-read")).toHaveCount(0);
    await expect(
      row(page, key(delta)).getByRole("img", { name: "The agent started on it" }),
    ).toHaveCount(1);
    await expect(row(page, key(gamma)).getByRole("img", { name: "Muted" })).toBeVisible();
    await expect(row(page, key(delta))).toContainText("Paused");
    // The group's faces: Lonora's avatar, several of them in the cluster.
    expect(
      await row(page, `group:${fixture.group.id}`).getByTestId("trading-avatar").count(),
    ).toBeGreaterThanOrEqual(2);
    // A group with nothing said yet shows its purpose.
    await expect(row(page, `group:${fixture.group.id}`)).toContainText("Gold research");
    const inbox = await (await context.request.get("/api/threads/inbox")).json();
    const total = inbox
      .filter((entry) => !entry.archived && !entry.muted)
      .reduce((sum, entry) => sum + (entry.unread_count || (entry.marked_unread ? 1 : 0)), 0);
    await expect(page.getByTestId("tab-chats")).toContainText(String(total));
    await page.screenshot({ path: `.runtime/mobile-chats-${theme}.png`, animations: "disabled" });
  });

test("pinning a fourth chat is refused locally and when the server answers 409; pins lead in pin order", async ({
  page,
  context,
}) => {
  const fixture = seed({ action: "init" });
  const headers = await signIn(context, fixture);
  const [alpha, beta, gamma, delta] = fixture.agents;
  const pin = (ids, pinned) =>
    context.request.post("/api/threads/prefs", { headers, data: { thread_ids: ids, pinned } });
  const before = await (await context.request.get("/api/threads/inbox")).json();
  const earlier = before.filter((entry) => entry.pinned_order != null).map((e) => e.thread_id);
  if (earlier.length) await pin(earlier, false);
  const mine = [fixture.threads[0].id, fixture.threads[1].id, fixture.threads[2].id];
  expect((await pin(mine, true)).ok()).toBe(true);
  try {
    await page.goto("/");
    await expect(row(page, key(alpha))).toBeVisible();
    const keys = await page
      .locator("[data-key]")
      .evaluateAll((rows) => rows.slice(0, 3).map((r) => r.dataset.key));
    expect(keys).toEqual([key(gamma), key(beta), key(alpha)]);
    await expect(row(page, key(alpha)).getByRole("img", { name: "Pinned" })).toBeVisible();
    // Refused locally: three are pinned already.
    await hold(page, row(page, key(delta)));
    await toolbar(page).getByRole("button", { name: "Pin", exact: true }).click();
    await expect(page.getByText("You can pin 3 chats only")).toBeVisible();
    await toolbar(page).getByRole("button", { name: "Cancel the selection" }).click();
    // A stale view (another device pinned meanwhile) reaches the server, which refuses (409).
    await page.route("**/api/threads/inbox", async (route) => {
      const rows = await (await route.fetch()).json();
      await route.fulfill({ json: rows.map((entry) => ({ ...entry, pinned_order: null })) });
    });
    await page.reload();
    await expect(row(page, key(delta))).toBeVisible();
    const refused = page.waitForResponse(
      (response) => response.url().endsWith("/api/threads/prefs") && response.status() === 409,
    );
    await hold(page, row(page, key(delta)));
    await toolbar(page).getByRole("button", { name: "Pin", exact: true }).click();
    await refused;
    await expect(page.getByText("You can pin 3 chats only")).toBeVisible();
  } finally {
    await page.unroute("**/api/threads/inbox");
    await pin(mine, false);
    if (earlier.length) await pin(earlier, true);
  }
});

test("selection: long press, toolbar, favourites and select all; archive with undo; the archived page", async ({
  page,
  context,
}) => {
  const fixture = seed({ action: "init" });
  await signIn(context, fixture, "ar");
  const [alpha, beta, gamma] = fixture.agents;
  await page.goto("/");
  await expect(row(page, key(alpha))).toBeVisible();
  await hold(page, row(page, key(alpha)));
  const bar = toolbar(page, "المحادثات المحددة");
  await expect(bar).toBeVisible();
  await expect(bar).toContainText("1");
  await row(page, key(beta)).click();
  await expect(bar).toContainText("2");
  await bar.getByRole("button", { name: "المزيد" }).click();
  await page.getByRole("button", { name: "إضافة إلى المفضلة" }).click();
  await expect(page.getByText("أُضيفت إلى المفضلة")).toBeVisible();
  await expect(bar).toHaveCount(0);
  await showFilters(page);
  await page.getByRole("button", { name: "المفضلة", exact: true }).click();
  await expect(row(page, key(alpha))).toBeVisible();
  await expect(row(page, key(beta))).toBeVisible();
  await expect(row(page, key(gamma))).toHaveCount(0);
  await page.getByRole("button", { name: "الكل", exact: true }).click();
  // ⋮ → select all picks every visible row; ✕ ends it.
  await hold(page, row(page, key(alpha)));
  await bar.getByRole("button", { name: "المزيد" }).click();
  await page.getByRole("button", { name: "تحديد الكل" }).click();
  const visible = await page.locator("[data-key]").count();
  await expect(bar).toContainText(String(visible));
  await bar.getByRole("button", { name: "إلغاء التحديد" }).click();
  await expect(bar).toHaveCount(0);
  // Archive one with an undo, then archive again and open «المؤرشفة».
  await hold(page, row(page, key(gamma)));
  await bar.getByRole("button", { name: "أرشفة", exact: true }).click();
  await expect(row(page, key(gamma))).toHaveCount(0);
  await page.getByRole("button", { name: "تراجع" }).click();
  await expect(row(page, key(gamma))).toBeVisible();
  await hold(page, row(page, key(gamma)));
  await bar.getByRole("button", { name: "أرشفة", exact: true }).click();
  await page.getByTestId("archive-row").click();
  await expect(row(page, key(gamma))).toBeVisible();
  const keep = page.getByRole("switch", { name: "إبقاء المحادثات مؤرشفة" });
  const was = await keep.getAttribute("aria-checked");
  await keep.click();
  await expect
    .poll(async () =>
      String((await (await context.request.get("/api/threads/settings")).json()).keep_archived),
    )
    .toBe(was === "true" ? "false" : "true");
  await keep.click();
  await hold(page, row(page, key(gamma)));
  await bar.getByRole("button", { name: "إلغاء الأرشفة" }).click();
  await expect(page.getByText("أُعيدت المحادثة إلى القائمة")).toBeVisible();
});

test("a custom list is created with the emoji panel, filters the rows and deletes with undo", async ({
  page,
  context,
}) => {
  const fixture = seed({ action: "init" });
  await signIn(context, fixture);
  const [alpha] = fixture.agents;
  await page.goto("/");
  await expect(row(page, key(alpha))).toBeVisible();
  await showFilters(page);
  await page.getByRole("button", { name: "New list", exact: true }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByRole("heading", { name: "New list" })).toBeVisible();
  const name = sheet.getByLabel("List name");
  await name.fill("Work");
  await sheet.getByRole("button", { name: "Add an emoji" }).click();
  await expect(sheet.getByLabel("Emojis")).toBeVisible();
  await sheet.getByLabel("Emojis").getByRole("button").nth(3).click();
  await expect(name).not.toHaveValue("Work");
  const listName = `Work ${Date.now() % 10000}`;
  await name.fill(listName);
  await sheet.getByRole("button", { name: "Add agents or groups" }).click();
  await sheet.getByRole("checkbox", { name: new RegExp(alpha.name) }).click();
  await sheet.getByRole("checkbox", { name: new RegExp(fixture.group.payload.name) }).click();
  await sheet.getByRole("button", { name: "Create the list · 2" }).click();
  await expect(page.getByText(`List «${listName}» created`)).toBeVisible();
  await expect(page.locator("[data-key]")).toHaveCount(2);
  const lists = await (await context.request.get("/api/chat-lists")).json();
  const saved = lists.find((list) => list.name === listName);
  expect(saved.thread_ids.sort()).toEqual(
    [fixture.threads[0].id, fixture.group.state.thread_id].sort(),
  );
  await page.getByRole("button", { name: listName, exact: true }).click({ delay: 600 });
  await page.getByRole("button", { name: "Delete the list" }).click();
  await expect(page.getByRole("button", { name: listName, exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByRole("button", { name: listName, exact: true })).toBeVisible();
});

test("search browses recent content and finds a message; the new-chat sheet leads to «Manage agents»", async ({
  page,
  context,
}) => {
  const fixture = seed({ action: "init" });
  await signIn(context, fixture);
  const [alpha] = fixture.agents;
  await page.goto("/");
  await expect(row(page, key(alpha))).toBeVisible();
  const field = page.getByRole("searchbox", { name: "Search in Lonora" });
  await field.click();
  await expect(page.getByRole("tab", { name: "Messages" })).toBeVisible();
  await expect(page.getByTestId("search-section-chats")).toBeVisible();
  await field.fill("Second update");
  await expect(page.getByTestId("search-section-messages")).toContainText("Second update");
  await page.getByRole("tab", { name: "Chats" }).click();
  await expect(page.getByText("No results in this category")).toBeVisible();
  await field.fill(alpha.name.split(" ")[0]);
  await expect(page.getByTestId("search-section-chats")).toContainText(alpha.name);
  await field.fill("Second update");
  await page.getByRole("tab", { name: "All", exact: true }).click();
  await page.getByTestId("search-hit-messages").first().click();
  await expect(page).toHaveURL(/\/thread\?.*around=\d+/);
  await page.goBack();
  await expect(field).toBeVisible();
  await page.getByRole("button", { name: "Close search" }).click();
  await expect(row(page, key(alpha))).toBeVisible();
  await page.getByRole("button", { name: "New chat", exact: true }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByRole("button", { name: /^New agent/ })).toBeVisible();
  await expect(sheet.getByTestId(`new-chat-agent-${alpha.id}`)).toBeVisible();
  await sheet.getByRole("button", { name: "Manage agents" }).click();
  await expect(page.getByTestId(`agent-row-${alpha.id}`)).toBeVisible();
});

test("«حذف» and «مسح» hide the history for the owner; agents and groups are never deleted", async ({
  page,
  context,
}) => {
  const fixture = seed({ action: "init" });
  await signIn(context, fixture);
  const [alpha] = fixture.agents;
  const deletes = [];
  page.on("request", (request) => {
    if (request.method() === "DELETE") deletes.push(request.url());
  });
  await page.goto("/");
  await expect(row(page, key(alpha))).toContainText("Yes, it opened.");
  await hold(page, row(page, key(alpha)));
  await toolbar(page).getByRole("button", { name: "Delete", exact: true }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByRole("heading", { name: "Delete the chats?" })).toBeVisible();
  await sheet.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(row(page, key(alpha))).toBeVisible();
  await expect(row(page, key(alpha))).not.toContainText("Yes, it opened.");
  expect(deletes).toEqual([]);
  const agents = await (await context.request.get("/api/agents")).json();
  expect(agents.some((agent) => agent.id === alpha.id)).toBe(true);
  const inbox = await (await context.request.get("/api/threads/inbox")).json();
  expect(
    inbox.find((entry) => entry.thread_id === fixture.threads[0].id).hidden_before_seq,
  ).toBeGreaterThan(0);
  // A group row too: «مسح الرسائل» from the ⋮ menu hides its history; the group stays (Q1, Q44).
  const groupKey = `group:${fixture.group.id}`;
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await hold(page, row(page, groupKey));
  await toolbar(page).getByRole("button", { name: "More" }).click();
  await page.getByRole("button", { name: "Clear the messages", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Clear", exact: true }).click();
  await expect(row(page, groupKey)).toBeVisible();
  expect(deletes).toEqual([]);
  const groups = await (await context.request.get("/api/groups")).json();
  expect(groups.some((group) => group.id === fixture.group.id)).toBe(true);
});

test("offline outbox (Q6): a message waiting for the network shows on its row and in the strip", async ({
  page,
  context,
}) => {
  const fixture = seed({ action: "init" });
  await signIn(context, fixture, "ar");
  const [alpha] = fixture.agents;
  await page.goto(`/thread?id=${fixture.threads[0].id}`);
  // The request never answers: the intent stays «sending» in this device's outbox.
  await page.route("**/api/threads/*/messages", (route) => {
    if (route.request().method() !== "POST") return route.continue();
  });
  const text = `queued ${Date.now() % 10000}`;
  await page.getByLabel("اكتب رسالة…", { exact: true }).fill(text);
  await page.getByRole("button", { name: "إرسال", exact: true }).click();
  await context.setOffline(true);
  await page.getByRole("button", { name: "رجوع", exact: true }).click();
  await expect(row(page, key(alpha))).toContainText(text);
  await expect(row(page, key(alpha)).getByRole("img", { name: "بانتظار الشبكة…" })).toBeVisible();
  await expect(page.getByTestId("network-strip")).toContainText("لا يوجد اتصال بالإنترنت", {
    timeout: 20000,
  });
  await expect(page.getByTestId("network-strip")).toContainText("رسالة واحدة تنتظر");
  await context.setOffline(false);
});

test("offline: the network strip says so and a restored connection clears it", async ({
  page,
  context,
}) => {
  const fixture = seed({ action: "init" });
  await signIn(context, fixture, "ar");
  const [alpha] = fixture.agents;
  await page.goto("/");
  await expect(row(page, key(alpha))).toBeVisible();
  await context.setOffline(true);
  await expect(page.getByTestId("network-strip")).toContainText("لا يوجد اتصال بالإنترنت", {
    timeout: 20000,
  });
  await context.setOffline(false);
  await expect(page.getByTestId("network-strip")).toContainText("عاد الاتصال", {
    timeout: 20000,
  });
});

test("no agent creation form: the agents page and «محادثة جديدة» offer none (P5)", async ({
  page,
  context,
}) => {
  const fixture = seed({ action: "init" });
  await signIn(context, fixture, "ar");
  await page.goto("/agents");
  await expect(page.getByRole("button", { name: "إنشاء وكيل" })).toHaveCount(0);
  await page.goto("/");
  await page.getByRole("button", { name: "محادثة جديدة", exact: true }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByRole("button", { name: /^مجموعة جديدة/ })).toBeVisible();
  await expect(sheet.getByRole("button", { name: /^وكيل جديد/ })).toHaveCount(0);
});

test("opening an unread chat reads it on the server; the row and the tab badge follow", async ({
  page,
  context,
}) => {
  const fixture = seed({ action: "init" });
  await signIn(context, fixture);
  const beta = fixture.agents[1];
  await page.goto("/");
  await expect(row(page, key(beta)).getByLabel("2 unread")).toBeVisible();
  await row(page, key(beta)).click();
  await expect(page).toHaveURL(/\/thread/);
  await expect
    .poll(async () => {
      const rows = await (await context.request.get("/api/threads/inbox")).json();
      return rows.find((entry) => entry.thread_id === fixture.threads[1].id).unread_count;
    })
    .toBe(0);
  await page.goBack();
  await expect(row(page, key(beta)).getByLabel("2 unread")).toHaveCount(0);
});

test("search pages a long result list by 32 with «Show more»", async ({ page, context }) => {
  test.setTimeout(90000);
  const fixture = seed({ action: "init", bulk: 40 });
  await signIn(context, fixture);
  await page.goto("/");
  const field = page.getByRole("searchbox", { name: "Search in Lonora" });
  await field.click();
  await field.fill("Paging needle");
  await page.getByRole("tab", { name: "Messages" }).click();
  const hits = page.getByTestId("search-hit-messages");
  await expect(hits).toHaveCount(32);
  await page.getByRole("button", { name: "Show more", exact: true }).click();
  await expect(hits).toHaveCount(40);
});
