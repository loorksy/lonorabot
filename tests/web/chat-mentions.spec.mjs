import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

/* «@الكل» in a group (reference mentionOptions, Desktop-37 5085-5094): the last row of the
   members' list says who it alerts, and sending it addresses every member by id. */
function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/agent_pages_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}
let data = null;
const errors = [];
test.beforeEach(async ({ page, context }) => {
  data = fixture({ action: "init" });
  data.groups = [];
  data.agents = [];
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  page.on("pageerror", (error) => errors.push(error.message));
});
test.afterEach(() => {
  expect(errors.splice(0)).toEqual([]);
  if (data) fixture({ ...data, action: "cleanup" });
  data = null;
});

test("a group's @ list ends with @all, which addresses every member", async ({ page }) => {
  const members = data.group.payload.member_ids;
  await page.goto(`/app/g/${data.group.id}`);
  const field = page.getByRole("combobox");
  await field.fill("Hi @");
  const rows = page.getByRole("listbox", { name: "Mention an agent" }).getByRole("option");
  await expect(rows).toHaveCount(members.length + 1);
  const all = rows.last();
  await expect(all.locator("strong")).toHaveText("@all");
  expect(members.length).toBeGreaterThan(1);
  await expect(all.locator("small")).toHaveText(`Alerts ${members.length} agents`);
  // Any of its names finds it, and a picked @all is a chip like a member's name.
  await field.fill("Hi @every");
  await expect(rows.locator("strong")).toHaveText(["@all"]);
  await page.keyboard.press("Enter");
  await expect(page.locator(".ta-mirror mark")).toHaveText("@all");
  const sent = page.waitForRequest(
    (request) =>
      request.method() === "POST" && /\/api\/threads\/[^/]+\/messages$/.test(request.url()),
  );
  await page.keyboard.press("Enter");
  const body = (await sent).postDataJSON();
  expect([...body.mention_agent_ids].sort()).toEqual([...members].sort());
  expect(body.mention_all).toBeFalsy();

  // A direct chat with no open session has no @all.
  await page.goto(`/app/${data.research.id}`);
  await field.fill("Hi @al");
  await expect(page.getByRole("option", { name: /@all/ })).toHaveCount(0);
});
