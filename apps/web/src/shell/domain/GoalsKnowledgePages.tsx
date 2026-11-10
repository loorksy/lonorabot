import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import { userError } from "../../lib/user_error";
import { useNavigation } from "../navigation";
import { SkRows } from "../Skeleton";
import { useToast } from "../Toast";
import { domainApi, type TradingGoalView } from "./api";
import { isTrader, useAgentParam, useItemParam, useLoad } from "./hooks";
import { Area, Check, Empty, Field, FormPage, Grouped, Row, SelectField, text } from "./ui";

const goalState = (status: string) =>
  status === "completed"
    ? t({ message: "Completed", context: "goal" })
    : status === "cancelled"
      ? t({ message: "Cancelled", context: "goal" })
      : status === "paused"
        ? t({ message: "Paused", context: "goal" })
        : t({ message: "Active", context: "goal" });

const Missing = ({ error }: { error: unknown }) =>
  error != null ? (
    <p role="alert">{userError(error)}</p>
  ) : (
    <Empty>{t`The item no longer exists.`}</Empty>
  );

/** «الأهداف»: a trading agent's plans (Q41), or a light goal list for any other agent. */
export function GoalsPage() {
  const agent = useAgentParam();
  const nav = useNavigation();
  const trader = isTrader(agent);
  const light = useLoad(
    agent && !trader ? () => domainApi.goals(agent.id) : null,
    `goals:${agent?.id}`,
  );
  const plans = useLoad(
    agent && trader ? () => domainApi.tradingGoals(agent.id) : null,
    `trading-goals:${agent?.id}`,
  );
  if (!agent) return null;
  const loading = trader ? plans.loading && !plans.data : light.loading && !light.data;
  const error = trader ? plans.error : light.error;
  if (loading) return <SkRows count={3} />;
  const openPlan = (goal: TradingGoalView) =>
    nav.go(`/app/${agent.id}${goal.thread_id ? `?thread=${goal.thread_id}` : ""}`);
  return (
    <div className="domain-page">
      {error != null && <p role="alert">{userError(error)}</p>}
      <Grouped empty={<Trans>No goals for this agent.</Trans>}>
        {trader
          ? (plans.data ?? []).map((goal) => (
              <Row
                key={goal.id}
                icon={goal.state.status === "completed" ? "check" : "target"}
                title={<bdi>{goal.payload.title ?? ""}</bdi>}
                sub={goal.payload.objective ? <bdi>{goal.payload.objective}</bdi> : undefined}
                value={goalState(String(goal.state.status ?? "active"))}
                onClick={() => openPlan(goal)}
              />
            ))
          : (light.data ?? []).map((goal) => (
              <Row
                key={goal.id}
                icon={goal.payload.done ? "check" : "target"}
                title={<bdi>{goal.payload.title}</bdi>}
                sub={goal.payload.description ? <bdi>{goal.payload.description}</bdi> : undefined}
                value={goal.payload.done ? goalState("completed") : goalState("active")}
                onClick={() => nav.go(`/app/new-goal?agent=${agent.id}&item=${goal.id}`)}
              />
            ))}
      </Grouped>
      <button
        type="button"
        className="btn full outline"
        onClick={() =>
          // A trading goal is a plan the agent drafts under its grant, in its conversation.
          nav.go(trader ? `/app/${agent.id}` : `/app/new-goal?agent=${agent.id}`)
        }
      >
        <Trans>Add a goal</Trans>
      </button>
    </div>
  );
}

