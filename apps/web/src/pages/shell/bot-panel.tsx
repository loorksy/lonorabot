// Modified for Lonora; source attribution in THIRD_PARTY_NOTICES.md. Apache-2.0.
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { AgentMarketMode } from "@lonora/core";
import { AgentAvatar } from "@lonora/ui-web";
import { useState } from "react";
import { AgentMarketPicker } from "../../components/trading/AgentMarketPicker";
import type { BrokerPair } from "../../components/trading/BrokerPairPicker";
import type { Agent } from "../../lib/api";
import { userError } from "../../lib/user_error";

const colors = ["#ee8555", "#818cf8", "#4fb8a7", "#e2ba58", "#ce77ae", "#8a9eae"];
export function AgentCreatePanel({
  create,
  onCreated,
}: {
  create: (
    name: string,
    avatar: string,
    color: string,
    profile?: {
      title?: string;
      description?: string;
      instructions?: string;
      scope_mode?: "flexible";
      trading_account_id?: string | null;
      trading_symbol?: string | null;
    },
  ) => Promise<Agent>;
  onCreated: (agent: Agent) => void;
}) {
  const [pair, setPair] = useState<BrokerPair>({ trading_account_id: "", trading_symbol: "" });
  const [mode, setMode] = useState<AgentMarketMode>("general");
  const [instructions, setInstructions] = useState("");
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [color, setColor] = useState(colors[0]);
  const avatar = "orb";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  return (
    <form
      className="tpl-profile-form"
      onSubmit={async (event) => {
        event.preventDefault();
        setBusy(true);
        setError(undefined);
        try {
          onCreated(
            await create(name.trim(), avatar, color, {
              scope_mode: "flexible",
              trading_account_id: mode === "market" ? pair.trading_account_id : null,
              trading_symbol: mode === "market" ? pair.trading_symbol : null,
              instructions: instructions.trim(),
              title: title.trim(),
              description: description.trim(),
            }),
          );
        } catch (failure) {
          setError(failure);
        } finally {
          setBusy(false);
        }
      }}
    >
      <label>
        <Trans>Name</Trans>
        <input
          required
          maxLength={80}
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={t`Agent name`}
        />
      </label>
      <label>
        <Trans>Title</Trans>
        <input
          maxLength={120}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder={t`Describe this agent's role`}
        />
      </label>
      <label>
        <Trans>Description</Trans>
        <textarea
          rows={3}
          maxLength={2000}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder={t`What this agent is for`}
        />
      </label>
      <label>
        <Trans>Instructions</Trans>
        <textarea
          value={instructions}
          maxLength={16000}
          rows={3}
          onChange={(e) => setInstructions(e.target.value)}
        />
      </label>
      <AgentMarketPicker mode={mode} pair={pair} onMode={setMode} onPair={setPair} />
      <details className="tpl-profile-appearance">
        <summary>
          <Trans>Appearance</Trans>
        </summary>
        <div className="tpl-profile-preview">
          <AgentAvatar name={name || "L"} color={color} shape={avatar} />
        </div>
        <fieldset className="tpl-colors">
          <legend>
            <Trans>Color</Trans>
          </legend>
          {colors.map((value) => (
            <button
              type="button"
              key={value}
              style={{ backgroundColor: value }}
              aria-label={`${t`Color`} ${value}`}
              aria-pressed={value === color}
              onClick={() => setColor(value)}
            />
          ))}
          <input
            type="color"
            aria-label={t`Custom color`}
            value={color}
            onChange={(event) => setColor(event.target.value)}
          />
        </fieldset>
      </details>
      {error != null && <p role="alert">{userError(error)}</p>}
      <button
        className="primary"
        type="submit"
        disabled={
          !name.trim() ||
          (mode === "market" && (!pair.trading_account_id || !pair.trading_symbol)) ||
          busy
        }
      >
        <Trans>Create agent</Trans>
      </button>
    </form>
  );
}
