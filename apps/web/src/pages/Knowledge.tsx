import { Trans } from "@lingui/react/macro";
import type { Agent } from "@lonora/contracts";
import { useState } from "react";
import { KnowledgeSection } from "./KnowledgeSection";
import { ScratchpadSection } from "./ScratchpadSection";
import { AgentPicker } from "./shell/bot-picker";

export function Knowledge({ agents, initialAgent }: { agents: Agent[]; initialAgent: string }) {
  const [agent, setAgent] = useState(initialAgent || agents[0]?.id || "");
  const [tab, setTab] = useState<"memory" | "skills" | "scratchpad">("memory");
  return (
    <section>
      <div className="page-header">
        <h1>
          <Trans>Knowledge</Trans>
        </h1>
        <AgentPicker agents={agents} value={agent} onChange={setAgent} />
      </div>
      <div className="tabs">
        <button
          type="button"
          className={tab === "memory" ? "selected" : ""}
          onClick={() => setTab("memory")}
        >
          <Trans>Long-term memory</Trans>
        </button>
        <button
          type="button"
          className={tab === "skills" ? "selected" : ""}
          onClick={() => setTab("skills")}
        >
          <Trans>Skills</Trans>
        </button>
        <button
          type="button"
          className={tab === "scratchpad" ? "selected" : ""}
          onClick={() => setTab("scratchpad")}
        >
          <Trans>Scratchpad</Trans>
        </button>
      </div>
      {agent ? (
        tab === "memory" ? (
          <KnowledgeSection key={agent} agentId={agent} />
        ) : (
          <ScratchpadSection key={`${agent}:${tab}`} agentId={agent} kind={tab} />
        )
      ) : (
        <p className="muted">
          <Trans>Choose an agent</Trans>
        </p>
      )}
    </section>
  );
}