/** «تحرير الهدف» (light goals only). */
export function GoalEditPage() {
  const agent = useAgentParam();
  const item = useItemParam();
  const nav = useNavigation();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const goals = useLoad(agent ? () => domainApi.goals(agent.id) : null, `goals:${agent?.id}`);
  const goal = goals.data?.find((row) => row.id === item);
  if (!agent || (item && goals.loading && !goals.data)) return <SkRows count={3} />;
  // An item that failed to load or is gone is never saved again as a new one.
  if (item && !goal) return <Missing error={goals.error} />;
  return (
    <div className="domain-page">
      <FormPage
        name="goal"
        submit={<Trans>Save</Trans>}
        busy={busy}
        onSubmit={async (form) => {
          const value = {
            title: text(form, "title"),
            description: text(form, "description"),
            done: form.get("done") === "on",
          };
          setBusy(true);
          try {
            if (goal) await domainApi.saveGoal(goal, value);
            else await domainApi.createGoal(agent.id, value);
            nav.go(`/app/goals?agent=${agent.id}`, { replace: true });
          } catch (cause) {
            toast(userError(cause), { type: "error" });
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field
          label={t`Goal title`}
          name="title"
          defaultValue={goal?.payload.title}
          required
          maxLength={160}
        />
        <Area
          label={t`Description`}
          name="description"
          defaultValue={goal?.payload.description}
          maxLength={2000}
        />
        <Check
          label={t({ message: "Completed", context: "goal" })}
          name="done"
          defaultChecked={goal?.payload.done}
        />
      </FormPage>
    </div>
  );
}

/** «المعرفة»: the agent's semantic notes and links (Q40). */
export function KnowledgePage() {
  const agent = useAgentParam();
  const nav = useNavigation();
  const items = useLoad(
    agent ? () => domainApi.knowledge(agent.id) : null,
    `knowledge:${agent?.id}`,
  );
  if (!agent) return null;
  return (
    <div className="domain-page">
      <p className="muted">
        <Trans>
          Knowledge of <bdi>{agent.name}</bdi>
        </Trans>
      </p>
      {items.loading && !items.data ? (
        <SkRows count={3} />
      ) : (
        <>
          {items.error != null && <p role="alert">{userError(items.error)}</p>}
          <Grouped empty={<Trans>No sources for this agent.</Trans>}>
            {(items.data ?? []).map((item) => (
              <Row
                key={item.id}
                icon="book"
                title={<bdi>{item.title}</bdi>}
                sub={item.type === "link" ? t({ message: "Link", context: "knowledge" }) : t`Note`}
                onClick={() => nav.go(`/app/knowledge-edit?agent=${agent.id}&item=${item.id}`)}
              />
            ))}
          </Grouped>
        </>
      )}
      <button
        type="button"
        className="btn full outline"
        onClick={() => nav.go(`/app/knowledge-edit?agent=${agent.id}`)}
      >
        <Trans>Add knowledge</Trans>
      </button>
    </div>
  );
}

/** «تحرير المعرفة»: a note (العنوان، المحتوى) or a link (العنوان، الرابط، المحتوى). */
export function KnowledgeEditPage() {
  const agent = useAgentParam();
  const id = useItemParam();
  const nav = useNavigation();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const items = useLoad(
    agent ? () => domainApi.knowledge(agent.id) : null,
    `knowledge:${agent?.id}`,
  );
  const item = items.data?.find((row) => row.id === id);
  const [type, setType] = useState<"note" | "link" | undefined>();
  if (!agent || (id && items.loading && !items.data)) return <SkRows count={3} />;
  if (id && !item) return <Missing error={items.error} />;
  const kind = type ?? item?.type ?? "note";
  return (
    <div className="domain-page">
      <FormPage
        name="knowledge"
        submit={<Trans>Save</Trans>}
        busy={busy}
        onSubmit={async (form) => {
          const title = text(form, "title");
          const content = text(form, "content");
          setBusy(true);
          try {
            if (kind === "link") {
              const link = { title, url: text(form, "url"), note: content };
              if (item?.type === "link" && item.version)
                await domainApi.saveLink(item.id, item.version, link);
              else await domainApi.addLink(agent.id, link);
            } else if (item?.type === "note") {
              await domainApi.saveNote(agent.id, item.id, title, content);
            } else {
              await domainApi.addNote(agent.id, title, content);
            }
            nav.go(`/app/knowledge?agent=${agent.id}`, { replace: true });
          } catch (cause) {
            toast(userError(cause), { type: "error" });
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label={t`Title`} name="title" defaultValue={item?.title} required maxLength={160} />
        <SelectField
          label={t`Type`}
          name="type"
          value={kind}
          onChange={(value) => setType(value === "link" ? "link" : "note")}
          options={
            item
              ? [
                  [
                    item.type,
                    item.type === "link" ? t({ message: "Link", context: "knowledge" }) : t`Note`,
                  ],
                ]
              : [
                  ["note", t`Note`],
                  ["link", t({ message: "Link", context: "knowledge" })],
                ]
          }
        />
        {kind === "link" && (
          <Field
            label={t({ message: "Link", context: "knowledge" })}
            name="url"
            type="url"
            dir="ltr"
            defaultValue={item?.url ?? ""}
            required
          />
        )}
        <Area
          label={t`Content`}
          name="content"
          defaultValue={item?.content}
          required={kind === "note"}
          maxLength={kind === "note" ? 8000 : 4000}
        />
      </FormPage>
    </div>
  );
}
