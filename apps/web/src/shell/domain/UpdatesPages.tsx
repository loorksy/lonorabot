import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { ActivityCode, ActivityEntry, AttentionViewRow } from "@lonora/contracts";
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
import { SkHead, SkPage, SkRows } from "../Skeleton";
import { useToast } from "../Toast";
import { domainApi } from "./api";
import { useLoad } from "./hooks";
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

/** «يحتاج انتباهك» (mandate 11.7): what needs the owner, across all agents, from one
 * server projection (GET /attention/view). A row opens its conversation, where the
 * fixed card or the question stands; opening it decides nothing. */
export function UpdatesPage() {
  const data = useShellData();
  const nav = useNavigation();
  const labels = useAttentionLabels();
  const attention = useAttention();
  const toast = useToast();
  const rows = useLoad(() => api.get<AttentionViewRow[]>("/attention/view"), "attention-view");
  if (rows.data === undefined && rows.error == null)
    return (
      <SkPage>
        <SkHead width={24} />
        <SkRows count={4} icon group />
      </SkPage>
    );
  const agentName = (id: string) => data.agents.find((agent) => agent.id === id)?.name ?? "";
  const title = (row: AttentionViewRow) =>
    row.kind === "owner_question"
      ? t`A question is waiting for your answer`
      : row.code
        ? labels[row.code]
        : "";
  const open = (row: AttentionViewRow) => {
    // Opening an alert reads it; a card or a question stays until it is answered.
    if (row.kind === "agent_alert" || row.kind === "system_alert")
      attention.seen(row.id).catch((cause) => toast(userError(cause), { type: "error" }));
    nav.go(
      row.group_id ? `/app/g/${row.group_id}` : `/app/${row.agent_id}?thread=${row.thread_id}`,
    );
  };
  const list = rows.data ?? [];
  return (
    <div className="domain-page">
      <div className="group" data-testid="attention-view">
        {rows.error != null ? (
          <p className="pad muted small">{userError(rows.error)}</p>
        ) : list.length ? (
          list.map((row) => (
            <button
              key={row.id}
              type="button"
              className="row"
              data-attention-id={row.id}
              data-attention-kind={row.kind}
              onClick={() => open(row)}
            >
              <span className="row-icon">
                <Icon name="bell" />
              </span>
              <span className="body">
                <strong>{title(row)}</strong>
                {row.summary ? (
                  <small dir="auto" data-testid="attention-summary">
                    {row.summary}
                  </small>
                ) : null}
                <small>
                  <bdi>{agentName(row.agent_id)}</bdi>
                  {row.symbol ? (
                    <>
                      {" · "}
                      <bdi>{row.symbol}</bdi>
                    </>
                  ) : null}
                </small>
              </span>
            </button>
          ))
        ) : (
          <p className="pad muted small">
            <Trans>Nothing needs you right now.</Trans>
          </p>
        )}
      </div>
    </div>
  );
}
