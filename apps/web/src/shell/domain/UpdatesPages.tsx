import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { ActivityCode, ActivityEntry, AttentionNotification } from "@lonora/contracts";
import { attentionAlwaysShows } from "@lonora/core";
import { Icon } from "@lonora/ui-web";
import { useState } from "react";
import { AgentAvatar } from "../../components/ai/AgentAvatar";
import { useAttentionLabels } from "../../components/ai/AttentionInbox";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useAttention } from "../../providers/AttentionProvider";
import { useShellData } from "../data";
import { clockTime } from "../lists/ThreadRow";
import { useNavigation } from "../navigation";
import { recoveryPath } from "../routes";
import { SkHead, SkPage, SkRows } from "../Skeleton";
import { useToast } from "../Toast";
import { domainApi } from "./api";
import { useLoad } from "./hooks";
import { routineTitle, scheduleFacts, useScheduleDetails } from "./SchedulesPages";
import { Empty } from "./ui";

function activityTitle(code: ActivityCode): string {
  switch (code) {
    case "agent_created":
      return t`Agent created`;
    case "authority_changed":
      return t`Delegation changed`;
    case "limits_changed":
      return t`Account limits changed`;
    case "restriction_set":
      return t`Restriction set`;
    case "restriction_lifted":
      return t`Restriction lifted`;
    case "operation_resolved":
      return t`Operation resolved`;
    case "approval_approved":
      return t`You approved a request`;
    case "approval_rejected":
      return t`You rejected a request`;
    case "task_created":
      return t`Task created`;
    case "task_completed":
      return t`Task completed`;
    case "task_cancelled":
      return t`Task cancelled`;
    case "skill_created":
      return t`Skill created`;
    case "skill_updated":
      return t`Skill updated`;
    case "supervision_granted":
      return t`Supervision started`;
    case "supervision_revoked":
      return t`Supervision ended`;
    case "watch_triggered":
      return t`A watch was met`;
    case "goal_created":
      return t`Goal added`;
    default:
      return t`Knowledge added`;
  }
}

const when = (iso: string) => {
  const at = new Date(iso);
  return at.toDateString() === new Date().toDateString()
    ? clockTime(iso)
    : at.toLocaleDateString("en-GB", { day: "2-digit", month: "2-digit" });
};

/** One «سجل الإجراءات» row: what happened, to what, and when; all from the server. */
function ActivityRow({ entry, boxed = false }: { entry: ActivityEntry; boxed?: boolean }) {
  const data = useShellData();
  const agent = data.agents.find((row) => row.id === entry.agent_id)?.name ?? "";
  const named = entry.code.startsWith("task_") || entry.code.startsWith("skill_");
  const detail = named && agent ? `${entry.subject} · ${agent}` : entry.subject || agent;
  return (
    <div className="row" data-activity={entry.code}>
      {boxed ? (
        <span className="row-icon">
          <Icon name="check" />
        </span>
      ) : (
        <Icon name="check" />
      )}
      <span className="body">
        <strong>{activityTitle(entry.code)}</strong>
        <small>
          <bdi>{detail}</bdi>
        </small>
      </span>
      <span className="value">
        <span className="ltr">{when(entry.created_at)}</span>
      </span>
    </div>
  );
}

/** «سجل الإجراءات» (Q45): a projection of durable events; the client invents nothing. */
export function ActivityPage() {
  const toast = useToast();
  const feed = useLoad(() => domainApi.activity(), "activity");
  const [more, setMore] = useState<ActivityEntry[]>([]);
  const [next, setNext] = useState<number | null | undefined>();
  if (feed.loading && !feed.data)
    return (
      <SkPage>
        <SkRows count={9} icon group />
      </SkPage>
    );
  if (feed.error != null && !feed.data) return <p role="alert">{userError(feed.error)}</p>;
  const items = [...(feed.data?.items ?? []), ...more];
  const cursor = next === undefined ? feed.data?.next_before : next;
  if (!items.length) return <Empty>{t`No activity yet.`}</Empty>;
  return (
    <div className="domain-page">
      <div className="group">
        {items.map((entry) => (
          <ActivityRow key={entry.id} entry={entry} />
        ))}
      </div>
      {cursor ? (
        <button
          type="button"
          className="btn full ghost"
          onClick={async () => {
            try {
              const page = await domainApi.activity(cursor);
              setMore((rows) => [...rows, ...page.items]);
              setNext(page.next_before);
            } catch (cause) {
              toast(userError(cause), { type: "error" });
            }
          }}
        >
          <Trans>Show more</Trans>
        </button>
      ) : null}
    </div>
  );
}

