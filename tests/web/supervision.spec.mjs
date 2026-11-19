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

// Lonora and a gold agent; one of Gold's routines is paused, held by a team supervisor
// from before grants were deleted, whose pause card still shows in Gold's conversation.
function seedSupervision(data) {
  const script = `
import asyncio,json,sys
sys.path.insert(0,'tests')
from check_streaming import Fixture
from lonora_contracts.domain import AgentCreate
from lonora_db.agents import create_agent
from lonora_db.personal_agent import ensure_personal_agent
from lonora_contracts.routines import RoutineCreate
from lonora_db.routines import create_routine
from lonora_db.schema import OwnerActionRow, SupervisionHoldRow
from pause_cards import raise_supervision_pause_card
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
            routine=await create_routine(session,f.owner,gold.id,RoutineCreate(prompt=data['routine'],interval_seconds=3600))
            await control_work(session,f.owner,actor_id=lonora.id,agent_id=gold.id,kind='routine',target_id=routine.id,action='pause',owner_message_id=None,run_id=None)
            # Lonora's pause raises no card: the card is a pause a team supervisor made
            # before grants were deleted (0127), which still renders with Resume.
            desk=await create_agent(session,f.owner,AgentCreate(name=data['gold']+' desk'))
            hold=await session.scalar(select(SupervisionHoldRow).where(SupervisionHoldRow.target_id==routine.id,SupervisionHoldRow.released_at.is_(None)))
            hold.holder_agent_id=desk.id
            await session.flush()
            await raise_supervision_pause_card(session,hold,run_id=None)
            pause=await session.scalar(select(OwnerActionRow.id).where(OwnerActionRow.kind=='supervision_paused',OwnerActionRow.agent_id==gold.id))
            await conversation_thread(session,f.owner,gold.id)
            print(json.dumps({'lonora_name':desk.name,'desk':desk.id,'gold':gold.id,'pause':pause}))
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
  en: { pauseTitle: "Paused by a supervisor", resume: "Resume", resumed: "Resumed." },
  ar: { pauseTitle: "أوقفه مشرف مؤقتًا", resume: "استئناف", resumed: "تم الاستئناف." },
};

for (const locale of ["en", "ar"])
  test(`${locale}: an earlier supervisor's pause card names who paused what, with one-tap Resume`, async ({
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
      routine: `Review gold ${suffix}`,
    });
    try {
      // Gold's conversation names who paused its routine, with one-tap Resume.
      await page.goto(`/app/${seeded.gold}`);
      const pause = page.locator(`[data-owner-action="${seeded.pause}"]`);
      await expect(pause).toHaveAttribute("data-owner-action-kind", "supervision_paused");
      await expect(pause.locator(".oa-kind")).toHaveText(text.pauseTitle);
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
      await context.request.delete(`/api/agents/${seeded.gold}`, { headers });
      await context.request.delete(`/api/agents/${seeded.desk}`, { headers });
      simulation({ ...data, action: "cleanup" });
    }
  });
