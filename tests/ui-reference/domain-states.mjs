// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: a standalone script run by hand.
/* UI phase 4b, the domain pages: the states side-by-side.mjs captures for «المستجدات»,
   «المهام» and «تفاصيل المهمة», «الأهداف», «المهام المجدولة», «المعرفة», «المهارات» with
   «سجل الإصدارات», «الملفات» and «سجل الإجراءات», plus their forms.

   The app side is seeded by seed_domain.py through the owner API with the reference's own rows
   (`initial`). Where an owner decision changes the data the reference shows, the reference is
   moved to the same data through its own state, never its markup: Gold trades, so its goals are
   trading plans (Q41) and the light goal sits on «مساعد الأبحاث» on both sides; «سجل الإجراءات»
   is the server's projection (Q45), so the reference's log gets the same lines. */
import { execFileSync } from "node:child_process";
import { join } from "node:path";

export function domainStates({ ROOT, env, seed, refRun, visible, pause }) {
  /* Seeded once, lazily, before the first domain state's app side: these states run last, so
     the earlier phases' states see the database exactly as seed_reference.py left it. */
  let extra = null;
  const ensure = () => {
    extra ??= JSON.parse(
      execFileSync(
        join(ROOT, ".venv/bin/python"),
        [join(ROOT, "tests/ui-reference/seed_domain.py")],
        {
          cwd: ROOT,
          env,
          input: JSON.stringify({ agents: seed.agents, threads: seed.threads }),
          encoding: "utf8",
        },
      ),
    );
    return extra;
  };
  const agent = (name) => seed.agents[name];
  const to = (route, args) => (page) => refRun(page, ([r, a]) => go(r, a), [route, args]);
  const goalOnResearch = (page) =>
    refRun(page, () => {
      S.goals = S.goals.map((g) => ({ ...g, agent: "research" }));
      save();
    });
  const states = [
    {
      name: "updates",
      ref: async (page) => {
        await refRun(page, () => {
          S.activities = [
            { title: "أُنشئت مهارة", text: "موجز الأخبار · Lonora", time: "" },
            { title: "أُنشئت مهمة", text: "متابعة الذهب · محلل الذهب", time: "" },
          ];
          save();
          go("updates");
        });
      },
      appPath: "/app/updates",
      app: async () => {},
    },
    {
      name: "tasks-active",
      ref: to("tasks", { filter: "active" }),
      appPath: "/app/tasks",
      app: async () => {},
    },
    {
      name: "tasks-scheduled",
      ref: to("tasks", { filter: "scheduled" }),
      appPath: "/app/tasks",
      app: (page) => visible(page, '.tabs [role="tab"]:nth-child(2)').click(),
    },
    {
      name: "task-page",
      ref: to("task", { item: "t1", agent: "gold" }),
      appPath: () => `/app/tasks/${ensure().task}`,
      app: async () => {},
    },
    { name: "new-task", ref: to("new-task", {}), appPath: "/app/new-task", app: async () => {} },
    {
      name: "goals",
      ref: async (page) => {
        await goalOnResearch(page);
        await to("goals", { agent: "research" })(page);
      },
      appPath: () => `/app/goals?agent=${agent("research")}`,
      app: async () => {},
    },
    {
      name: "new-goal",
      ref: to("new-goal", { item: null, agent: "research" }),
      appPath: () => `/app/new-goal?agent=${agent("research")}`,
      app: async () => {},
    },
    {
      name: "schedules",
      ref: to("schedules", { agent: "lonora" }),
      appPath: () => `/app/routines?agent=${agent("lonora")}`,
      app: async () => {},
    },
    {
      name: "schedule-details",
      ref: async (page) => {
        await to("schedules", { agent: "lonora" })(page);
        await pause(page, 300);
        await visible(page, "#app main .row .body").click();
      },
      appPath: () => `/app/routines?agent=${agent("lonora")}`,
      app: (page) => visible(page, "#app main .row .body").click(),
    },
    {
      name: "new-schedule",
      ref: to("new-schedule", { agent: "lonora" }),
      appPath: () => `/app/new-schedule?agent=${agent("lonora")}`,
      app: async () => {},
    },
    {
      name: "knowledge",
      ref: to("knowledge", { agent: "lonora" }),
      appPath: () => `/app/knowledge?agent=${agent("lonora")}`,
      app: async () => {},
    },
    {
      name: "knowledge-edit",
      ref: to("knowledge-edit", { item: null, agent: "lonora" }),
      appPath: () => `/app/knowledge-edit?agent=${agent("lonora")}`,
      app: async () => {},
    },
    {
      name: "skills",
      ref: to("skills", { agent: "lonora" }),
      appPath: () => `/app/skills?agent=${agent("lonora")}`,
      app: async () => {},
    },
    {
      name: "skill-page",
      ref: to("skill", { item: "k1", agent: "lonora" }),
      appPath: () => `/app/skills/${ensure().skill}`,
      app: async () => {},
    },
    {
      name: "skill-history",
      ref: async (page) => {
        await to("skill", { item: "k1", agent: "lonora" })(page);
        await pause(page, 300);
        await refRun(page, () => handle("skill-history"));
      },
      appPath: () => `/app/skills/${ensure().skill}`,
      app: async (page) => {
        await pause(page, 300);
        await visible(page, "#app main form .btn.full").click();
      },
      wait: 1100,
    },
    {
      name: "files",
      ref: to("files", { agent: "lonora" }),
      appPath: () => `/app/artifacts?agent=${agent("lonora")}`,
      app: async () => {},
    },
    {
      name: "file-open",
      ref: async (page) => {
        await to("files", { agent: "lonora" })(page);
        await pause(page, 300);
        await visible(page, "#app main .group .row").click();
      },
      appPath: () => `/app/artifacts?agent=${agent("lonora")}`,
      app: (page) => visible(page, "#app main .group .row").click(),
      wait: 1100,
    },
    {
      name: "file-edit",
      ref: to("file-edit", { item: null, agent: "lonora" }),
      appPath: () => `/app/file-edit?agent=${agent("lonora")}`,
      app: async () => {},
    },
  ];
  return states.map((state) => ({
    ...state,
    domain: true,
    appSetup: async (a, memo) => {
      ensure();
      if (state.appSetup) await state.appSetup(a, memo);
    },
  }));
}

/** The reference's own class names on these pages, probed on both sides. */
export const DOMAIN_PROBES = [
  "#app main .group",
  "#app main .group > .row",
  "#app main .row .body strong",
  "#app main .row .body small",
  "#app main .row .value",
  "#app main .row .switch",
  ".tabs",
  ".tabs button",
  ".tabs button.active",
  "#app main h2",
  ".badge",
  ".fold-card",
  ".fold-top",
  ".field",
  ".field > span",
  ".field input",
  ".field select",
  ".field textarea",
  "form .check",
  "#app main .actions",
  "#app main .btn.full",
  "#app main .btn.outline",
  "#app main .btn.primary",
  "#app main .empty",
  "#app main .note",
  ".stories",
  ".story",
  ".story-ring",
  ".section-head",
  ".section-head .link",
  ".row.unread",
  "#app main .dot",
  "#app main .row-icon",
  ".paper",
  "dialog .row",
  "dialog .btn",
];