/** «المستجدات»: stories, «التنبيهات», «المواعيد القادمة», «آخر الإجراءات». */
export function UpdatesPage() {
  const data = useShellData();
  const nav = useNavigation();
  const toast = useToast();
  const attention = useAttention();
  const labels = useAttentionLabels();
  const notes = useLoad(
    () => api.get<AttentionNotification[]>("/attention/history"),
    "attention-history",
  );
  const routines = useLoad(() => domainApi.routines(), "routines:*");
  const feed = useLoad(() => domainApi.activity(), "activity");
  const details = useScheduleDetails(routines.reload);
  if (
    [notes, routines, feed].some((load) => load.data === undefined && load.error == null) ||
    (!attention.loaded && attention.error == null)
  )
    return (
      <SkPage>
        <SkHead width={24} />
        <SkRows count={2} size={40} group />
        <SkHead width={20} />
        <SkRows count={5} icon group />
      </SkPage>
    );
  const upcoming = (routines.data ?? []).filter((row) => row.enabled);
  const ring = (agentId: string) =>
    data.inbox.some((entry) => entry.agent_id === agentId && entry.unread_count > 0) ||
    upcoming.some((row) => row.agent_id === agentId);
  const list = notes.data ?? [];
  // The tab dot's own list: a row is unread while it is still among the open items.
  const unread = (item: AttentionNotification) =>
    attention.loaded
      ? attention.items.some((open) => open.id === item.id)
      : item.status === "pending" || item.status === "ready";
  // «تحديد الكل كمقروء» leaves critical and action_required items to the owner's own look.
  const markable = list.some((item) => unread(item) && !attentionAlwaysShows(item.importance));
  const agentName = (id: string) => data.agents.find((agent) => agent.id === id)?.name ?? "";
  const readAll = async () => {
    try {
      await domainApi.seenAll();
      attention.refresh();
    } catch (cause) {
      toast(userError(cause), { type: "error" });
    }
  };
  const detail = (item: AttentionNotification) =>
    item.parameters.summary ? (
      <span dir="auto" data-testid="attention-summary">
        {item.parameters.summary}
      </span>
    ) : (
      <>
        <bdi>{agentName(item.agent_id)}</bdi>
        {item.parameters.symbol ? (
          <>
            {" · "}
            <bdi>{item.parameters.symbol}</bdi>
          </>
        ) : null}
      </>
    );
  const openNote = (item: AttentionNotification) => {
    if (unread(item))
      attention.seen(item.id).catch((cause) => toast(userError(cause), { type: "error" }));
    // A group's notification opens the group conversation, as the inbox did.
    // A broker outage opens the recovery page for its account (recovery.page).
    nav.go(
      item.code === "broker_degraded"
        ? recoveryPath(item.parameters.account_id)
        : item.parameters.group_id
          ? `/app/g/${item.parameters.group_id}`
          : `/app/${item.agent_id}?thread=${item.thread_id}`,
    );
  };
  const acts = (feed.data?.items ?? []).slice(0, 4);
  return (
    <div className="domain-page">
      {/* biome-ignore lint/a11y/useSemanticElements: the reference's labelled row of stories. */}
      <div className="stories" role="group" aria-label={t`Agents`}>
        {data.agents.map((agent) => (
          <button
            key={agent.id}
            type="button"
            className={`story ${ring(agent.id) ? "ring" : ""}`.trim()}
            aria-label={ring(agent.id) ? t`${agent.name}, has something new` : agent.name}
            onClick={() => nav.go(`/app/${agent.id}`)}
          >
            <span className="story-ring">
              <AgentAvatar agent={agent} />
            </span>
            <small>
              <bdi>{agent.name}</bdi>
            </small>
          </button>
        ))}
      </div>
      <div className="section-head">
        <h3>
          <Trans context="updates section">Notifications</Trans>
        </h3>
        {markable && (
          <button type="button" className="link" onClick={() => void readAll()}>
            <Trans>Mark all as read</Trans>
          </button>
        )}
      </div>
      <div className="group">
        {notes.error != null && !notes.data ? (
          <p className="pad small" role="alert">
            {userError(notes.error)}
          </p>
        ) : list.length ? (
          list.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`row ${unread(item) ? "unread" : ""}`.trim()}
              data-attention-id={item.id}
              onClick={() => openNote(item)}
            >
              <span className="row-icon">
                <Icon name="bell" />
              </span>
              <span className="body">
                <strong>{labels[item.code]}</strong>
                <small>{detail(item)}</small>
                {unread(item) && attentionAlwaysShows(item.importance) ? (
                  <small>
                    <Trans>Needs your action</Trans>
                  </small>
                ) : null}
              </span>
              <span className="value">
                <span className="ltr">{when(item.created_at)}</span>
              </span>
              {unread(item) && <span className="dot" role="img" aria-label={t`Unread`} />}
            </button>
          ))
        ) : (
          <p className="pad muted small">
            <Trans>No notifications.</Trans>
          </p>
        )}
      </div>
      <div className="section-head">
        <h3>
          <Trans>Upcoming</Trans>
        </h3>
      </div>
      <div className="group">
        {routines.error != null && !routines.data ? (
          <p className="pad small" role="alert">
            {userError(routines.error)}
          </p>
        ) : upcoming.length ? (
          upcoming.map((routine) => {
            const agent = data.agents.find((row) => row.id === routine.agent_id);
            const facts = scheduleFacts(routine);
            return (
              <button
                key={routine.id}
                type="button"
                className="row"
                onClick={() => details(routine)}
              >
                {agent ? (
                  <AgentAvatar agent={agent} />
                ) : (
                  <span className="row-icon">
                    <Icon name="clock" />
                  </span>
                )}
                <span className="body">
                  <strong>
                    <bdi>{routineTitle(routine)}</bdi>
                  </strong>
                  <small>
                    <bdi>{agent?.name ?? ""}</bdi> · {facts.repeat}
                  </small>
                </span>
                <span className="value ltr">{facts.time}</span>
              </button>
            );
          })
        ) : (
          <p className="pad muted small">
            <Trans>No enabled schedules.</Trans>
          </p>
        )}
      </div>
      <div className="section-head">
        <h3>
          <Trans>Latest actions</Trans>
        </h3>
      </div>
      <div className="group">
        {feed.error != null && !feed.data ? (
          <p className="pad small" role="alert">
            {userError(feed.error)}
          </p>
        ) : acts.length ? (
          <>
            {acts.map((entry) => (
              <ActivityRow key={entry.id} entry={entry} boxed />
            ))}
            <button
              type="button"
              className="btn full ghost"
              onClick={() => nav.go("/app/activity")}
            >
              <Trans>Show the full log</Trans>
            </button>
          </>
        ) : (
          <p className="pad muted small">
            <Trans>No activity yet.</Trans>
          </p>
        )}
      </div>
    </div>
  );
}
