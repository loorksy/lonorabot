import { useLingui } from "@lingui/react";
import { Trans } from "@lingui/react/macro";
import type { Agent } from "@lonora/contracts";
import { ownerProfileLabel } from "@lonora/core";
import { useState } from "react";
import { KnowledgeSection } from "./KnowledgeSection";
import { OwnerProfileSection } from "./OwnerProfileSection";
import { ScratchpadSection } from "./ScratchpadSection";
import { SkillsSection } from "./SkillsSection";
import { AgentPicker } from "./shell/bot-picker";

export function Knowledge({ agents, initialAgent }: { agents: Agent[]; initialAgent: string }) {
  const [agent, setAgent] = useState(initialAgent || agents[0]?.id || "");
  const { i18n } = useLingui();
  const [tab, setTab] = useState<"profile" | "memory" | "skills" | "scratchpad">("profile");
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
          className={tab === "profile" ? "selected" : ""}
          onClick={() => setTab("profile")}
        >
          {ownerProfileLabel("title", i18n.locale)}
        </button>
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
      {tab === "profile" ? (
        // The owner profile is shared by every agent, whichever agent is selected.
        <OwnerProfileSection />
      ) : agent ? (
        tab === "memory" ? (
          <KnowledgeSection key={agent} agentId={agent} />
        ) : tab === "skills" ? (
          <SkillsSection key={agent} agentId={agent} />
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
