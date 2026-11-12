import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api, type Thread } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useShellData } from "../data";
import { useNavigation } from "../navigation";
import { SkPage, SkRows } from "../Skeleton";
import { useSheets } from "../sheets/SheetHost";
import { useToast } from "../Toast";
import { domainApi, type TaskView } from "./api";
import { useAgentParam, useLoad } from "./hooks";
import { ScheduleList } from "./SchedulesPages";
import {
  Area,
  Empty,
  Field,
  FoldCard,
  FormPage,
  Grouped,
  Row,
  SelectField,
  text,
  ValueRow,
} from "./ui";

const FILTERS = ["active", "scheduled", "done"] as const;
type Filter = (typeof FILTERS)[number];
const TERMINAL = new Set<TaskView["status"]>(["completed", "cancelled", "failed"]);

/** The reference's four task words for the server's statuses. */
export function taskStatus(task: TaskView): string {
  switch (task.status) {
    case "completed":
      return t({ message: "Completed", context: "task status" });
    case "cancelled":
      return t({ message: "Cancelled", context: "task status" });
    case "paused":
      return t({ message: "Paused", context: "task status" });
    case "failed":
    case "waiting":
      return t({ message: "Awaiting review", context: "task status" });
    default:
      return t({ message: "In progress", context: "task status" });
  }
}
const isDone = (task: TaskView) => task.status === "completed" || task.status === "cancelled";

/** «المهام»: نشطة · مجدولة · مكتملة. */
export function TasksPage() {
  const data = useShellData();
  const nav = useNavigation();
  // The tab is in the address, so Back returns to the tab the owner was on.
  const [params, setParams] = useSearchParams();
  const filter = FILTERS.find((key) => key === params.get("tab")) ?? "active";
  const choose = (key: Filter) =>
    setParams(
      (old) => {
        const next = new URLSearchParams(old);
        if (key === "active") next.delete("tab");
        else next.set("tab", key);
        return next;
      },
      { replace: true },
    );
  const tasks = useLoad(() => domainApi.tasks(), "tasks");
  useEffect(() => {
    if (params.get("new") === "1") nav.go("/app/new-task", { replace: true });
  }, [params, nav]);
  const tabs: [Filter, string][] = [
    ["active", t({ message: "Active", context: "tasks tab" })],
    ["scheduled", t({ message: "Scheduled", context: "tasks tab" })],
    ["done", t({ message: "Completed", context: "tasks tab" })],
  ];
  const agentName = (id: string) => data.agents.find((agent) => agent.id === id)?.name ?? "";
  const list = (tasks.data ?? []).filter((task) =>
    filter === "done" ? isDone(task) : !isDone(task),
  );
  return (
    <div className="domain-page">
      <div className="tabs" role="tablist">
        {tabs.map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={filter === key}
            className={filter === key ? "active" : ""}
            onClick={() => choose(key)}
          >
            {label}
          </button>
        ))}
      </div>
      {filter === "scheduled" ? (
        <>
          <ScheduleList />
          <button
            type="button"
            className="btn full outline"
            onClick={() => nav.go("/app/new-schedule")}
          >
            <Trans>Schedule a task</Trans>
          </button>
        </>
      ) : tasks.loading && !tasks.data ? (
        <SkPage>
          <SkRows count={7} icon group />
        </SkPage>
      ) : tasks.error != null && !tasks.data ? (
        <p role="alert">{userError(tasks.error)}</p>
      ) : (
        <Grouped empty={<Trans>No tasks.</Trans>}>
          {list.map((task) => (
            <Row
              key={task.id}
              icon={task.status === "completed" ? "check" : "task"}
              title={<bdi>{task.title}</bdi>}
              sub={
                <>
                  <bdi>{agentName(task.agent_id)}</bdi> · {taskStatus(task)}
                </>
              }
              onClick={() => nav.go(`/app/tasks/${task.id}`)}
            />
          ))}
        </Grouped>
      )}
    </div>
  );
}

