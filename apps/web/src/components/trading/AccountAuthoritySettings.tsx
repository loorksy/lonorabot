import { useLingui } from "@lingui/react";
import type { Agent, Thread } from "@lonora/contracts";
import { useEffect, useState } from "react";
import { api, isRequestCancelled } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { AgentPermissions } from "../permissions/AgentPermissions";
import { permissionLabels } from "../permissions/permission-labels";

/** Settings and the conversation share one authorization experience. Keeping this
 * entry lazy avoids duplicating signing state or loading it for closed profiles. */
export function AccountAuthoritySettings({ agent }: { agent: Agent }) {
  const { i18n } = useLingui();
  const text = permissionLabels[i18n.locale.startsWith("ar") ? "ar" : "en"];
  const [open, setOpen] = useState(false);
  const [threadId, setThreadId] = useState<string>();
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    if (!open) return;
    let active = true;
    setThreadId(undefined);
    setError(undefined);
    void api
      .get<Thread[]>(`/threads?agent_id=${encodeURIComponent(agent.id)}`)
      .then((threads) => {
        if (active)
          setThreadId(
            threads.find((thread) => thread.agent_id === agent.id && !thread.group_id)?.id ?? "",
          );
      })
      .catch((cause) => {
        if (active && !isRequestCancelled(cause)) setError(cause);
      });
    return () => {
      active = false;
    };
  }, [open, agent.id]);
  if (agent.role === "delegated") return null;
  return (
    <details
      className="tpl-profile-advanced"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>{text.title}</summary>
      {open &&
        (error != null ? (
          <p role="alert">{userError(error)}</p>
        ) : threadId === undefined ? (
          <p role="status">{text.loading}</p>
        ) : (
          <AgentPermissions key={agent.id} agent={agent} threadId={threadId} />
        ))}
    </details>
  );
}
