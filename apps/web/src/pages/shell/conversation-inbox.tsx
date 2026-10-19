import { t } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { GroupAvatar } from "@lonora/ui-web";
import { Plus, Search, X } from "lucide-react";
import { useState } from "react";
import { AgentAvatar } from "../../components/ai/AgentAvatar";
import { PersonalAgentBadge } from "../../components/ai/PersonalAgentBadge";
import type { Agent, Resource } from "../../lib/api";
import { userError } from "../../lib/user_error";

export type InboxEntry = {
  thread_id: string;
  agent_id: string | null;
  group_id: string | null;
  last_message: { content: string } | null;
  last_activity_at: string;
};

type Row = { kind: "agent"; value: Agent } | { kind: "group"; value: Resource };

/** A projection of existing conversations; opening home never creates a Thread. */
export function ConversationInbox({
  agents,
  groups,
  entries,
  loading,
  error,
  busyIds,
  onOpen,
  onCreate,
  onRetry,
}: {
  agents: Agent[];
  groups: Resource[];
  entries: InboxEntry[];
  loading: boolean;
  error: unknown;
  busyIds: Set<string>;
  onOpen: (path: string) => void;
  onCreate: () => void;
  onRetry: () => void;
}) {
  const { i18n } = useLingui();
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const byEntity = new Map(
    entries.map((entry) => [
      entry.agent_id ? `agent:${entry.agent_id}` : `group:${entry.group_id}`,
      entry,
    ]),
  );
  const needle = query.trim().toLocaleLowerCase();
  const rows: Row[] = [
    ...agents.map((value) => ({ kind: "agent" as const, value })),
    ...groups.map((value) => ({ kind: "group" as const, value })),
  ];
  const name = (row: Row) =>
    row.kind === "agent" ? row.value.name : String(row.value.payload.name);
  const time = (row: Row) =>
    byEntity.get(`${row.kind}:${row.value.id}`)?.last_activity_at ?? row.value.created_at;
  const visible = rows.filter((row) => name(row).toLocaleLowerCase().includes(needle));
  visible.sort((a, b) => {
    const personalA = a.kind === "agent" && a.value.role === "personal";
    const personalB = b.kind === "agent" && b.value.role === "personal";
    if (personalA !== personalB) return personalA ? -1 : 1;
    return time(b).localeCompare(time(a)) || a.value.id.localeCompare(b.value.id);
  });
  return (
    <section
      className="tpl-inbox lonora-scroll"
      aria-label={t`Conversations`}
      data-testid="conversation-inbox"
    >
      <div className="tpl-inbox-heading">
        <h1>
          <Trans>Conversations</Trans>
        </h1>
        <div className="tpl-toolbar">
          <button
            type="button"
            className="tpl-icon-button"
            aria-label={t`Search conversations`}
            aria-expanded={searching}
            onClick={() => {
              setSearching(!searching);
              setQuery("");
            }}
          >
            {searching ? <X /> : <Search />}
          </button>
          <button
            type="button"
            className="tpl-icon-button"
            aria-label={t`Create conversation`}
            onClick={onCreate}
          >
            <Plus />
          </button>
        </div>
      </div>
      {searching && (
        <input
          className="tpl-inbox-search"
          aria-label={t`Search conversations`}
          placeholder={t`Search conversations`}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      )}
      {error != null && (
        <div className="tpl-error-banner" role="alert">
          {userError(error)}
          <button type="button" onClick={onRetry}>
            <Trans>Retry</Trans>
          </button>
        </div>
      )}
      {loading && !rows.length && (
        <p role="status" className="tpl-roster-notice">
          <Trans>Loading conversations…</Trans>
        </p>
      )}
      <div className="tpl-inbox-list">
        {visible.map((row) => {
          const entry = byEntity.get(`${row.kind}:${row.value.id}`);
          const members =
            row.kind === "group"
              ? agents.filter((agent) =>
                  ((row.value.payload.member_ids ?? []) as string[]).includes(agent.id),
                )
              : [];
          const at = new Date(time(row));
          const preview =
            entry?.last_message?.content ||
            (row.kind === "agent"
              ? row.value.title || row.value.description || (row.value.paused ? t`Paused` : "")
              : members.map((agent) => agent.name).join(" · "));
          return (
            <button
              type="button"
              className="tpl-inbox-row"
              data-inbox-agent-id={row.kind === "agent" ? row.value.id : undefined}
              data-inbox-group-id={row.kind === "group" ? row.value.id : undefined}
              key={`${row.kind}:${row.value.id}`}
              onClick={() =>
                onOpen(
                  row.kind === "group"
                    ? `/app/g/${row.value.id}`
                    : `/app/${row.value.id}${entry ? `?thread=${encodeURIComponent(entry.thread_id)}` : ""}`,
                )
              }
            >
              <span className="tpl-inbox-avatar">
                {row.kind === "agent" ? (
                  <AgentAvatar agent={row.value} working={busyIds.has(row.value.id)} />
                ) : (
                  <GroupAvatar members={members} />
                )}
              </span>
              <span className="tpl-inbox-copy">
                <span className="tpl-inbox-title">
                  <strong dir="auto">{name(row)}</strong>
                  {row.kind === "agent" && <PersonalAgentBadge agent={row.value} />}
                  <time dateTime={at.toISOString()}>
                    {at.toDateString() === new Date().toDateString()
                      ? at.toLocaleTimeString(i18n.locale, { hour: "2-digit", minute: "2-digit" })
                      : at.toLocaleDateString(i18n.locale, { month: "short", day: "numeric" })}
                  </time>
                </span>
                <span className="tpl-inbox-preview" dir="auto">
                  {preview || t`Start a conversation`}
                </span>
              </span>
            </button>
          );
        })}
      </div>
      {!loading && !visible.length && (
        <div className="tpl-empty">
          <p>{needle ? t`No conversations match` : t`Your team starts here`}</p>
          {!needle && (
            <button type="button" className="primary" onClick={onCreate}>
              <Plus />
              <Trans>Create conversation</Trans>
            </button>
          )}
        </div>
      )}
    </section>
  );
}