const dueLabel = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleString("en-GB", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : t({ message: "Not set", context: "task due" });

/** «تفاصيل المهمة». */
export function TaskPage() {
  const { taskId = "" } = useParams();
  const data = useShellData();
  const nav = useNavigation();
  const sheets = useSheets();
  const toast = useToast();
  const loaded = useLoad(() => domainApi.task(taskId), `task:${taskId}`);
  const [busy, setBusy] = useState(false);
  const task = loaded.data;
  if (loaded.loading && !task)
    return (
      <SkPage>
        <SkRows count={3} icon group />
      </SkPage>
    );
  if (!task) return <Empty>{t`The task no longer exists.`}</Empty>;
  const agent = data.agents.find((row) => row.id === task.agent_id);
  const act = async (run: () => Promise<TaskView>, done?: string) => {
    setBusy(true);
    try {
      const next = await run();
      loaded.set(() => ({ ...task, ...next }));
      if (done) toast(done, { type: "success" });
    } catch (cause) {
      toast(userError(cause), { type: "error" });
      loaded.reload();
    } finally {
      setBusy(false);
    }
  };
  const description = task.description;
  const confirmDelete = () =>
    sheets.open({
      id: "confirm-delete",
      title: t`Confirm deletion`,
      body: (
        <>
          <p>
            <Trans>Delete this task?</Trans>
          </p>
          <div className="actions">
            <button type="button" className="btn" onClick={() => sheets.close()}>
              <Trans>Cancel</Trans>
            </button>
            <button
              type="button"
              className="btn danger"
              onClick={async () => {
                try {
                  await api.delete(`/tickets/${task.id}`);
                  sheets.close();
                  nav.go("/app/tasks", { replace: true });
                } catch (cause) {
                  toast(userError(cause), { type: "error" });
                }
              }}
            >
              <Trans>Delete</Trans>
            </button>
          </div>
        </>
      ),
    });
  return (
    <div className="domain-page">
      <h2>
        <bdi>{task.title}</bdi>
      </h2>
      <span className="badge">{taskStatus(task)}</span>
      <FoldCard title={t`Task details`} summary={description.slice(0, 110)}>
        <p className="muted">{description}</p>
        <ValueRow label={t`Agent`} value={<bdi>{agent?.name ?? ""}</bdi>} />
        <ValueRow label={t`Due`} value={<span className="ltr">{dueLabel(task.due_at)}</span>} />
        <ValueRow
          label={t`Completion criterion`}
          value={task.completion_criteria || t`The requested work is done`}
        />
      </FoldCard>
      <div className="actions">
        <button
          type="button"
          className="btn primary"
          onClick={() => nav.go(`/app/${task.agent_id}?thread=${task.origin_thread_id}`)}
        >
          <Trans>View conversation</Trans>
        </button>
        {/* Each button sends its own action: a task held for the owner can be both. */}
        {task.can_pause && (
          <button
            type="button"
            className="btn outline"
            disabled={busy}
            onClick={() => void act(() => domainApi.controlTask(task, "pause"))}
          >
            <Trans context="task">Pause</Trans>
          </button>
        )}
        {task.can_resume && (
          <button
            type="button"
            className="btn outline"
            disabled={busy}
            onClick={() => void act(() => domainApi.controlTask(task, "resume"))}
          >
            <Trans>Resume</Trans>
          </button>
        )}
      </div>
      <div className="actions">
        {!isDone(task) && task.control_requested !== "complete" && (
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => void act(() => domainApi.completeTask(task), t`Task completed`)}
          >
            <Trans>Mark as completed</Trans>
          </button>
        )}
        {TERMINAL.has(task.status) && (
          <button type="button" className="btn danger" onClick={confirmDelete}>
            <Trans>Delete</Trans>
          </button>
        )}
      </div>
    </div>
  );
}

/** «موعد الإنجاز» is a time of day: today at that time, or tomorrow once it has passed. */
export function dueFromTime(value: string, now = new Date()): string | null {
  const match = /^(\d{2}):(\d{2})$/.exec(value);
  if (!match) return null;
  const due = new Date(now);
  due.setHours(Number(match[1]), Number(match[2]), 0, 0);
  if (due.getTime() <= now.getTime()) due.setDate(due.getDate() + 1);
  return due.toISOString();
}

/** «إنشاء مهمة». */
export function NewTaskPage() {
  const data = useShellData();
  const nav = useNavigation();
  const toast = useToast();
  const agent = useAgentParam();
  const [busy, setBusy] = useState(false);
  return (
    <div className="domain-page">
      <FormPage
        name="task"
        submit={<Trans context="submit">Create task</Trans>}
        busy={busy}
        onSubmit={async (form) => {
          const agentId = text(form, "agent");
          setBusy(true);
          try {
            const thread = await api.post<Thread>(`/agents/${agentId}/conversation`, {});
            const task = await domainApi.createTask(agentId, thread.id, {
              title: text(form, "title"),
              description: text(form, "description"),
              due_at: dueFromTime(text(form, "due")),
              completion_criteria: text(form, "criteria"),
            });
            nav.go(`/app/tasks/${task.id}`, { replace: true });
          } catch (cause) {
            toast(userError(cause), { type: "error" });
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label={t`Task title`} name="title" required maxLength={160} />
        <SelectField
          label={t`Responsible agent`}
          name="agent"
          value={agent?.id}
          options={data.agents.map((row) => [row.id, row.name] as const)}
        />
        <Area label={t`What is needed`} name="description" maxLength={16000} />
        <Field label={t`Due time`} name="due" type="time" defaultValue="18:00" />
        <Area label={t`Completion criterion`} name="criteria" maxLength={2000} />
      </FormPage>
    </div>
  );
}
