/** Actual run/tool observations only. This projection never invents reasoning steps. */
import type { Event, Run, RunStatus } from "@lonora/contracts";
import type { AvatarStateId } from "./trading-avatar-motion";

export type ActivityPhase =
  | "queued"
  | "preparing"
  | "thinking"
  | "searching"
  | "reading"
  | "analyzing"
  | "executing"
  | "learning"
  | "sending"
  | "writing"
  | "waiting_input"
  | "waiting_external"
  | "completed"
  | "failed"
  | "cancelled";
/** How a tool acts, from the registry's own metadata (E2): never guessed from its name. */
export type ActivityEffect = "read" | "change" | "financial";
export type ActivityCall = {
  id: string;
  /** The tool's registry id: for Technical details and tests, never the normal view. */
  name: string;
  /** The tool's capability family (toolset), as the server reported it. */
  toolset?: string;
  effect?: ActivityEffect;
  status: "running" | "completed" | "failed" | "cancelled" | "interrupted";
  started_at?: string;
  completed_at?: string;
};
const statuses: Record<string, RunStatus> = {
  "run.queued": "queued",
  "run.leased": "leased",
  "run.recovered": "leased",
  "run.running": "running",
  "run.waiting_input": "waiting_input",
  "run.waiting_takeover": "waiting_takeover",
  "run.completed": "completed",
  "run.failed": "failed",
  "run.cancelled": "cancelled",
};
function validRun(value: unknown): value is Run {
  if (!value || typeof value !== "object") return false;
  const row = value as Partial<Run>;
  return (
    typeof row.id === "string" &&
    typeof row.thread_id === "string" &&
    typeof row.agent_id === "string" &&
    typeof row.created_at === "string" &&
    typeof row.updated_at === "string" &&
    typeof row.trigger === "string" &&
    typeof row.model_metadata === "object" &&
    Object.values(statuses).includes(row.status as RunStatus)
  );
}
/** New server projections and lifecycle events update a view without a full-history GET. */
export function projectRunEvents(runs: Run[], events: Event[], threadId?: string): Run[] {
  const rows = new Map<string, Run>();
  for (const row of runs) {
    if (threadId && row.thread_id !== threadId) continue;
    const previous = rows.get(row.id);
    if (!previous || Date.parse(row.updated_at) >= Date.parse(previous.updated_at))
      rows.set(row.id, row);
  }
  for (const event of [...events].sort((a, b) => a.cursor - b.cursor)) {
    if (!event.run_id || (threadId && event.thread_id !== threadId)) continue;
    const snapshot = event.payload.run;
    if (
      validRun(snapshot) &&
      snapshot.id === event.run_id &&
      snapshot.thread_id === event.thread_id &&
      snapshot.agent_id === event.agent_id
    ) {
      const prior = rows.get(snapshot.id);
      if (!prior || Date.parse(snapshot.updated_at) >= Date.parse(prior.updated_at))
        rows.set(snapshot.id, snapshot);
    }
    const row = rows.get(event.run_id),
      status = statuses[event.kind];
    if (!row || !status || Date.parse(event.created_at) < Date.parse(row.updated_at)) continue;
    rows.set(row.id, {
      ...row,
      status,
      updated_at: event.created_at,
      ...(typeof event.payload.code === "string" ? { error_code: event.payload.code } : {}),
    });
  }
  return [...rows.values()].sort((a, b) => a.created_at.localeCompare(b.created_at));
}
type ToolKind = { toolset?: unknown; effect?: unknown };
function effectOf(value: unknown): ActivityEffect | undefined {
  return value === "read" || value === "change" || value === "financial" ? value : undefined;
}
/** The phase a running tool puts the agent in, from its toolset and effect. */
function callPhase({ toolset, effect }: ToolKind): ActivityPhase {
  const change = effect === "change";
  if (effect === "financial") return "executing";
  if (toolset === "memory" && change) return "learning";
  if (toolset === "collaboration" && change) return "sending";
  if (toolset === "charts" && change) return "writing";
  if (toolset === "files" && change) return "executing";
  if (toolset === "research") return "searching";
  if (["market", "charts", "intelligence", "account"].includes(String(toolset))) return "analyzing";
  return "reading";
}
function toolPhase(calls: ToolKind[]): ActivityPhase {
  // The strongest phase among concurrent calls: acting outranks reading.
  const order: ActivityPhase[] = [
    "executing",
    "learning",
    "sending",
    "writing",
    "searching",
    "analyzing",
    "reading",
  ];
  const phases = calls.map(callPhase);
  return order.find((phase) => phases.includes(phase)) ?? "reading";
}
function observedPhase(
  kind: unknown,
  tool?: ToolKind & { name?: unknown },
): ActivityPhase | undefined {
  if (kind === "run.context_started") return "preparing";
  if (kind === "run.reply_started") return "thinking";
  if (kind === "run.delta" || kind === "run.rich_partial") return "writing";
  if (kind === "tool.started" && typeof tool?.name === "string") return toolPhase([tool]);
  if (["tool.completed", "tool.failed", "tool.cancelled"].includes(String(kind))) return "thinking";
  return undefined;
}
const avatar: Record<ActivityPhase, AvatarStateId> = {
  queued: "waiting",
  preparing: "thinking",
  thinking: "thinking",
  searching: "searching",
  reading: "inspecting",
  analyzing: "analyzing",
  executing: "executing",
  learning: "learning",
  sending: "sending",
  writing: "writing",
  waiting_input: "reviewing",
  waiting_external: "reviewing",
  completed: "success",
  failed: "error",
  cancelled: "waiting",
};
export function turnActivity(
  run: Run,
  events: Event[],
): { phase: ActivityPhase; avatar: AvatarStateId; calls: ActivityCall[]; observedAt: string } {
  const calls = new Map<string, ActivityCall>();
  let phase: ActivityPhase =
    run.stream?.phase === "streaming" && (run.stream.text || run.stream.rich_content?.parts.length)
      ? "writing"
      : "preparing";
  const saved = run.model_metadata?.activity;
  const snapshot = saved && typeof saved === "object" && !Array.isArray(saved) ? saved : undefined;
  const snapshotPhase = observedPhase(snapshot?.kind, snapshot);
  let phaseAt =
    snapshotPhase && typeof snapshot?.observed_at === "string"
      ? Date.parse(snapshot.observed_at)
      : 0;
  if (snapshotPhase && Number.isFinite(phaseAt)) phase = snapshotPhase;
  else phaseAt = 0;
  let observedAt = phaseAt ? String(snapshot?.observed_at) : run.updated_at;
  for (const event of [...events].sort((a, b) => a.cursor - b.cursor)) {
    if (event.run_id !== run.id) continue;
    const nextPhase = observedPhase(event.kind, event.payload);
    const eventTime = Date.parse(event.created_at);
    if (nextPhase && (eventTime >= phaseAt || (!phaseAt && !Number.isFinite(eventTime)))) {
      phase = nextPhase;
      phaseAt = Number.isFinite(eventTime) ? eventTime : phaseAt;
      observedAt = event.created_at;
    }
    const id = event.payload.call_id;
    if (typeof id !== "string" || !id || !event.kind.startsWith("tool.")) continue;
    const previous = calls.get(id);
    const name =
      (typeof event.payload.name === "string" && event.payload.name.trim()) || previous?.name;
    if (!name) continue;
    const toolset =
      typeof event.payload.toolset === "string" ? event.payload.toolset : previous?.toolset;
    const effect = effectOf(event.payload.effect) ?? previous?.effect;
    if (event.kind === "tool.started")
      calls.set(id, {
        id,
        name,
        ...(toolset ? { toolset } : {}),
        ...(effect ? { effect } : {}),
        status: "running",
        started_at: event.created_at,
      });
    if (["tool.completed", "tool.failed", "tool.cancelled"].includes(event.kind))
      calls.set(id, {
        ...previous,
        id,
        name,
        status:
          event.kind === "tool.cancelled"
            ? "cancelled"
            : event.kind === "tool.failed" || event.payload.ok === false
              ? "failed"
              : "completed",
        completed_at: event.created_at,
      });
  }
  const active = [...calls.values()].filter((call) => call.status === "running");
  if (active.length) phase = toolPhase(active);
  const stable: Partial<Record<RunStatus, ActivityPhase>> = {
    queued: "queued",
    waiting_input: "waiting_input",
    waiting_takeover: "waiting_external",
    completed: "completed",
    failed: "failed",
    cancelled: "cancelled",
  };
  phase = stable[run.status] ?? phase;
  if (["completed", "failed", "cancelled"].includes(run.status)) {
    for (const call of active) calls.set(call.id, { ...call, status: "interrupted" });
  }
  return { phase, avatar: avatar[phase], calls: [...calls.values()].slice(-24), observedAt };
}

