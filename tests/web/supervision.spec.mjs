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

// Lonora (supervising every agent by default), a gold agent and a watcher that
// proposed to supervise it, as supervision_change raises the card without an owner
// message (no model involved); Lonora paused one of Gold's routines on its own, which
// raises the pause card in Gold's conversation.
function seedSupervision(data) {
  const script = `
import asyncio,json,sys
sys.path.insert(0,'tests')
from uuid import uuid4
from check_streaming import Fixture
from lonora_contracts.domain import AgentCreate
from lonora_db.agents import create_agent
from lonora_db.owner_actions import propose_supervision
from lonora_db.personal_agent import ensure_personal_agent
from lonora_contracts.routines import RoutineCreate
from lonora_db.routines import create_routine
from lonora_db.schema import OwnerActionRow
from lonora_db.supervision import control_work
from sqlalchemy import select
from lonora_db.threads import conversation_thread
async def main():
    data=json.load(sys.stdin)
    f=await Fixture().open()
    try:
        async with f.runtime.db.sessions() as session, session.begin():
            lonora=await ensure_personal_agent(session,f.owner)
            gold=await create_agent(session,f.owner,AgentCreate(name=data['gold'],scope_mode='flexible'))
            watcher=await create_agent(session,f.owner,AgentCreate(name=data['watcher'],scope_mode='flexible'))
            thread=await conversation_thread(session,f.owner,watcher.id)
            card,_=await propose_supervision(session,f.owner,watcher.id,[gold.id],card_id=str(uuid4()),agent_id=watcher.id,thread_id=thread.id,run_id=None)
            routine=await create_routine(session,f.owner,gold.id,RoutineCreate(prompt=data['routine'],interval_seconds=3600))
            await control_work(session,f.owner,actor_id=lonora.id,agent_id=gold.id,kind='routine',target_id=routine.id,action='pause',owner_message_id=None,run_id=None)
            pause=await session.scalar(select(OwnerActionRow.id).where(OwnerActionRow.kind=='supervision_paused',OwnerActionRow.agent_id==gold.id))
            gold_thread=await conversation_thread(session,f.owner,gold.id)
            print(json.dumps({'lonora':lonora.id,'lonora_name':lonora.name,'gold':gold.id,'watcher':watcher.id,'card':card.id,'pause':pause}))
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
  en: {
    settings: "Agent info",
    section: "Lonora supervises your agents",
    byDefault: "by default",
    byYou: "set by you",
    stop: "Stop",
    supervise: "Supervise",
    notSupervised: "Not supervised by Lonora",
    title: "Let it supervise?",
    allow: "Allow",
    set: "Supervision set.",
    created: "Supervision set",
    undo: "Undo",
    undone: "Undone: supervision stopped.",
    never: /never trades for them/,
    pauseTitle: "Paused by a supervisor",
    resume: "Resume",
    resumed: "Resumed.",
  },
  ar: {
    settings: "معلومات الوكيل",
    section: "لونورا تشرف على وكلائك",
    byDefault: "افتراضيًا",
    byYou: "عيّنته أنت",
    stop: "إيقاف",
    supervise: "إشراف",
    notSupervised: "لا تشرف عليهم لونورا",
    title: "السماح له بالإشراف؟",
    allow: "السماح",
    set: "تم تعيين الإشراف.",
    created: "تم تعيين الإشراف",
    undo: "تراجع",
    undone: "تم التراجع: توقف الإشراف.",
    never: /لا يتداول عنهم/,
    pauseTitle: "أوقفه مشرف مؤقتًا",
    resume: "استئناف",
    resumed: "تم الاستئناف.",
  },
};

for (const locale of ["en", "ar"])
  test(`${locale}: Lonora's profile stops and restores supervision, and a card sets it with Undo`, async ({
    page,
    context,
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
    const suffix = randomUUID().slice(0, 6);
    const seeded = seedSupervision({
      gold: `Gold ${suffix}`,
      watcher: `Watcher ${suffix}`,
      routine: `Review gold ${suffix}`,
    });
    try {
      // Lonora's profile: every agent is supervised by default, each with one-tap Stop.
      await page.goto(`/app/${seeded.lonora}`);
      await page.getByRole("button", { name: text.settings, exact: true }).click();
      const section = page.getByTestId("supervision-settings");
      await section.locator("summary").click();
      await expect(section.locator("summary")).toHaveText(text.section);
      const row = section.locator("li").filter({ hasText: `Gold ${suffix}` });
      await expect(row).toContainText(text.byDefault);
      if (locale === "ar") {
        await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
        await section.screenshot({ path: test.info().outputPath("supervision-profile-ar.png") });
      }
      await row.getByRole("button", { name: text.stop, exact: true }).click();
      const offered = section
        .locator(".supervision-list")
        .filter({ hasText: text.notSupervised })
        .locator("li")
        .filter({ hasText: `Gold ${suffix}` });
      await expect(offered).toBeVisible();
      const view = await (
        await context.request.get(`/api/supervision?agent_id=${seeded.gold}`)
      ).json();
      expect(view.supervised_by.some((grant) => grant.supervisor.id === seeded.lonora)).toBe(false);
      await offered.getByRole("button", { name: text.supervise, exact: true }).click();
      await expect(
        section
          .locator("li")
          .filter({ hasText: `Gold ${suffix}` })
          .first(),
      ).toContainText(text.byYou);

      // The watcher's card: Allow sets supervision; its Undo card stops it again.
      await page.goto(`/app/${seeded.watcher}`);
      const card = page.locator(`[data-owner-action="${seeded.card}"]`);
      await expect(card).toHaveAttribute("data-owner-action-kind", "supervise");
      await expect(card.locator("strong")).toHaveText(text.title);
      await expect(card).toContainText(`⁨Gold ${suffix}⁩`);
      await expect(card).toContainText(text.never);
      await card.getByRole("button", { name: text.allow, exact: true }).click();
      await expect(card).toHaveAttribute("data-owner-action-status", "confirmed");
      await expect(card.getByRole("status")).toHaveText(text.set);
      const undo = page.locator('[data-owner-action-kind="supervision_created"]');
      await expect(undo.locator("strong")).toHaveText(text.created);
      await undo.getByRole("button", { name: text.undo, exact: true }).click();
      await expect(undo).toHaveAttribute("data-owner-action-status", "confirmed");
      await expect(undo.getByRole("status")).toHaveText(text.undone);
      const after = await (
        await context.request.get(`/api/supervision?agent_id=${seeded.watcher}`)
      ).json();
      expect(after.supervises).toEqual([]);

      // Gold's conversation names who paused its routine, with one-tap Resume.
      await page.goto(`/app/${seeded.gold}`);
      const pause = page.locator(`[data-owner-action="${seeded.pause}"]`);
      await expect(pause).toHaveAttribute("data-owner-action-kind", "supervision_paused");
      await expect(pause.locator("strong")).toHaveText(text.pauseTitle);
      await expect(pause).toContainText(`⁨${seeded.lonora_name}⁩`);
      await expect(pause).toContainText(`⁨Review gold ${suffix}⁩`);
      if (locale === "ar")
        await pause.screenshot({ path: test.info().outputPath("supervision-pause-ar.png") });
      await pause.getByRole("button", { name: text.resume, exact: true }).click();
      await expect(pause).toHaveAttribute("data-owner-action-status", "confirmed");
      await expect(pause.getByRole("status")).toHaveText(text.resumed);
      const routines = await (await context.request.get(`/api/routines`)).json();
      expect(
        routines.filter((row) => row.agent_id === seeded.gold).map((row) => row.enabled),
      ).toEqual([true]);
    } finally {
      for (const id of [seeded.gold, seeded.watcher])
        await context.request.delete(`/api/agents/${id}`, { headers });
      simulation({ ...data, action: "cleanup" });
    }
  });
