import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { AvatarStateId } from "@lonora/core";
import { GroupAvatar, Icon } from "@lonora/ui-web";
import { AgentAvatar } from "../components/ai/AgentAvatar";
import { PersonalAgentBadge } from "../components/ai/PersonalAgentBadge";
import { CallPill } from "../components/call/CallPill";
import { SafetyPill } from "../components/trading/SafetyPill";
import type { Agent, Resource } from "../lib/api";
import type { NetPhase } from "./NetworkStrip";

/* The conversation header: back · avatar · name and presence · call · menu. Phase 3 owns the
   conversation (typing, status line, alert capsule); the shell places the header and its actions. */
export function ChatHeader({
  agent,
  group,
  memberAgents,
  agents,
  working,
  avatarState,
  net,
  voiceActive,
  onBack,
  onInfo,
  onCall,
  onMenu,
}: {
  agent?: Agent;
  group?: Resource;
  memberAgents: Agent[];
  agents: Agent[];
  working: boolean;
  avatarState?: AvatarStateId;
  net: NetPhase;
  voiceActive: boolean;
  onBack: () => void;
  onInfo: () => void;
  onCall: () => void;
  onMenu: () => void;
}) {
  const name = group ? String(group.payload.name) : (agent?.name ?? "Lonora");
  const infoLabel = group ? t`Group info` : t`Agent info`;
  const presence =
    net === "off" ? (
      <Trans>Waiting for the network…</Trans>
    ) : net === "connecting" ? (
      <Trans>Connecting…</Trans>
    ) : group ? (
      memberAgents.map((member) => member.name).join("، ")
    ) : agent?.paused ? (
      <Trans>Paused</Trans>
    ) : (
      <Trans>Active</Trans>
    );
  return (
    <header className="chat-head">
      <button type="button" className="icon chat-back" aria-label={t`Back`} onClick={onBack}>
        <Icon name="back" />
      </button>
      <button type="button" className="head-avatar" aria-label={infoLabel} onClick={onInfo}>
        {group ? (
          <span className="group-av">
            <GroupAvatar members={memberAgents} />
          </span>
        ) : agent ? (
          <AgentAvatar agent={agent} working={working} state={avatarState} />
        ) : null}
      </button>
      <div className="chat-title">
        <button type="button" className="chat-name" onClick={onInfo} dir="auto">
          {name}
          <PersonalAgentBadge agent={agent} />
        </button>
        <span className="presence">{presence}</span>
      </div>
      {agent && <SafetyPill agentId={agent.id} agents={agents} />}
      <CallPill />
      {agent && (
        <button
          type="button"
          className="icon"
          aria-label={voiceActive ? t`Open active call` : t`Voice call`}
          title={voiceActive ? t`Open active call` : t`Voice call`}
          disabled={Boolean(agent.paused && !voiceActive)}
          onClick={onCall}
        >
          <Icon name="phone" />
        </button>
      )}
      {/* The menu is built from the loaded agent or group (its Goals row, its info page): until
          they arrive after a reload it would open without them and keep that body. */}
      <button
        type="button"
        className="icon"
        aria-label={t`Chat menu`}
        disabled={!agent && !group}
        onClick={onMenu}
      >
        <Icon name="more" />
      </button>
    </header>
  );
}
