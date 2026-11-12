// Modified for Lonora; source attribution in THIRD_PARTY_NOTICES.md. Apache-2.0.
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { AgentModelSummary, AgentTemplate } from "@lonora/contracts";
import { DEFAULT_AVATAR_COLOR } from "@lonora/core";
import { Icon, type IconName } from "@lonora/ui-web";
import { useState } from "react";
import { AgentAvatar } from "../../components/ai/AgentAvatar";
import { type BrokerPair, BrokerPairPicker } from "../../components/trading/BrokerPairPicker";
import { type Agent, api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useAvatarSheet } from "../../shell/agent/AvatarSheet";
import { useRead } from "../../shell/agent/shared";
import { useShellData } from "../../shell/data";
import "../../shell/agent/agent.css";

type Template = Exclude<AgentTemplate, "supervisor">;

/* «وكيل جديد» (owner decision Q9): step 1 is the reference's three templates (agentTypePage);
   step 2 names the agent and its role (and the pair for a trading agent). The agent is created
   through POST /api/agents/create, the same input and service as the agent_create tool, so the
   template is persisted and the ladder starts where the template says. «الإشراف على وكلاء
   آخرين» is a capability on any template: the agents it supervises go in `supervises`. */
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
  const [supervise, setSupervise] = useState(false);
  const [supervises, setSupervises] = useState<string[]>([]);
  const [model, setModel] = useState("");
  const data = useShellData();
  const openAvatar = useAvatarSheet();
  // The models the owner can pick are the connected providers', not the agent's: read them once
  // from the personal agent's summary (the same catalog every agent offers).
  const personal = data.agents.find((row) => row.role === "personal");
  const models = useRead<AgentModelSummary>(
    step === "details" && personal
      ? `/agents/${encodeURIComponent(personal.id)}/model/summary`
      : null,
  );
  const others = data.agents.filter((row) => row.role !== "delegated");
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
        <div className="group">
          <div className="row">
            <span className="row-icon">
              <Icon name="eye" />
            </span>
            <span className="body">
              <strong>
                <Trans>Supervise other agents</Trans>
              </strong>
              <small>
                <Trans>A capability added to any template, not a separate type</Trans>
              </small>
            </span>
            <button
              type="button"
              className="switch"
              role="switch"
              aria-checked={supervise}
              aria-label={t`Supervise other agents`}
              onClick={() => setSupervise((on) => !on)}
            />
          </div>
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
            ...(model ? { model: JSON.parse(model) } : {}),
            ...(supervise && supervises.length ? { supervises } : {}),
          });
          // The appearance is the agent's own setting, saved on it right after. The agent
          // exists either way: a failed save is not a failed creation (a retry would make a
          // second agent); the appearance stays editable in the agent's settings.
          if (avatar !== agent.avatar || color !== agent.color)
            await api.patch(`/agents/${agent.id}`, { avatar, color }).catch(() => undefined);
          onCreated(agent);
        } catch (failure) {
          setError(failure);
          setBusy(false);
        }
      }}
    >
      <div className="hero">
        <span className="edit-wrap">
          <AgentAvatar
            agent={{
              id: "new",
              name,
              avatar,
              color,
              instructions: "",
              paused: false,
              trading_mode: "ask",
              parent_id: null,
              created_at: "",
            }}
          />
          <button
            type="button"
            className="pencil"
            data-testid="avatar-studio-trigger"
            aria-label={t`Edit avatar`}
            onClick={() =>
              openAvatar(null, {
                name,
                look: { avatar, color },
                onPick: (look) => {
                  setAvatar(look.avatar);
                  setColor(look.color);
                },
              })
            }
          >
            <Icon name="edit" />
          </button>
        </span>
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
      <label className="field">
        <span>
          <Trans>Model</Trans>
        </span>
        <select name="model" value={model} onChange={(event) => setModel(event.target.value)}>
          <option value="">{t({ message: "Lonora's model", context: "model" })}</option>
          {(models.value?.available ?? []).map((item) => (
            <option
              key={`${item.provider}:${item.model}`}
              value={JSON.stringify({ provider: item.provider, model: item.model })}
            >
              {item.name}
            </option>
          ))}
        </select>
      </label>
      {supervise && others.length > 0 && (
        <>
          <h3>
            <Trans>Agents it supervises</Trans>
          </h3>
          {others.map((row) => (
            <label className="check" key={row.id}>
              <span>
                <bdi>{row.name}</bdi>
              </span>
              <input
                type="checkbox"
                className="switch"
                role="switch"
                checked={supervises.includes(row.id)}
                aria-checked={supervises.includes(row.id)}
                disabled={!supervises.includes(row.id) && supervises.length >= 10}
                onChange={(event) =>
                  setSupervises((old) =>
                    event.target.checked ? [...old, row.id] : old.filter((id) => id !== row.id),
                  )
                }
              />
            </label>
          ))}
        </>
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
