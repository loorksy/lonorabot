// Modified for Lonora; source attribution in THIRD_PARTY_NOTICES.md. Apache-2.0.
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { AgentTemplate } from "@lonora/contracts";
import { DEFAULT_AVATAR_COLOR } from "@lonora/core";
import { Icon, type IconName } from "@lonora/ui-web";
import { useState } from "react";
import { AvatarStudio } from "../../components/ai/AvatarStudio";
import { type BrokerPair, BrokerPairPicker } from "../../components/trading/BrokerPairPicker";
import { type Agent, api } from "../../lib/api";
import { userError } from "../../lib/user_error";

type Template = Exclude<AgentTemplate, "supervisor">;

/* «وكيل جديد» (owner decision Q9): step 1 is the reference's three templates (agentTypePage);
   step 2 names the agent and its role (and the pair for a trading agent). The agent is created
   through POST /api/agents/create, the same input and service as the agent_create tool, so the
   template is persisted and the ladder starts where the template says. */
export function AgentCreatePanel({ onCreated }: { onCreated: (agent: Agent) => void }) {
  const [template, setTemplate] = useState<Template>("general");
  const [step, setStep] = useState<"template" | "details">("template");
  const [pair, setPair] = useState<BrokerPair>({ trading_account_id: "", trading_symbol: "" });
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [color, setColor] = useState(DEFAULT_AVATAR_COLOR);
  const [avatar, setAvatar] = useState("face-smile");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const templates: Record<Template, { icon: IconName; label: string; sub: string; code: string }> =
    {
      trading: {
        icon: "trend",
        label: t`Trading agent`,
        sub: t`Follows one pair and trades within your permissions`,
        code: t`Specialist role · Fixed market`,
      },
      general: {
        icon: "bot",
        label: t`General agent`,
        sub: t`Gets daily tasks done without a set pair`,
        code: t`General role · Flexible scope`,
      },
      research: {
        icon: "search",
        label: t`Research agent`,
        sub: t`Gathers information and summarises it without trading`,
        code: t`Specialist role · Flexible scope`,
      },
    };
  if (step === "template")
    return (
      <>
        <p className="muted">
          <Trans>Pick a template; the agent's type follows from its role and scope.</Trans>
        </p>
        <div className="group" role="radiogroup" aria-label={t`Agent template`}>
          {(Object.keys(templates) as Template[]).map((key) => (
            <label key={key} className="check tpl-row">
              <Icon name={templates[key].icon} />
              <span>
                <strong>{templates[key].label}</strong>
                <small className="tpl-sub">{templates[key].sub}</small>
                <small className="tpl-code">{templates[key].code}</small>
              </span>
              <input
                type="radio"
                name="agent-template"
                value={key}
                checked={template === key}
                onChange={() => setTemplate(key)}
              />
            </label>
          ))}
        </div>
        <button type="button" className="btn full primary" onClick={() => setStep("details")}>
          <Trans>Next</Trans>
        </button>
      </>
    );
  const trading = template === "trading";
  return (
    <form
      noValidate
      onSubmit={async (event) => {
        event.preventDefault();
        if (busy) return;
        setBusy(true);
        setError(undefined);
        try {
          const agent = await api.post<Agent>("/agents/create", {
            template,
            name: name.trim(),
            responsibility: role.trim(),
            ...(trading
              ? { market: pair.trading_symbol, account_id: pair.trading_account_id }
              : {}),
          });
          // The appearance is the agent's own setting, saved on it right after.
          if (avatar !== agent.avatar || color !== agent.color)
            await api.patch(`/agents/${agent.id}`, { avatar, color });
          onCreated(agent);
        } catch (failure) {
          setError(failure);
          setBusy(false);
        }
      }}
    >
      <div className="hero legacy-surface">
        <AvatarStudio
          name={name}
          avatar={avatar}
          color={color}
          onChange={(face, value) => {
            setAvatar(face);
            setColor(value);
          }}
        />
      </div>
      <label className="field">
        <span>
          <Trans>Agent name</Trans>
        </span>
        <input
          required
          maxLength={60}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <label className="field">
        <span>
          <Trans>Description</Trans>
        </span>
        <input
          required
          maxLength={180}
          value={role}
          onChange={(event) => setRole(event.target.value)}
        />
      </label>
      <div className="group">
        <div className="row">
          <span className="body">
            <Trans>Type</Trans>
          </span>
          <span className="value">{templates[template].label}</span>
        </div>
      </div>
      {trading && (
        <div className="legacy-surface">
          <BrokerPairPicker value={pair} onChange={setPair} />
        </div>
      )}
      <p className="note">
        {trading
          ? t`It starts at «Ask me»: every order is shown to you before it is sent. The level is changed from its chat.`
          : template === "research"
            ? t`It gathers information and summarises it, and needs no permissions.`
            : t`It starts at «No trading». The level is changed from its chat.`}
      </p>
      {error != null && <p role="alert">{userError(error)}</p>}
      <div className="actions">
        <button type="button" className="btn outline" onClick={() => setStep("template")}>
          <Trans>Back</Trans>
        </button>
        <button
          type="submit"
          className="btn primary"
          disabled={
            busy ||
            !name.trim() ||
            !role.trim() ||
            (trading && (!pair.trading_account_id || !pair.trading_symbol))
          }
        >
          <Trans>Create the agent</Trans>
        </button>
      </div>
    </form>
  );
}
