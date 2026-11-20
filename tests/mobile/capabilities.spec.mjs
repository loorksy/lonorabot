import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "../ui-test.mjs";

function simulation(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

// A news agent whose card asks the owner to add a news feed (a Secret card for its
// address), as the tool raises it (no model involved), and another feed's site it trusted
// on the owner's own words (no card: VISION 10.3.2).
function seedCards(data) {
  const script = `
import asyncio,json,sys
sys.path.insert(0,'tests')
from uuid import uuid4
from check_streaming import Fixture
from lonora_contracts.domain import AgentCreate
from lonora_db.agents import create_agent
from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_db.owner_actions import propose
from lonora_db.schema import SkillRow
from lonora_db.threads import conversation_thread
from lonora_db.trusted_sources import trust_source
async def main():
    data=json.load(sys.stdin)
    f=await Fixture().open()
    try:
        async with f.runtime.db.sessions() as session, session.begin():
            agent=await create_agent(session,f.owner,AgentCreate(name=data['agent'],scope_mode='flexible'))
            thread=await conversation_thread(session,f.owner,agent.id)
            credential,_=await propose(session,f.owner,OwnerActionProposal(kind='secret',target='news_feed',name=data['feed']),card_id=str(uuid4()),agent_id=agent.id,thread_id=thread.id,run_id=None)
            await trust_source(session,f.owner,'feed_domain',data['domain'],via='owner_message',agent_id=agent.id)
            skill=data['skill']
            session.add(SkillRow(id=str(uuid4()),owner_id=f.owner,agent_id=agent.id,version=1,payload={'name':skill,'content':'---\\nname: '+skill+'\\ndescription: Short sourced notes.\\n---\\nUse cited evidence only.\\n','enabled':True,'manifest':{'id':skill,'version':'1.0.0','title':skill,'description':'Short sourced notes.','source':'installed','activation':{'mode':'explicit'}}}))
            print(json.dumps({'agent':agent.id,'thread':thread.id,'credential':credential.id}))
    finally:
        await f.close(cleanup=False)
asyncio.run(main())
`;
  return JSON.parse(
    execFileSync(".venv/bin/python", ["-c", script], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

const copy = {
  ar: {
    connectTitle: "إضافة موجز أخبار",
    url: "عنوان الموجز",
    connect: "ربط",
    connected: "تم الربط. لا يرى أي وكيل ما كتبته.",
    title: "التكاملات",
    remove: "إزالة",
    undo: "تراجع",
    undone: "تم التراجع",
    setUp: "إعداد التكاملات على الويب",
  },
  en: {
    connectTitle: "Add a news feed",
    url: "Feed URL",
    connect: "Connect",
    connected: "Connected. No agent sees what you typed.",
    title: "Integrations",
    remove: "Remove",
    undo: "Undo",
    undone: "undone",
    setUp: "Set up integrations on the web",
  },
};

for (const locale of ["ar", "en"])
  test(`Expo ${locale}: a feed form in the chat and a site trusted from chat, then Integrations`, async ({
    page,
    context,
    cleanup,
  }) => {
    test.setTimeout(90000);
    const text = copy[locale];
    const data = simulation({ action: "init", empty: true });
    await context.addCookies(
      data.cookies.map((cookie) => ({
        ...cookie,
        url: test.info().project.use.baseURL,
        httpOnly: cookie.name === "lonora_session",
        sameSite: "Strict",
      })),
    );
    await context.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
    const headers = {
      "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value,
    };
    const suffix = randomUUID().slice(0, 8);
    const site = `site-${suffix}.analyst.example`;
    const feed = `https://desk-${suffix}.news.example/rss`;
    const skill = `notes-${suffix}`;
    const seeded = seedCards({
      agent: `News ${suffix}`,
      domain: site,
      skill,
      feed: `Desk ${suffix}`,
    });
    cleanup(async () => {
      await context.request.delete(`/api/agents/${seeded.agent}`, { headers });
      simulation({ ...data, action: "cleanup" });
    });

    await page.goto(`/thread?id=${seeded.thread}`);
    const card = page.getByTestId(`owner-action-${seeded.credential}`);
    await expect(card.getByText(text.connectTitle, { exact: true })).toBeVisible();
    // The feed's name came from chat; the owner types only its address.
    await expect(card).toContainText(`⁨Desk ${suffix}⁩`);
    await card.getByLabel(text.url, { exact: true }).fill(feed);
    if (locale === "ar")
      await card.screenshot({ path: test.info().outputPath("credential-native-ar.png") });
    await card.getByRole("button", { name: text.connect, exact: true }).click();
    await expect(card.getByText(text.connected, { exact: true })).toBeVisible();

    // Trusting the site raised no card: the credential card is the conversation's only one.
    const cards = await (
      await context.request.get(`/api/owner-actions?thread_id=${seeded.thread}`)
    ).json();
    expect(cards.map((item) => item.kind)).toEqual(["secret"]);

    await page.goto("/integrations");
    await expect(page.getByText(text.title, { exact: true }).first()).toBeVisible();
    const report = await (await context.request.get("/api/capabilities")).json();
    const added = report.integrations.find((item) => item.name === `Desk ${suffix}`);
    expect(added.type).toBe("news_feed");
    expect(added.domain).toBe(`desk-${suffix}.news.example`);
    const trusted = report.trusted_sources.find((item) => item.identifier === site);
    expect(trusted.added_via).toBe("owner_message");
    const row = page.getByTestId(`integration-${added.id}`);
    await expect(row).toContainText(`⁨Desk ${suffix}⁩`);
    if (locale === "ar")
      await page.screenshot({ path: test.info().outputPath("capabilities-native-ar.png") });
    await row.getByRole("button", { name: text.remove, exact: true }).click();
    await expect(row).toHaveCount(0);
    // The last feed of its site is gone: the site leaves the trusted list too.
    const after = await (await context.request.get("/api/capabilities")).json();
    expect(
      after.trusted_sources.some(
        (item) => item.identifier === `desk-${suffix}.news.example` && item.active,
      ),
    ).toBe(false);
    const written = after.skills.find((item) => item.skill_id === skill);
    const line = page.getByTestId(`capability-skill-${written.resource_id}`);
    await line.getByRole("button", { name: text.undo, exact: true }).click();
    await expect(line).toContainText(text.undone);
    await expect(line.getByRole("button", { name: text.undo, exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: text.setUp, exact: true })).toBeVisible();
  });

const review = {
  en: {
    review: "Review and trust",
    writes: "may change something (only with non-financial writes)",
    trust: "Trust",
    trustWrite: "Trust: non-financial writes",
    read: "read only",
    remove: "Remove",
  },
  ar: {
    review: "مراجعة ووثوق",
    writes: "قد تغيّر شيئًا (مع الكتابة غير المالية فقط)",
    trust: "ثقة",
    trustWrite: "ثقة: كتابة غير مالية",
    read: "قراءة فقط",
    remove: "إزالة",
  },
};

for (const locale of ["ar", "en"])
  test(`Expo ${locale}: a server whose tools are not trusted yet is reviewed and trusted here`, async ({
    page,
    context,
    cleanup,
  }) => {
    const text = review[locale];
    const data = simulation({ action: "init", empty: true });
    await context.addCookies(
      data.cookies.map((cookie) => ({
        ...cookie,
        url: test.info().project.use.baseURL,
        httpOnly: cookie.name === "lonora_session",
        sameSite: "Strict",
      })),
    );
    await context.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
    // The saved server and its tools are scripted; the routes and their bodies are real.
    const server = {
      connection_id: "scripted-server",
      // A name in the other script: its line still reads in the interface's direction.
      name: locale === "ar" ? "X posts" : "منشورات X",
      enabled: true,
      credentials_configured: true,
      trusted_tier: null,
      trusted_tools: [],
      tool_titles: {},
      tool_titles_kept: true,
      write_tools: [],
      blocked_tools: [],
      operator_declared: 0,
      trust_source_id: null,
      last_used_at: null,
    };
    await page.route("**/api/capabilities", async (route) => {
      const response = await route.fetch();
      const report = await response.json();
      await route.fulfill({ response, json: { ...report, mcp_servers: [server] } });
    });
    await page.route("**/api/trusted-sources/mcp/scripted-server/preview", (route) =>
      route.fulfill({
        json: {
          name: "X posts",
          tools: ["post_note", "search_posts"],
          writes: ["post_note"],
          blocked: ["send_usdc"],
          titles: { post_note: "حفظ ملاحظة", search_posts: "Search posts" },
          unsupported: 0,
          digest: "a".repeat(64),
          trusted_tier: null,
        },
      }),
    );
    const trusted = [];
    await page.route("**/api/trusted-sources/mcp/scripted-server", (route) => {
      const body = JSON.parse(route.request().postData() ?? "{}");
      trusted.push(body);
      // As the trust route leaves it: the passing tools pinned at the tier asked for.
      Object.assign(server, {
        trusted_tier: body.tier,
        trusted_tools: ["post_note", "search_posts"],
        write_tools: ["post_note"],
        blocked_tools: ["send_usdc"],
        trust_source_id: "scripted-trust",
      });
      return route.fulfill({ json: {} });
    });
    cleanup(async () => {
      // The list reloads after trusting; a handler still reading it when the page closes is not
      // a failure of this test.
      await page.unrouteAll({ behavior: "ignoreErrors" });
      simulation({ ...data, action: "cleanup" });
    });

    await page.goto("/integrations");
    const line = page.getByTestId("mcp-server-scripted-server");
    const words = line.locator(":scope > div").first();
    await expect(words).toContainText(server.name);
    expect(await words.evaluate((node) => getComputedStyle(node).direction)).toBe(
      locale === "ar" ? "rtl" : "ltr",
    );
    await line.getByRole("button", { name: text.review, exact: true }).click();
    const preview = page.getByTestId("mcp-preview");
    // Each tool by the server's own title; a tool it gave no title keeps its name.
    await expect(preview).toContainText("⁨Search posts⁩");
    await expect(preview).toContainText(`${text.writes}: ⁨حفظ ملاحظة⁩`);
    await expect(preview).not.toContainText("search_posts");
    await expect(preview).not.toContainText("post_note");
    await expect(preview).toContainText("⁨send_usdc⁩");
    // A server that offers a blocked money tool is trusted to read only: no write tier.
    await expect(preview.getByRole("button", { name: text.trustWrite, exact: true })).toHaveCount(
      0,
    );
    if (locale === "ar")
      await page.screenshot({ path: test.info().outputPath("mcp-review-native-ar.png") });
    await preview.getByRole("button", { name: text.trust, exact: true }).click();
    await expect(preview).toHaveCount(0);
    expect(trusted).toEqual([{ tier: "read", digest: "a".repeat(64) }]);
    // The screen reads the report again: the server is now trusted to read only.
    await expect(line).toContainText(text.read);
    await expect(line.getByRole("button", { name: text.remove, exact: true })).toBeVisible();
    await expect(line.getByRole("button", { name: text.review, exact: true })).toHaveCount(0);
  });
