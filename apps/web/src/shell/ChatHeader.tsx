import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { type AvatarStateId, showsTradingControl } from "@lonora/core";
import { GroupAvatar, Icon } from "@lonora/ui-web";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AgentAvatar } from "../components/ai/AgentAvatar";
import { PersonalAgentBadge } from "../components/ai/PersonalAgentBadge";
import { useChatPrefs } from "../conversation/prefs";
import {
  SafetyCapsule,
  StatusAvatar,
  StatusLine,
  useAgentSheet,
} from "../conversation/sheets/AgentSheet";
import { useVoice } from "../hooks/useVoice";
import type { Agent, Resource } from "../lib/api";
import { useRead } from "./agent/shared";
import { CallCapsule, useCallClock, useCallStarter } from "./call/CallPages";
import { useShellData } from "./data";
import type { NetPhase } from "./NetworkStrip";

/* The conversation header: back · avatar · name and presence · call · menu. Phase 3 owns the
   conversation (typing, status line, alert capsule); the shell places the header and its actions. */
export function ChatHeader({
  agent,
  group,
  memberAgents,
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
  onMenu: (anchor: HTMLElement) => void;
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
  // Lonora (the personal agent) trades too (Q19): its chat has the capsule and the sheet's
  // trading section like any trading agent's.
  const trading = Boolean(
    agent &&
      (agent.template === "trading" ||
        showsTradingControl({ role: agent.role, trading_account_id: agent.trading_account_id })),
  );
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
  const voice = useVoice();
  const starter = useCallStarter();
  const readiness = useRead<{ transport_configured: boolean }>(agent ? "/voice/status" : null);
  const unready = Boolean(readiness.value && !readiness.value.transport_configured);
  const onThisCall = Boolean(agent && voice.target?.agentId === agent.id);
  const clock = useCallClock(onThisCall ? voice.startedAt : null);
  const wasOnCall = useRef(false);
  const [callReturned, setCallReturned] = useState(false);
  useEffect(() => {
    if (wasOnCall.current && !onThisCall) setCallReturned(true);
    wasOnCall.current = onThisCall;
  }, [onThisCall]);
  const statusOn = Boolean(agent && prefs.agentStatus && !working && net === "on" && !onThisCall);
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
          {onThisCall ? (
            <span className={`presence oncall${voice.muted ? " muted" : ""}`}>
              {voice.muted ? <Trans>Muted</Trans> : <Trans>In a call</Trans>}
              {" · "}
              <span className="ltr" data-clock>
                {clock}
              </span>
            </span>
          ) : statusOn && agent ? (
            <StatusLine agent={agent} onOpen={openSheet} />
          ) : (
            <span className={`presence${working || typingName ? " typing" : ""}`}>{presence}</span>
          )}
        </div>
        {onThisCall ? (
          <CallCapsule />
        ) : (
          agent && (
            <button
              type="button"
              className={`icon${callReturned ? " call-back" : ""}`}
              aria-label={voiceActive ? t`Open active call` : t`Voice call`}
              title={voiceActive ? t`Open active call` : t`Voice call`}
              aria-disabled={unready ? true : undefined}
              disabled={Boolean(agent.paused && !voiceActive)}
              onClick={() => {
                if (unready) starter.notConfigured();
                else onCall();
              }}
            >
              <Icon name="phone" />
            </button>
          )
        )}
        <button
          type="button"
          className="icon"
          aria-label={t`Chat menu`}
          aria-haspopup="menu"
          aria-expanded="false"
          onClick={(event) => onMenu(event.currentTarget)}
        >
          <Icon name="more" />
        </button>
      </header>
      {agent && trading && <SafetyCapsule agent={agent} onOpen={openSheet} />}
    </>
  );
}
