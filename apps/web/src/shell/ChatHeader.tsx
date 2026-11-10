import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { AvatarStateId } from "@lonora/core";
import { GroupAvatar, Icon } from "@lonora/ui-web";
import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { AgentAvatar } from "../components/ai/AgentAvatar";
import { PersonalAgentBadge } from "../components/ai/PersonalAgentBadge";
import { CallPill } from "../components/call/CallPill";
import { useChatPrefs } from "../conversation/prefs";
import {
  SafetyCapsule,
  StatusAvatar,
  StatusLine,
  useAgentSheet,
} from "../conversation/sheets/AgentSheet";
import type { Agent, Resource } from "../lib/api";
import { useShellData } from "./data";
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
  const prefs = useChatPrefs();
  const data = useShellData();
  const sheet = useAgentSheet((id) =>
    window.dispatchEvent(new CustomEvent("lonora:jump", { detail: { id } })),
  );
  const threadId = group ? String(group.state?.thread_id ?? "") : "";
  const replying = group
    ? data.runs.find(
        (run) => run.thread_id === threadId && ["queued", "leased", "running"].includes(run.status),
      )
    : undefined;
  const typingName = replying ? memberAgents.find((m) => m.id === replying.agent_id)?.name : null;
  const trading = Boolean(agent && (agent.trading_account_id || agent.template === "trading"));
  const openSheet = () =>
    agent && (trading || prefs.agentStatus) && sheet(agent, trading, prefs.agentStatus);
  // The agent page's «التداول والأمان» row lands here with ?sheet=agent: open the sheet once
  // and drop the parameter so Back does not reopen it.
  const [params, setParams] = useSearchParams();
  const wanted = params.get("sheet") === "agent";
  // biome-ignore lint/correctness/useExhaustiveDependencies: opened once per landing.
  useEffect(() => {
    if (!wanted || !agent) return;
    openSheet();
    setParams(
      (old) => {
        const next = new URLSearchParams(old);
        next.delete("sheet");
        return next;
      },
      { replace: true },
    );
  }, [wanted, agent?.id]);
  const statusOn = Boolean(agent && prefs.agentStatus && !working && net === "on");
  const infoLabel = group ? t`Group info` : t`Agent info`;
  const presence =
    net === "off" ? (
      <Trans>Waiting for the network…</Trans>
    ) : net === "connecting" ? (
      <Trans>Connecting…</Trans>
    ) : group ? (
      typingName ? (
        <Trans>{typingName} is typing…</Trans>
      ) : (
        memberAgents.map((member) => member.name).join("، ")
      )
    ) : working ? (
      <Trans>Typing…</Trans>
    ) : agent?.paused ? (
      <Trans>Paused</Trans>
    ) : (
      <Trans>Active</Trans>
    );
  return (
    <>
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
            <StatusAvatar agent={agent}>
              <AgentAvatar agent={agent} working={working} state={avatarState} />
            </StatusAvatar>
          ) : null}
        </button>
        <div className="chat-title">
          <button type="button" className="chat-name" onClick={onInfo} dir="auto">
            {name}
            <PersonalAgentBadge agent={agent} />
          </button>
          {statusOn && agent ? (
            <StatusLine agent={agent} onOpen={openSheet} />
          ) : (
            <span className={`presence${working || typingName ? " typing" : ""}`}>{presence}</span>
          )}
        </div>
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
        <button type="button" className="icon" aria-label={t`Chat menu`} onClick={onMenu}>
          <Icon name="more" />
        </button>
      </header>
      {agent && trading && <SafetyCapsule agent={agent} onOpen={openSheet} />}
    </>
  );
}
