import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { Resource, Routine } from "@lonora/contracts";
import { Icon } from "@lonora/ui-web";
import { useState } from "react";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useShellData } from "../data";
import { useNavigation } from "../navigation";
import { SkRows } from "../Skeleton";
import { useSheets } from "../sheets/SheetHost";
import { useToast } from "../Toast";
import { domainApi } from "./api";
import { isTrader, useAgentParam, useLoad } from "./hooks";
import { Empty, Field, FormPage, SelectField, Toggle, text, ValueRow } from "./ui";

type Repeat = "daily" | "workdays" | "weekly";
type Kind = "repeat" | "once" | "condition";
type WatchPayload = {
  symbol?: string;
  condition?: string;
  level?: string;
  prompt?: string;
  enabled?: boolean;
  expires_at?: string | null;
};
type WatchRow = Resource<WatchPayload> & { state?: { code?: string; lifecycle?: string } };
/** A cancelled or expired watch is no longer a schedule; a paused one keeps its switch off. */
const listedWatch = (row: WatchRow) =>
  !!row.payload.prompt &&
  row.state?.code !== "watch_cancelled" &&
  row.state?.lifecycle !== "expired" &&
  !(row.payload.expires_at && new Date(row.payload.expires_at).getTime() <= Date.now());
const until = (row: WatchRow) =>
  row.payload.expires_at
    ? new Date(row.payload.expires_at).toLocaleString("en-GB", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : t`No expiry`;

/** «تأكيد الحذف» (the reference's confirm-delete sheet) before a destructive action. */
export function useConfirm() {
  const sheets = useSheets();
  const toast = useToast();
  return (question: string, action: string, run: () => Promise<void>) =>
    sheets.open({
      id: "confirm-delete",
      title: t`Confirm deletion`,
      body: (
        <>
          <p>{question}</p>
          <div className="actions">
            <button type="button" className="btn" onClick={() => sheets.close()}>
              <Trans>Cancel</Trans>
            </button>
            <button
              type="button"
              className="btn danger"
              onClick={async () => {
                try {
                  await run();
                  sheets.close();
                } catch (cause) {
                  toast(userError(cause), { type: "error" });
                }
              }}
            >
              {action}
            </button>
          </div>
        </>
      ),
    });
}
const zone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
const hhmm = (h: number, m: number) =>
  `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;

/** What one schedule row says: its type, its repeat and its time (the reference's line). */
export function scheduleFacts(routine: Routine) {
  if (routine.run_at) {
    const at = new Date(routine.run_at);
    return {
      kind: t({ message: "Once", context: "schedule type" }),
      repeat: at.toLocaleDateString("en-GB"),
      time: hhmm(at.getHours(), at.getMinutes()),
    };
  }
  const kind = t({ message: "Recurring", context: "schedule type" });
  const cron = /^(\d+) (\d+) \* \* (\*|1-5|\d)$/.exec(routine.cron ?? "");
  if (cron) {
    const repeat =
      cron[3] === "*"
        ? t({ message: "Daily", context: "schedule repeat" })
        : cron[3] === "1-5"
          ? t({ message: "Workdays", context: "schedule repeat" })
          : t({ message: "Weekly", context: "schedule repeat" });
    return { kind, repeat, time: hhmm(Number(cron[2]), Number(cron[1])) };
  }
  const minutes = Math.round((routine.interval_seconds ?? 0) / 60);
  const repeat =
    minutes >= 60 && minutes % 60 === 0
      ? t`Every ${minutes / 60} h`
      : routine.cron
        ? routine.cron
        : t`Every ${minutes} min`;
  const next = new Date(routine.next_run_at);
  return { kind, repeat, time: hhmm(next.getHours(), next.getMinutes()) };
}

export const routineTitle = (routine: Routine) => routine.title || routine.prompt.slice(0, 80);

const conditionText = (payload: WatchPayload) =>
  `${payload.symbol ?? ""} ${
    payload.condition === "below" ? t({ message: "below", context: "watch" }) : t`above`
  } ${payload.level ?? ""}`;

/** The schedule details sheet: «التكرار», «الوقت», «القناة», «حذف الجدول». */
export function useScheduleDetails(onDeleted: () => void) {
  const sheets = useSheets();
  const confirm = useConfirm();
  return (routine: Routine) => {
    const facts = scheduleFacts(routine);
    sheets.open({
      id: "schedule-details",
      title: <bdi>{routineTitle(routine)}</bdi>,
      label: routineTitle(routine),
      body: (
        <>
          <ValueRow label={t`Repeat`} value={facts.repeat} />
          <ValueRow label={t`Time`} value={<span className="ltr">{facts.time}</span>} />
          <ValueRow
            label={t({ message: "Channel", context: "schedule details" })}
            value={t`In the app`}
          />
          <button
            type="button"
            className="btn full danger"
            onClick={() =>
              confirm(t`Delete this schedule?`, t`Delete`, async () => {
                await domainApi.deleteRoutine(routine.id);
                onDeleted();
              })
            }
          >
            <Trans>Delete schedule</Trans>
          </button>
        </>
      ),
    });
  };
}

/** A conditional schedule's sheet: its condition, «حتى», and «إيقاف المراقبة». */
function useWatchDetails(onChanged: () => void) {
  const sheets = useSheets();
  const confirm = useConfirm();
  return (watch: WatchRow) =>
    sheets.open({
      id: "watch-details",
      title: <bdi>{watch.payload.prompt}</bdi>,
      label: watch.payload.prompt ?? "",
      body: (
        <>
          <ValueRow
            label={t({ message: "Condition", context: "watch" })}
            value={<span className="ltr">{conditionText(watch.payload)}</span>}
          />
          <ValueRow label={t`Until`} value={<span className="ltr">{until(watch)}</span>} />
          <ValueRow
            label={t({ message: "Channel", context: "schedule details" })}
            value={t`In the app`}
          />
          <button
            type="button"
            className="btn full danger"
            onClick={() =>
              confirm(t`Stop this watch?`, t`Stop the watch`, async () => {
                await api.post(`/watches/${watch.id}/control`, { action: "cancel" });
                onChanged();
              })
            }
          >
            <Trans>Stop the watch</Trans>
          </button>
        </>
      ),
    });
}

/** «scheduleList»: the routines (and the agent's conditional watches) with their switches. */
export function ScheduleList({ agentId }: { agentId?: string }) {
  const toast = useToast();
  const routines = useLoad(() => domainApi.routines(agentId), `routines:${agentId ?? "*"}`);
  const watches = useLoad(
    agentId ? () => api.get<WatchRow[]>(`/watches?agent_id=${encodeURIComponent(agentId)}`) : null,
    `watches:${agentId ?? "-"}`,
  );
  const details = useScheduleDetails(routines.reload);
  const watchDetails = useWatchDetails(() => watches.reload());
  if (routines.loading && !routines.data) return <SkRows count={3} />;
  if (routines.error != null && !routines.data)
    return <p role="alert">{userError(routines.error)}</p>;
  const rows = (routines.data ?? []).filter((routine) => !routine.goal_id);
  const conditional = (watches.data ?? []).filter(listedWatch);
  const watchToggle = async (watch: WatchRow, on: boolean) => {
    watches.set((list) =>
      list?.map((row) =>
        row.id === watch.id ? { ...row, payload: { ...row.payload, enabled: on } } : row,
      ),
    );
    try {
      await api.post(`/watches/${watch.id}/control`, { action: on ? "resume" : "pause" });
    } catch (cause) {
      toast(userError(cause), { type: "error" });
    }
    watches.reload();
  };
  if (!rows.length && !conditional.length) return <Empty>{t`No scheduled tasks.`}</Empty>;
  const toggle = async (routine: Routine, enabled: boolean) => {
    routines.set((list) => list?.map((row) => (row.id === routine.id ? { ...row, enabled } : row)));
    try {
      await domainApi.saveRoutine(routine.id, {
        title: routine.title,
        prompt: routine.prompt,
        interval_seconds: routine.interval_seconds,
        cron: routine.cron,
        run_at: routine.run_at,
        timezone: routine.timezone,
        enabled,
      });
    } catch (cause) {
      toast(userError(cause), { type: "error" });
      routines.reload();
    }
  };
  return (
    <div className="group">
      {rows.map((routine) => {
        const facts = scheduleFacts(routine);
        return (
          <div className="row" key={routine.id}>
            <Icon name="clock" />
            <button type="button" className="body as-button" onClick={() => details(routine)}>
              <strong>
                <bdi>{routineTitle(routine)}</bdi>
              </strong>
              <small>
                {facts.kind} · {facts.repeat} · <span className="ltr">{facts.time}</span>
              </small>
            </button>
            <Toggle
              on={routine.enabled}
              label={t`Enable ${routineTitle(routine)}`}
              onChange={(next) => void toggle(routine, next)}
            />
          </div>
        );
      })}
      {conditional.map((watch) => (
        <div className="row" key={watch.id}>
          <Icon name="radar" />
          <button type="button" className="body as-button" onClick={() => watchDetails(watch)}>
            <strong>
              <bdi>{watch.payload.prompt}</bdi>
            </strong>
            <small>
              {t({ message: "When a condition is met", context: "schedule type" })} ·{" "}
              <span className="ltr">{conditionText(watch.payload)}</span> ·{" "}
              <span className="ltr">{until(watch)}</span>
            </small>
          </button>
          <Toggle
            on={watch.payload.enabled !== false}
            label={t`Enable ${watch.payload.prompt ?? ""}`}
            onChange={(next) => void watchToggle(watch, next)}
          />
        </div>
      ))}
    </div>
  );
}

/** «المهام المجدولة» of one agent. */
export function SchedulesPage() {
  const agent = useAgentParam();
  const nav = useNavigation();
  return (
    <div className="domain-page">
      {agent && <ScheduleList agentId={agent.id} />}
      <button
        type="button"
        className="btn full outline"
        onClick={() => nav.go(`/app/new-schedule${agent ? `?agent=${agent.id}` : ""}`)}
      >
        <Trans>Schedule a task</Trans>
      </button>
    </div>
  );
}

/** «الشرط»: a price level and its side, e.g. «تحت 2330» or "above 2350" (above by default). */
export function parseCondition(value: string): { level: string; below: boolean } | null {
  const digits = value
    .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660))
    .replace(/٫/g, ".");
  const level = /\d+(?:[.,]\d+)?/.exec(digits)?.[0]?.replace(",", ".");
  if (!level) return null;
  return { level, below: /(تحت|أقل|دون|below|under|<)/i.test(value) };
}

const CRON_DAYS: Record<Repeat, string> = { daily: "*", workdays: "1-5", weekly: "" };

/** «جدولة مهمة». */
export function NewSchedulePage() {
  const data = useShellData();
  const nav = useNavigation();
  const toast = useToast();
  const initial = useAgentParam();
  // The agent list may arrive after the first render: follow `?agent=` until the owner picks.
  const [chosen, setAgentId] = useState<string>();
  const agentId = chosen ?? initial?.id ?? "";
  const [kind, setKind] = useState<Kind>("repeat");
  const [busy, setBusy] = useState(false);
  const agent = data.agents.find((row) => row.id === agentId);
  const canWatch = isTrader(agent) && !!agent?.trading_account_id && !!agent.trading_symbol;
  const kinds: [Kind, string][] = [
    ["repeat", t({ message: "Recurring", context: "schedule type" })],
    ["once", t({ message: "Once", context: "schedule type" })],
    ...(canWatch
      ? ([["condition", t({ message: "When a condition is met", context: "schedule type" })]] as [
          Kind,
          string,
        ][])
      : []),
  ];
  const type = kinds.some(([key]) => key === kind) ? kind : "repeat";
  return (
    <div className="domain-page">
      <FormPage
        name="schedule"
        submit={<Trans>Save schedule</Trans>}
        busy={busy}
        onSubmit={async (form) => {
          const title = text(form, "title");
          const [hour, minute] = (text(form, "time") || "09:00").split(":").map(Number);
          setBusy(true);
          try {
            if (type === "condition" && agent) {
              const condition = parseCondition(text(form, "condition"));
              if (!condition) {
                toast(t`Write the alert condition.`, { type: "warn" });
                return;
              }
              await domainApi.createWatch(agent.id, {
                kind: "price",
                account_id: agent.trading_account_id,
                symbol: agent.trading_symbol,
                condition: condition.below ? "below" : "above",
                level: condition.level,
                prompt: title,
              });
            } else if (type === "once") {
              const date = text(form, "date");
              if (!date) {
                toast(t`Choose the task's date.`, { type: "warn" });
                return;
              }
              const at = new Date(`${date}T${hhmm(hour, minute)}:00`);
              if (at.getTime() <= Date.now()) {
                toast(t`Choose a time that has not passed.`, { type: "warn" });
                return;
              }
              await domainApi.createRoutine(agentId, {
                title,
                prompt: title,
                run_at: at.toISOString(),
                timezone: zone(),
              });
            } else {
              const repeat = text(form, "repeat") as Repeat;
              const day = repeat === "weekly" ? String(new Date().getDay()) : CRON_DAYS[repeat];
              await domainApi.createRoutine(agentId, {
                title,
                prompt: title,
                cron: `${minute} ${hour} * * ${day}`,
                timezone: zone(),
              });
            }
            toast(t`Schedule saved`, { type: "success" });
            nav.go(`/app/routines?agent=${agentId}`, { replace: true });
          } catch (cause) {
            toast(userError(cause), { type: "error" });
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label={t`Task`} name="title" required maxLength={160} />
        <SelectField
          label={t`Agent`}
          name="agent"
          value={agentId}
          onChange={setAgentId}
          options={data.agents.map((row) => [row.id, row.name] as const)}
        />
        <SelectField
          label={t`Schedule type`}
          name="type"
          value={type}
          onChange={(value) => setKind(value as Kind)}
          options={kinds}
        />
        <SelectField
          label={t`Repeat`}
          name="repeat"
          options={[
            ["daily", t({ message: "Daily", context: "schedule repeat" })],
            ["workdays", t({ message: "Workdays", context: "schedule repeat" })],
            ["weekly", t({ message: "Weekly", context: "schedule repeat" })],
          ]}
        />
        <Field label={t`Date`} name="date" type="date" />
        <Field label={t`Time`} name="time" type="time" defaultValue="09:00" />
        {canWatch && <Field label={t`Condition — for the conditional alert`} name="condition" />}
        {/* Lonora is the owner's only channel (Q53); the channel is owner-wide (Q39). */}
        <SelectField label={t`Alert channel`} name="channel" options={[["app", t`In the app`]]} />
      </FormPage>
    </div>
  );
}