type Label = { readonly en: string; readonly ar: string };
const callLabels: Readonly<
  Record<string, Partial<Record<ActivityEffect, Label>> & { read: Label }>
> = {
  trading: {
    read: { en: "Checking trades", ar: "يراجع الصفقات" },
    change: { en: "Updating trading safeguards", ar: "يحدّث ضوابط التداول" },
    financial: { en: "Placing a trade action", ar: "ينفّذ إجراء تداول" },
  },
  goals: {
    read: { en: "Reading a plan", ar: "يقرأ خطة" },
    change: { en: "Updating a plan", ar: "يحدّث خطة" },
    financial: { en: "Running a plan step", ar: "ينفّذ خطوة من خطة" },
  },
  market: {
    read: { en: "Reading market data", ar: "يقرأ بيانات السوق" },
    change: { en: "Setting a market watch", ar: "يضبط مراقبة للسوق" },
  },
  charts: {
    read: { en: "Reading a chart", ar: "يقرأ رسمًا بيانيًا" },
    change: { en: "Working on a chart", ar: "يعمل على رسم بياني" },
  },
  account: { read: { en: "Reading the account", ar: "يقرأ الحساب" } },
  research: { read: { en: "Searching sources", ar: "يبحث في المصادر" } },
  intelligence: {
    read: { en: "Reviewing analysis", ar: "يراجع التحليل" },
    change: { en: "Recording analysis", ar: "يسجّل التحليل" },
  },
  memory: {
    read: { en: "Recalling", ar: "يسترجع من الذاكرة" },
    change: { en: "Saving to memory", ar: "يحفظ في الذاكرة" },
  },
  files: {
    read: { en: "Reading files", ar: "يقرأ الملفات" },
    change: { en: "Working in the workspace", ar: "يعمل في مساحة العمل" },
  },
  tasks: {
    read: { en: "Checking tasks", ar: "يراجع المهام" },
    change: { en: "Updating tasks", ar: "يحدّث المهام" },
  },
  collaboration: {
    read: { en: "Checking with agents", ar: "يراجع الوكلاء" },
    change: { en: "Messaging agents", ar: "يراسل الوكلاء" },
  },
  voice: {
    read: { en: "Checking what needs you", ar: "يراجع ما ينتظرك" },
    change: { en: "Notifying you", ar: "يرسل لك تنبيهًا" },
  },
};
const genericCall: Label = { en: "Using a tool", ar: "يستخدم أداة" };

