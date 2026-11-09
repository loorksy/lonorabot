import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

/* The chat list, its owner state on the server and the unified search
   (docs/ui-reference/Lonora-Desktop-37.html, phase 2): rows from seeded conversations, the
   pin limit, mute against critical attention, archive with undo, the selection toolbar,
   custom lists, search categories with the jump to a hit, «حذف»/«مسح» hiding history only
   (owner decision Q1) and the offline queue (owner decision Q6). */
function seed(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/chat_lists_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}
/* The agents and the group a test seeded leave with it: their queued runs (a message
   sent here) must not reach a later spec's scripted worker. API cleanup, not the UI. */
let seeded = null;
test.afterEach(async ({ context }) => {
  if (!seeded) return;
  const { fixture, headers } = seeded;
  seeded = null;
  await context.request.delete(`/api/groups/${fixture.group.id}`, { headers });
  for (const agent of fixture.agents)
    await context.request.delete(`/api/agents/${agent.id}`, { headers });
});
async function signIn(context, fixture, locale = "en") {
  await context.addCookies(
    fixture.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
  const headers = {
    "X-CSRF-Token": fixture.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
  };
  if (fixture.agents && fixture.group) seeded = { fixture, headers };
  return headers;
}
const key = (agent) => `agent:${agent.id}`;
const desktopRow = (page, rowKey) => page.locator(`.desktop-list .thread[data-key="${rowKey}"]`);
const toolbar = (page, name = "Selected chats") => page.getByRole("toolbar", { name });

test("rows show the server's state: previews, ticks, unread counts and the badge", async ({
  page,
  context,
}) => {
  const fixture = seed({ action: "init" });
  await signIn(context, fixture);
  const [alpha, beta, gamma, delta] = fixture.agents;
  await page.goto("/app");
  await expect(desktopRow(page, key(alpha))).toContainText("Yes, it opened.");
  await expect(desktopRow(page, key(alpha)).locator(".count")).toContainText("1");
  await expect(desktopRow(page, key(alpha))).toHaveClass(/unread/);
  await expect(desktopRow(page, key(beta)).locator(".count")).toContainText("2");
  await expect(desktopRow(page, key(beta))).toContainText("Second update");
  // Q2: one grey tick when the server accepted it; two accent ticks once the run started.
  await expect(desktopRow(page, key(gamma))).toContainText("You: Accepted only");
  await expect(desktopRow(page, key(gamma)).locator(".pv .tick")).toHaveCount(1);
  await expect(desktopRow(page, key(gamma)).locator(".pv .read")).toHaveCount(0);
  await expect(desktopRow(page, key(delta)).locator(".pv .read")).toHaveCount(1);
  await expect(desktopRow(page, key(delta)).locator("time")).toHaveText(/^\d\d:\d\d$/);
  // A group with nothing said yet shows its purpose.
  await expect(desktopRow(page, `group:${fixture.group.id}`)).toContainText("Gold research");
  // The Chats badge: unread over conversations neither archived nor muted.
  const inbox = await (await context.request.get("/api/threads/inbox")).json();
  const total = inbox
    .filter((entry) => !entry.archived && !entry.muted)
    .reduce((sum, entry) => sum + (entry.unread_count || (entry.marked_unread ? 1 : 0)), 0);
  await expect(page.locator(".desktop-rail .rail-badge")).toHaveText(String(total));
  // Opening a chat reads it on the server; the row and the badge follow.
  await desktopRow(page, key(beta)).click();
  await expect(page).toHaveURL(new RegExp(`/app/${beta.id}`));
  await expect(desktopRow(page, key(beta)).locator(".count")).toHaveCount(0);
  await expect(page.locator(".desktop-rail .rail-badge")).toHaveText(String(total - 2));
  await expect
    .poll(async () => {
      const rows = await (await context.request.get("/api/threads/inbox")).json();
      return rows.find((entry) => entry.thread_id === fixture.threads[1].id).unread_count;
    })
    .toBe(0);
});

test("pinning a fourth chat is refused locally and when the server answers 409", async ({
  page,
  context,
}) => {
  const fixture = seed({ action: "init" });
  const headers = await signIn(context, fixture);
  const [alpha, beta, gamma, delta] = fixture.agents;
  const pin = (ids, pinned) =>
    context.request.post("/api/threads/prefs", { headers, data: { thread_ids: ids, pinned } });
  // Earlier pins of this owner (other specs) are cleared first.
  const before = await (await context.request.get("/api/threads/inbox")).json();
  const pinned = before.filter((entry) => entry.pinned_order != null).map((e) => e.thread_id);
  if (pinned.length) await pin(pinned, false);
  expect(
    (await pin([fixture.threads[0].id, fixture.threads[1].id, fixture.threads[2].id], true)).ok(),
  ).toBe(true);
  await page.goto("/app");
  await expect(desktopRow(page, key(alpha))).toBeVisible();
  try {
    // Pinned rows lead, newest pin on top, each with its pin mark.
    const keys = await page
      .locator(".desktop-list .thread[data-key]")
      .evaluateAll((rows) => rows.slice(0, 3).map((row) => row.dataset.key));
    expect(keys).toEqual([key(gamma), key(beta), key(alpha)]);
    await expect(desktopRow(page, key(alpha)).getByRole("img", { name: "Pinned" })).toBeVisible();
    await desktopRow(page, key(delta)).click({ button: "right" });
    await expect(toolbar(page)).toBeVisible();
    await toolbar(page).getByRole("button", { name: "Pin", exact: true }).click();
    await expect(page.locator("#toast")).toHaveText("You can pin 3 chats only");
    // A stale view (another device pinned meanwhile) reaches the server, which refuses.
    await page.route("**/api/threads/inbox", async (route) => {
      const rows = await (await route.fetch()).json();
      await route.fulfill({ json: rows.map((row) => ({ ...row, pinned_order: null })) });
    });
    await page.reload();
    await expect(desktopRow(page, key(delta))).toBeVisible();
    const refused = page.waitForResponse(
      (response) => response.url().endsWith("/api/threads/prefs") && response.status() === 409,
    );
    await desktopRow(page, key(delta)).click({ button: "right" });
    await toolbar(page).getByRole("button", { name: "Pin", exact: true }).click();
    await refused;
    await expect(page.locator("#toast")).toHaveText("You can pin 3 chats only");
  } finally {
    // Later refetches (afterEach deletes the seeded agents) must not reach a closing page.
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await pin([fixture.threads[0].id, fixture.threads[1].id, fixture.threads[2].id], false);
  }
});

test("mute silences a chat's heads-up and badge; critical attention always shows", async ({
  page,
  context,
}) => {
  const fixture = seed({ action: "init" });
  const headers = await signIn(context, fixture);
  const [alpha, beta] = fixture.agents;
  const personal = (await (await context.request.get("/api/agents")).json()).find(
    (agent) => agent.role === "personal",
  );
  await page.goto("/app");
  await desktopRow(page, key(alpha)).click({ button: "right" });
  await toolbar(page).getByRole("button", { name: "Mute notifications" }).click();
  await expect(page.locator("#toast")).toHaveText("Notifications muted");
  await expect(desktopRow(page, key(alpha)).getByRole("img", { name: "Muted" })).toBeVisible();
  await expect(desktopRow(page, key(alpha)).locator(".count.quiet")).toBeVisible();
  // An answer in a muted chat: no banner.
  seed({
    action: "message",
    thread: fixture.threads[0].id,
    agent: alpha.id,
    content: "Muted news",
  });
  await expect(desktopRow(page, key(alpha))).toContainText("Muted news");
  await expect(page.locator("#headsup")).toHaveCount(0);
  // An answer in another chat: the banner, then «رد» opens it.
  seed({ action: "message", thread: fixture.threads[1].id, agent: beta.id, content: "Fresh news" });
  const banner = page.locator("#headsup");
  await expect(banner).toContainText(beta.name);
  await expect(banner).toContainText("Fresh news");
  await banner.getByRole("button", { name: "Reply" }).click();
  await expect(page).toHaveURL(new RegExp(`/app/${beta.id}`));
  // Muting Lonora's own chat never hides a critical attention item.
  await page.goto("/app");
  await desktopRow(page, key(personal)).click({ button: "right" });
  await toolbar(page).getByRole("button", { name: "Mute notifications" }).click();
  await expect(desktopRow(page, key(personal)).getByRole("img", { name: "Muted" })).toBeVisible();
  const controls = await (await context.request.get("/api/trading/controls")).json();
  try {
    const alert = seed({ action: "attention" });
    expect(alert.importance).toBe("critical");
    await expect(page.locator("#headsup")).toContainText(personal.name, { timeout: 15_000 });
  } finally {
    seed({
      action: "restore",
      controls: { enabled: controls.enabled, emergency_stop: controls.emergency_stop },
    });
    const inbox = await (await context.request.get("/api/threads/inbox")).json();
    await context.request.post("/api/threads/prefs", {
      headers,
      data: { thread_ids: inbox.filter((e) => e.muted).map((e) => e.thread_id), muted: false },
    });
  }
});

test("archive leaves the list with an undo; the archived page keeps its setting", async ({
  page,
  context,
}) => {
  const fixture = seed({ action: "init" });
  await signIn(context, fixture);
  const gamma = fixture.agents[2];
  await page.goto("/app");
  await desktopRow(page, key(gamma)).click({ button: "right" });
  await toolbar(page).getByRole("button", { name: "Archive", exact: true }).click();
  const toast = page.locator("#toast");
  await expect(toast).toContainText("one chat archived");
  await expect(desktopRow(page, key(gamma))).toHaveCount(0);
  await expect(page.locator(".desktop-list .archive-row")).toBeVisible();
  await toast.getByRole("button", { name: "Undo" }).click();
  await expect(desktopRow(page, key(gamma))).toBeVisible();
  // Archive again and open «المؤرشفة».
  await desktopRow(page, key(gamma)).click({ button: "right" });
  await toolbar(page).getByRole("button", { name: "Archive", exact: true }).click();
  await page.locator(".desktop-list .archive-row").click();
  await expect(page).toHaveURL(/\/app\/archived$/);
  const archived = page.locator(".desktop-content .thread[data-key]");
  await expect(archived.filter({ hasText: gamma.name })).toBeVisible();
  const keep = page.getByRole("switch", { name: "Keep chats archived" });
  const before = await keep.getAttribute("aria-checked");
  await keep.click();
  await expect(keep).not.toHaveAttribute("aria-checked", before);
  const settings = await (await context.request.get("/api/threads/settings")).json();
  expect(String(settings.keep_archived)).toBe(before === "true" ? "false" : "true");
  await keep.click();
  // Selecting an archived chat offers «إلغاء الأرشفة».
  await archived.filter({ hasText: gamma.name }).click({ button: "right" });
  await toolbar(page).getByRole("button", { name: "Unarchive" }).click();
  await expect(toast).toHaveText("Chat returned to the list");
  await expect(desktopRow(page, key(gamma))).toBeVisible();
});

test("phone selection: long-press, toolbar, select all, favourites, Back ends it, group from selected", async ({
  page,
  context,
}) => {
  const fixture = seed({ action: "init" });
  await signIn(context, fixture, "ar");
  await page.setViewportSize({ width: 390, height: 844 });
  const [alpha, beta] = fixture.agents;
  const row = (agent) => page.locator(`#view-scroll .thread[data-key="${key(agent)}"]`);
  await page.goto("/app");
  await expect(row(alpha)).toBeVisible();
  const press = (selector) =>
    page.evaluate(async (selector) => {
      const target = document.querySelector(selector);
      const box = target.getBoundingClientRect();
      const init = {
        bubbles: true,
        cancelable: true,
        pointerId: 9,
        pointerType: "touch",
        isPrimary: true,
        clientX: box.left + 40,
        clientY: box.top + 20,
      };
      target.dispatchEvent(new PointerEvent("pointerdown", init));
      await new Promise((resolve) => setTimeout(resolve, 520));
      target.dispatchEvent(new PointerEvent("pointerup", init));
      // The click that ends a long-press is swallowed for 450ms (the reference's rule).
      await new Promise((resolve) => setTimeout(resolve, 500));
    }, selector);
  await press(`#view-scroll .thread[data-key="${key(alpha)}"]`);
  const bar = toolbar(page, "المحادثات المحددة");
  await expect(bar).toBeVisible();
  await expect(bar.locator(".sel-count")).toContainText("1");
  await expect(row(alpha)).toHaveClass(/picked/);
  await row(beta).click();
  await expect(bar.locator(".sel-count")).toContainText("2");
  // Back ends the selection and stays on the list.
  await page.goBack();
  await expect(bar).toHaveCount(0);
  await expect(page).toHaveURL(/\/app$/);
  await expect(row(alpha)).not.toHaveClass(/picked/);
  // Select two again: favourites, then the المفضلة filter shows exactly them.
  await press(`#view-scroll .thread[data-key="${key(alpha)}"]`);
  await row(beta).click();
  await bar.getByRole("button", { name: "المزيد" }).click();
  await page.getByRole("menuitem", { name: "إضافة إلى المفضلة" }).click();
  await expect(page.locator("#toast")).toHaveText("أُضيفت إلى المفضلة");
  await expect(bar).toHaveCount(0);
  await page.locator("#view-scroll").evaluate((main) => main.scrollTo({ top: 0 }));
  await page.locator(".list-filters").getByRole("button", { name: "المفضلة" }).click();
  await expect(row(alpha)).toBeVisible();
  await expect(row(beta)).toBeVisible();
  await expect(row(fixture.agents[2])).toHaveCount(0);
  await page.locator(".list-filters").getByRole("button", { name: "الكل" }).click();
  // ⋮ → select all picks every row on screen; ✕ ends it.
  await press(`#view-scroll .thread[data-key="${key(alpha)}"]`);
  await bar.getByRole("button", { name: "المزيد" }).click();
  await page.getByRole("menuitem", { name: "تحديد الكل" }).click();
  const visible = await page.locator("#view-scroll .thread[data-key]").count();
  await expect(bar.locator(".sel-count")).toContainText(String(visible));
  await bar.getByRole("button", { name: "إلغاء التحديد" }).click();
  await expect(bar).toHaveCount(0);
  // The two favourites again: remove them, then «مجموعة من المحددين» prefills the group.
  await press(`#view-scroll .thread[data-key="${key(alpha)}"]`);
  await row(beta).click();
  await bar.getByRole("button", { name: "المزيد" }).click();
  await page.getByRole("menuitem", { name: "إزالة من المفضلة" }).click();
  await expect(page.locator("#toast")).toHaveText("أُزيلت من المفضلة");
  await press(`#view-scroll .thread[data-key="${key(alpha)}"]`);
  await row(beta).click();
  await bar.getByRole("button", { name: "المزيد" }).click();
  await page.getByRole("menuitem", { name: "مجموعة من المحددين" }).click();
  await expect(page).toHaveURL(/\/app\/new-group$/);
  const name = await page.locator("form input").first().inputValue();
  expect(name).toContain(alpha.name);
  expect(name).toContain(beta.name);
});

test("a custom list is created with the emoji panel, filters the rows and deletes with undo", async ({
  page,
  context,
}) => {
  const fixture = seed({ action: "init" });
  await signIn(context, fixture);
  const [alpha] = fixture.agents;
  await page.goto("/app");
  await page.locator(".desktop-list .list-filters .chip-add").click();
  const sheet = page.locator("#dialog");
  await expect(sheet.getByRole("heading", { name: "New list" })).toBeVisible();
  const name = sheet.locator("#list-name");
  await name.fill("Work");
  await sheet.getByRole("button", { name: "Add an emoji" }).click();
  const panel = sheet.locator(".emoji-panel");
  await expect(panel.locator(".emo-grid .emo").nth(20)).toBeVisible();
  const emoji = await panel.locator(".emo-sec[data-sec='1'] .emo").first().getAttribute("data-e");
  await panel.locator(".emo-sec[data-sec='1'] .emo").first().click();
  await expect(name).toHaveValue(`Work${emoji}`);
  const listName = `Work${emoji} ${Date.now() % 10000}`;
  await name.fill(listName);
  await sheet.getByRole("button", { name: "Add agents or groups" }).click();
  await sheet.getByRole("checkbox", { name: new RegExp(alpha.name) }).click();
  await sheet.getByRole("checkbox", { name: new RegExp(fixture.group.payload.name) }).click();
  await sheet.getByRole("button", { name: "Create the list · 2" }).click();
  await expect(page.locator("#toast")).toHaveText(`List «${listName}» created`);
  const chip = page.locator(".desktop-list .list-filters .list-chip", { hasText: listName });
  await expect(chip).toHaveClass(/active/);
  await expect(page.locator(".desktop-list .thread[data-key]")).toHaveCount(2);
  const lists = await (await context.request.get("/api/chat-lists")).json();
  const saved = lists.find((list) => list.name === listName);
  expect(saved.thread_ids.sort()).toEqual(
    [fixture.threads[0].id, fixture.group.state.thread_id].sort(),
  );
  // Right-click the chip (once it has scrolled into view): delete, then undo restores it.
  await expect(chip).toBeInViewport();
  await page.waitForTimeout(400);
  await chip.click({ button: "right" });
  await page.getByRole("menuitem", { name: "Delete the list" }).click();
  await expect(chip).toHaveCount(0);
  await page.locator("#toast").getByRole("button", { name: "Undo" }).click();
  await expect(
    page.locator(".desktop-list .list-filters .list-chip", { hasText: listName }),
  ).toBeVisible();
});

test("unified search: categories with counts, the latest query only, and the jump to a hit", async ({
  page,
  context,
}) => {
  const fixture = seed({ action: "init" });
  await signIn(context, fixture);
  const beta = fixture.agents[1];
  await page.goto("/app");
  // A slow first query never replaces the newer one.
  let slow = true;
  await page.route("**/api/search?*", async (route) => {
    if (slow && new URL(route.request().url()).searchParams.get("q") === "First") {
      slow = false;
      await new Promise((resolve) => setTimeout(resolve, 1200));
    }
    await route.continue();
  });
  const field = page.locator("#desktop-search");
  await field.fill("First");
  await field.fill("Second update");
  const results = page.locator("#search-results");
  await expect(results.locator("[data-search-section='messages']")).toContainText("Second update");
  await page.waitForTimeout(1500);
  await expect(results).not.toContainText("First update");
  await expect(results.locator("[data-search-section='messages'] mark").first()).toHaveText(
    /Second update/i,
  );
  // A category tab with its count.
  await page.getByRole("tab", { name: "Messages" }).click();
  await expect(page.getByRole("tab", { name: "Messages" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  const hit = results.locator("[data-search-hit='messages']").first();
  await expect(hit).toContainText(beta.name);
  await hit.click();
  await expect(page).toHaveURL(new RegExp(`/app/${beta.id}\\?thread=.*&around=\\d+`));
  await expect(page.getByTestId("transcript").getByText("Second update")).toBeInViewport();
  // Chats category: an agent by name.
  await field.fill(fixture.agents[0].name.split(" ")[0]);
  await page.getByRole("tab", { name: "Chats" }).click();
  await expect(results.locator("[data-search-section='chats']")).toContainText(
    fixture.agents[0].name,
  );
  await field.fill("");
  await expect(page.locator(".desktop-list .thread[data-key]").first()).toBeVisible();
});

test("phone search browses recent content when the query is empty", async ({ page, context }) => {
  const fixture = seed({ action: "init" });
  await signIn(context, fixture, "ar");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/app");
  await page.locator("#search").click();
  await expect(page.locator("#app")).toHaveClass(/search-mode/);
  await expect(page.locator("#search-results")).toContainText("الرسائل الأخيرة");
  await expect(page.locator(".search-tip")).toBeVisible();
  await page.getByRole("tab", { name: "الرسائل" }).click();
  await expect(page.locator("#search-results .search-count")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator("#app")).not.toHaveClass(/search-mode/);
});

test("«حذف» and «مسح» hide the history for the owner; agents and groups are never deleted", async ({
  page,
  context,
}) => {
  const fixture = seed({ action: "init" });
  await signIn(context, fixture);
  const beta = fixture.agents[1];
  const deletes = [];
  page.on("request", (request) => {
    if (request.method() === "DELETE") deletes.push(request.url());
  });
  await page.goto("/app");
  await desktopRow(page, key(beta)).click({ button: "right" });
  await toolbar(page).getByRole("button", { name: "Delete", exact: true }).click();
  const sheet = page.locator("#dialog");
  await expect(sheet).toContainText("hidden for you");
  await expect(sheet).toContainText("The agents stay");
  await expect(sheet).not.toContainText("this device");
  await sheet.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page.locator("#toast")).toHaveText("one chat deleted");
  await expect(desktopRow(page, key(beta))).toBeVisible();
  await expect(desktopRow(page, key(beta))).not.toContainText("Second update");
  const messages = await (
    await context.request.get(`/api/threads/${fixture.threads[1].id}/messages`)
  ).json();
  expect(messages).toEqual([]);
  const agents = await (await context.request.get("/api/agents")).json();
  expect(agents.some((agent) => agent.id === beta.id)).toBe(true);
  // A group: «مسح الرسائل» from ⋮; the group and its members stay.
  const groupThread = fixture.group.state.thread_id;
  seed({
    action: "message",
    thread: groupThread,
    agent: fixture.agents[0].id,
    content: "Group note",
  });
  await expect(desktopRow(page, `group:${fixture.group.id}`)).toContainText("Group note");
  await desktopRow(page, `group:${fixture.group.id}`).click({ button: "right" });
  await toolbar(page).getByRole("button", { name: "More" }).click();
  await page.getByRole("menuitem", { name: "Clear the messages" }).click();
  await expect(sheet).toContainText("the chats stay in the list");
  await sheet.getByRole("button", { name: "Clear", exact: true }).click();
  await expect(page.locator("#toast")).toHaveText("Messages cleared");
  const groups = await (await context.request.get("/api/groups")).json();
  const group = groups.find((row) => row.id === fixture.group.id);
  expect(group.payload.member_ids).toEqual(fixture.group.payload.member_ids);
  expect(await (await context.request.get(`/api/threads/${groupThread}/messages`)).json()).toEqual(
    [],
  );
  expect(deletes).toEqual([]);
});

test("a cleared conversation leaves the open chat and stays hidden when it is reopened", async ({
  page,
  context,
}) => {
  const fixture = seed({ action: "init" });
  await signIn(context, fixture);
  const [alpha, beta] = fixture.agents;
  await page.goto(`/app/${beta.id}?thread=${fixture.threads[1].id}`);
  const cleared = page.locator("article", { hasText: "Second update" });
  await expect(cleared.first()).toBeVisible();
  await desktopRow(page, key(beta)).click({ button: "right" });
  await toolbar(page).getByRole("button", { name: "Delete", exact: true }).click();
  await page.locator("#dialog").getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page.locator("#toast")).toHaveText("one chat deleted");
  // Q1 in the same session: the open conversation hides what the server hides, no reload.
  await expect(cleared).toHaveCount(0);
  await desktopRow(page, key(alpha)).click();
  await expect(page).toHaveURL(new RegExp(`/app/${alpha.id}`));
  await expect(page.getByTestId("transcript").getByText("Yes, it opened.")).toBeVisible();
  // Reopened from this session's conversation cache.
  await desktopRow(page, key(beta)).click();
  await expect(page).toHaveURL(new RegExp(`/app/${beta.id}`));
  await expect(page.getByTestId("transcript")).toBeVisible();
  await expect(cleared).toHaveCount(0);
});

test("offline: a plain message waits and goes out by itself; an answer stays failed for a manual retry", async ({
  page,
  context,
}) => {
  const fixture = seed({ action: "init" });
  await signIn(context, fixture);
  const gamma = fixture.agents[2];
  const thread = fixture.threads[2];
  let offline = true;
  const sent = [];
  await page.route(`**/api/threads/${thread.id}/messages`, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    if (offline) return route.abort("internetdisconnected");
    sent.push(route.request().postDataJSON());
    return route.continue();
  });
  await page.goto(`/app/${gamma.id}?thread=${thread.id}`);
  const composer = page.getByRole("combobox", { name: "Message", exact: true });
  await composer.fill("Written offline");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  const waiting = page.locator("article[data-delivery='queued']");
  await expect(waiting).toContainText("Written offline");
  await expect(waiting.getByRole("status", { name: "Waiting for the network…" })).toBeVisible();
  // The list row shows the clock too.
  await expect(desktopRow(page, key(gamma)).locator(".pv .wait")).toBeVisible();
  offline = false;
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect(page.locator("#toast")).toHaveText("One waiting message was sent");
  await expect(page.locator("article[data-delivery]")).toHaveCount(0);
  expect(sent).toHaveLength(1);
  expect(sent[0].content).toBe("Written offline");
  expect(sent[0].input_answer).toBeUndefined();
});

test("offline: an owner's answer is never sent later by itself", async ({ page, context }) => {
  const fixture = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_question_browser.py"], {
      input: JSON.stringify({ locale: "en" }),
      encoding: "utf8",
    }),
  );
  const headers = await signIn(context, fixture);
  const nonces = [];
  let offline = true;
  await page.route(`**/api/threads/${fixture.thread.id}/messages`, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    nonces.push(route.request().postDataJSON().client_nonce);
    if (offline) return route.abort("internetdisconnected");
    return route.continue();
  });
  try {
    await page.goto(`/app/${fixture.agent.id}?thread=${fixture.thread.id}`);
    const card = page.locator(`[data-question-id="${fixture.question.id}"]`);
    await card.getByRole("button", { name: fixture.question.choices[0].label }).click();
    const failed = page.locator("article[data-delivery='failed']");
    await expect(failed).toBeVisible();
    offline = false;
    await page.evaluate(() => window.dispatchEvent(new Event("online")));
    await page.waitForTimeout(800);
    // Nothing went out by itself: still failed, one attempt.
    await expect(failed).toBeVisible();
    expect(nonces).toHaveLength(1);
    await failed.getByRole("button", { name: "Retry" }).click();
    await expect(page.locator("article[data-delivery]")).toHaveCount(0);
    expect(nonces).toHaveLength(2);
    expect(nonces[1]).toBe(nonces[0]);
  } finally {
    await context.request.delete(`/api/agents/${fixture.agent.id}`, { headers });
  }
});
