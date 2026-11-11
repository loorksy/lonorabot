// Modified for Lonora; source attribution in THIRD_PARTY_NOTICES.md. Apache-2.0.

import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { type AgentMarketMode, agentMarketMode, marketScopeChange } from "@lonora/core";
import { useState } from "react";
import { AgentAvatar } from "../../components/ai/AgentAvatar";
import { PersonalAgentBadge } from "../../components/ai/PersonalAgentBadge";
import { SupervisionSettings } from "../../components/ai/SupervisionSettings";
import { AgentModelCard } from "../../components/models/AgentModelCard";
import { AccountAuthoritySettings } from "../../components/trading/AccountAuthoritySettings";
import { AgentMarketPicker } from "../../components/trading/AgentMarketPicker";
import { type Agent, api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import { useAvatarSheet } from "../../shell/agent/AvatarSheet";
export function AgentSettings({ agent, onClose }: { agent: Agent; onClose: () => void }) {
  const { refresh } = useClient();
  const [scopeBase] = useState(agent);
  const [mode, setMode] = useState<AgentMarketMode>(() => agentMarketMode(agent));
  const [pair, setPair] = useState({
    trading_account_id: agent.trading_account_id ?? "",
    trading_symbol: agent.trading_symbol ?? "",
  });
  const canEditScope = !agent.parent_id && agent.role !== "personal" && agent.role !== "delegated";
  const [name, setName] = useState(agent.name);
  const [title, setTitle] = useState(agent.title ?? "");
  const [description, setDescription] = useState(agent.description ?? "");
  const openAvatar = useAvatarSheet();
  const [instructions, setInstructions] = useState(agent.instructions);
  const [paused, setPaused] = useState(agent.paused);
  const [error, setError] = useState<unknown>();
  const [saving, setSaving] = useState(false);
  return (
    <form
      className="tpl-profile-form"
      onSubmit={async (event) => {
        event.preventDefault();
        if (saving) return;
        setSaving(true);
        setError(undefined);
        try {
          await api.patch(`/agents/${agent.id}`, {
            ...(canEditScope
              ? marketScopeChange(mode, pair, scopeBase.scope_revision ?? 0, scopeBase)
              : {}),
            name: name.trim(),
            title: title.trim(),
            description: description.trim(),
            instructions,
            paused,
          });
          refresh();
          onClose();
        } catch (failure) {
          setError(failure);
        } finally {
          setSaving(false);
        }
      }}
    >
      <button
        type="button"
        aria-label={t`Edit avatar`}
        disabled={saving}
        onClick={() => openAvatar(agent)}
      >
        <AgentAvatar agent={agent} />
      </button>
      <p dir="auto">
        {agent.name}
        <PersonalAgentBadge agent={agent} />
      </p>
      {agent.trading_symbol && (
        <p>
          <Trans>Trading pair</Trans>: <bdi>{agent.trading_symbol}</bdi>
        </p>
      )}
      {canEditScope && (
        <AgentMarketPicker
          mode={mode}
          pair={pair}
          onMode={setMode}
          onPair={setPair}
          allowFixed={agentMarketMode(agent) === "fixed"}
        />
      )}
      <AccountAuthoritySettings key={agent.id} agent={agent} />
      <AgentModelCard key={`model-${agent.id}`} agent={agent} />
      <SupervisionSettings key={`supervision-${agent.id}`} agent={agent} />
      <label>
        <Trans>Name</Trans>
        <input
          required
          maxLength={80}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <label>
        <Trans>Title</Trans>
        <input maxLength={120} value={title} onChange={(event) => setTitle(event.target.value)} />
      </label>
      <label>
        <Trans>Description</Trans>
        <textarea
          rows={3}
          maxLength={2000}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </label>
      <details className="tpl-profile-advanced">
        <summary>
          <Trans>Advanced</Trans>
        </summary>

        <label>
          <Trans>Instructions</Trans>
          <textarea
            rows={9}
            value={instructions}
            placeholder={t`What should this agent know about its work?`}
            onChange={(event) => setInstructions(event.target.value)}
          />
        </label>
        <label className="check">
          <input
            type="checkbox"
            role="switch"
            data-lonora-switch="true"
            aria-checked={paused}
            checked={paused}
            onChange={(event) => setPaused(event.target.checked)}
          />
          <Trans>Pause agent and scheduled work</Trans>
        </label>
        {agent.parent_id && (
          <p className="muted">
            <Trans>Persistent child agent</Trans>
          </p>
        )}
      </details>
      {error != null && <p role="alert">{userError(error)}</p>}
      <div className="actions">
        <button type="button" onClick={onClose} disabled={saving}>
          <Trans>Close</Trans>
        </button>
        <button
          type="submit"
          className="primary"
          disabled={
            !name.trim() ||
            saving ||
            (canEditScope &&
              mode === "market" &&
              (!pair.trading_account_id || !pair.trading_symbol))
          }
        >
          <Trans>Save</Trans>
        </button>
      </div>
    </form>
  );
}