const SKILL_WORK: Label = { en: "Working on a skill", ar: "يعمل على مهارة" };
const SKILL_READ: Label = { en: "Reviewing skills", ar: "يراجع المهارات" };
const HELPER: Label = { en: "Starting a helper agent", ar: "يبدأ وكيلًا مساعدًا" };
const WATCH_STEER: Label = { en: "Updating a market watch", ar: "يحدّث مراقبة للسوق" };
/** The few tools whose family label would state the wrong action, by registry id. */
const toolLabels: Readonly<Record<string, Label>> = {
  owner_call_request: { en: "Preparing a call", ar: "يجهّز اتصالًا" },
  owner_action_propose: { en: "Preparing a card for you", ar: "يجهّز بطاقة لك" },
  wait_for_input: { en: "Waiting for your reply", ar: "ينتظر ردك" },
  group_silence: { en: "Staying quiet in the group", ar: "يلتزم الصمت في المجموعة" },
  market_position_size: { en: "Sizing a position", ar: "يحسب حجم المركز" },
  market_candles_to_workspace: {
    en: "Copying market data to the workspace",
    ar: "ينسخ بيانات السوق إلى مساحة العمل",
  },
  consult_model: { en: "Consulting another model", ar: "يستشير نموذجًا آخر" },
  model_request: { en: "Changing its model", ar: "يغيّر نموذجه" },
  model_list: { en: "Checking its models", ar: "يراجع نماذجه" },
  mcp_execute: { en: "Using a connected tool", ar: "يستخدم أداة متصلة" },
  agent_create: { en: "Creating an agent", ar: "ينشئ وكيلًا" },
  agent_inspect: { en: "Reviewing an agent's work", ar: "يراجع عمل وكيل" },
  agent_control: { en: "Steering an agent's work", ar: "يوجّه عمل وكيل" },
  supervision_change: { en: "Setting supervision", ar: "يضبط الإشراف" },
  news_feed_subscribe: { en: "Subscribing to a news feed", ar: "يشترك في موجز أخبار" },
  capabilities_list: { en: "Checking capabilities", ar: "يراجع القدرات" },
  watch_cancel: WATCH_STEER,
  watch_pause: WATCH_STEER,
  watch_resume: WATCH_STEER,
  watch_update: WATCH_STEER,
  child_agent_create: HELPER,
  subagent_spawn: HELPER,
  skill_package_control: SKILL_WORK,
  skill_package_create: SKILL_WORK,
  skill_package_import: SKILL_WORK,
  skill_package_validate: SKILL_WORK,
  skill_repository_inspect: SKILL_READ,
  skill_view: SKILL_READ,
  skills_list: SKILL_READ,
};

/**
 * The owner-facing line for one tool call, from its toolset and effect (E2 metadata), in
 * Arabic or English; a short override names the few tools whose family label would be
 * wrong. The registry id stays behind "Technical details".
 */
export function activityCallLabel(
  call: Pick<ActivityCall, "toolset" | "effect"> & { name?: string },
  locale: string,
): string {
  const family = call.toolset ? callLabels[call.toolset] : undefined;
  const override =
    call.name && Object.hasOwn(toolLabels, call.name) ? toolLabels[call.name] : undefined;
  const label =
    override ??
    (family ? (family[call.effect ?? "read"] ?? family.change ?? family.read) : undefined);
  return (label ?? genericCall)[locale.toLowerCase().startsWith("ar") ? "ar" : "en"];
}
