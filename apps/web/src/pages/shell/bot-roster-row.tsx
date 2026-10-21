import { t as superBotText } from "@lingui/core/macro";
// Adapted for Lonora from Tampletgrok Shell.tsx roster rows; Apache-2.0.

import { useLingui } from "@lingui/react/macro";
import { AgentAvatar } from "@lonora/ui-web";
import { Users } from "lucide-react";
import type { CSSProperties, MouseEventHandler, ReactNode } from "react";
import { PersonalAgentBadge } from "../../components/ai/PersonalAgentBadge";
import type { Agent, Resource } from "../../lib/api";

export function SidebarRow({
  agent,
  group,
  selected = false,
  working = false,
  subtitle,
  depth = 0,
  trailing,
  onClick,
  onContextMenu,
}: {
  agent?: Agent;
  group?: Resource;
  selected?: boolean;
  working?: boolean;
  subtitle?: string;
  depth?: number;
  trailing?: ReactNode;
  onClick: () => void;
  onContextMenu?: MouseEventHandler<HTMLButtonElement>;
}) {
  const { t } = useLingui();
  const name = agent?.name ?? String(group?.payload.name ?? "");
  const preview =
    subtitle ??
    (working ? t`Working` : agent?.paused ? t`Paused` : agent?.parent_id ? t`Child agent` : "");

  return (
    <button
      type="button"
      className="tpl-sidebar-row"
      data-selected={selected ? "true" : "false"}
      data-working={working ? "true" : "false"}
      data-roster-agent-id={agent?.id}
      data-roster-group-id={group?.id}
      data-roster-depth={depth || undefined}
      aria-current={selected ? "page" : undefined}
      onClick={onClick}
      onContextMenu={onContextMenu}
      style={{ "--tpl-roster-indent": `${Math.max(0, depth) * 14}px` } as CSSProperties}
    >
      {agent ? (
        <AgentAvatar
          name={agent.name}
          color={agent.color}
          shape={agent.avatar}
          superBot={agent.super_bot_active}
          superBotLabel={superBotText`Super Bot enabled`}
          working={working}
          className="tpl-roster-avatar"
        />
      ) : (
        <span className="tpl-group-avatar" aria-hidden="true">
          <Users size={20} strokeWidth={1.8} />
        </span>
      )}
      <span className="tpl-roster-copy">
        <span className="tpl-roster-name" dir="auto">
          {name}
          <PersonalAgentBadge agent={agent} />
        </span>
        {preview ? (
          <span className="tpl-roster-preview" dir="auto">
            {preview}
          </span>
        ) : null}
      </span>
      {trailing}
    </button>
  );
}
