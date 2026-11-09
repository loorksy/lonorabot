import { t } from "@lingui/core/macro";
import {
  type ChatRow,
  isMuted,
  isPinned,
  rowCount,
  rowIsUnread,
  rowMarkedOnly,
} from "@lonora/core";
import { GroupAvatar, Icon, type IconName } from "@lonora/ui-web";
import { memo } from "react";
import { AgentAvatar } from "../../components/ai/AgentAvatar";
import type { Agent, InboxMessageKind } from "../../lib/api";
import type { OutgoingIntent } from "../../lib/outgoing-messages";

/** HH:mm with Latin digits, as the reference's fmtTime. */
export const clockTime = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });

const kindIcon: Partial<Record<InboxMessageKind, IconName>> = {
  voice: "mic",
  file: "file",
  image: "image",
  card: "shield",
};

/** A group's faces, the lead first (the reference's cluster; Lonora's avatar). */
export function groupMembers(row: ChatRow, agents: readonly Agent[]) {
  const ids = (row.group?.payload.member_ids ?? []) as string[];
  const lead = row.group?.payload.lead_agent_id;
  const ordered =
    typeof lead === "string" && ids.includes(lead)
      ? [lead, ...ids.filter((id) => id !== lead)]
      : ids;
  return ordered
    .map((id) => agents.find((agent) => agent.id === id))
    .filter((agent): agent is Agent => Boolean(agent));
}

export function RowAvatar({
  row,
  agents,
  working = false,
}: {
  row: ChatRow;
  agents: readonly Agent[];
  working?: boolean;
}) {
  if (row.agent) return <AgentAvatar agent={row.agent} working={working} />;
  const members = groupMembers(row, agents);
  return members.length ? (
    <span className="group-av">
      <GroupAvatar members={members} />
    </span>
  ) : (
    <span className="avatar icon-av">
      <Icon name="users" />
    </span>
  );
}

/* Line 2: what was said last, who said it, its kind and the owner's ticks (Q2: one grey
   tick = accepted by the server; two accent ticks = the agent's run started on it). A
   message still in this device's outbox is the latest the owner wrote: a clock while it
   waits for the network, a red mark when it failed. */
function Preview({
  row,
  agents,
  outgoing,
}: {
  row: ChatRow;
  agents: readonly Agent[];
  outgoing?: OutgoingIntent;
}) {
  if (outgoing) {
    const failed = outgoing.message.delivery === "failed";
    return (
      <>
        <span
          className={failed ? "fail" : "wait"}
          role="img"
          aria-label={failed ? t`Not sent` : t`Waiting for the network…`}
        >
          <Icon name={failed ? "alert" : "clock"} />
        </span>
        <span dir="auto">{t`You: ${outgoing.message.content}`}</span>
      </>
    );
  }
  const last = row.entry?.last_message;
  if (!last) return <span dir="auto">{row.subtitle || t`Start a chat`}</span>;
  const mine = last.role === "user";
  const speaker =
    !mine && row.kind === "group" && last.agent_id
      ? agents.find((agent) => agent.id === last.agent_id)?.name
      : undefined;
  const text = last.preview || last.content;
  const icon = kindIcon[last.kind];
  return (
    <>
      {mine &&
        (last.consumed ? (
          <span className="read" aria-hidden="true">
            <Icon name="checks" />
          </span>
        ) : (
          <span className="tick" aria-hidden="true">
            <Icon name="check" />
          </span>
        ))}
      {icon && <Icon name={icon} />}
      <span dir="auto">{mine ? t`You: ${text}` : speaker ? `${speaker}: ${text}` : text}</span>
    </>
  );
}

export const ThreadRow = memo(function ThreadRow({
  row,
  agents,
  current,
  selecting,
  picked,
  working,
  outgoing,
  onOpen,
}: {
  row: ChatRow;
  agents: readonly Agent[];
  /** The open conversation (desktop list). */
  current: boolean;
  selecting: boolean;
  picked: boolean;
  working: boolean;
  outgoing?: OutgoingIntent;
  onOpen: (row: ChatRow) => void;
}) {
  const unread = rowIsUnread(row);
  const muted = isMuted(row);
  const count = rowCount(row);
  const at = outgoing?.message.created_at ?? row.entry?.last_message?.created_at;
  const classes = [
    "row",
    "thread",
    unread ? "unread" : "",
    muted ? "muted" : "",
    current ? "selected" : "",
    picked ? "picked" : "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <button
      type="button"
      className={classes}
      data-key={row.key}
      data-inbox-agent-id={row.kind === "agent" ? row.id : undefined}
      data-inbox-group-id={row.kind === "group" ? row.id : undefined}
      aria-current={current ? "true" : undefined}
      aria-pressed={selecting ? picked : undefined}
      onClick={() => onOpen(row)}
    >
      <span className="av-wrap">
        <RowAvatar row={row} agents={agents} working={working} />
        <span className="pick" aria-hidden="true">
          <Icon name="check" />
        </span>
      </span>
      <span className="body">
        <span className="line1">
          <strong dir="auto">{row.name}</strong>
          {at && (
            <time className="ltr" dateTime={at}>
              {clockTime(at)}
            </time>
          )}
        </span>
        <span className="line2">
          <span className="pv">
            <Preview row={row} agents={agents} outgoing={outgoing} />
          </span>
          {row.paused && (
            <span className="paused">{t({ message: "Paused", context: "agent badge" })}</span>
          )}
          {muted && (
            <span className="t-ic" title={t`Muted`} role="img" aria-label={t`Muted`}>
              <Icon name="bellOff" />
            </span>
          )}
          {isPinned(row) && (
            <span className="t-ic" title={t`Pinned`} role="img" aria-label={t`Pinned`}>
              <Icon name="pin" />
            </span>
          )}
          {count > 0 ? (
            <span className={`count${muted ? " quiet" : ""}`}>
              <span aria-hidden="true">{count}</span>
              <span className="sr-only">{t`${count} unread`}</span>
            </span>
          ) : rowMarkedOnly(row) ? (
            <span
              className={`count dot${muted ? " quiet" : ""}`}
              role="img"
              aria-label={t({ message: "Unread", context: "marked" })}
            />
          ) : null}
        </span>
      </span>
    </button>
  );
});
