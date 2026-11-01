// Modified for Lonora; source attribution in THIRD_PARTY_NOTICES.md. Apache-2.0.

import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { type AgentMarketMode, agentMarketMode, marketScopeChange } from "@lonora/core";
import { AgentAvatar } from "@lonora/ui-web";
import { useEffect, useRef, useState } from "react";
import { PersonalAgentBadge } from "../../components/ai/PersonalAgentBadge";
import { AccountAuthoritySettings } from "../../components/trading/AccountAuthoritySettings";
import { AgentMarketPicker } from "../../components/trading/AgentMarketPicker";
import { ExecutionModeSettings } from "../../components/trading/ExecutionModeSettings";
import { type Agent, api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
export function AgentSettings({
  agent,
  onClose,
  onDelete,
}: {
  agent: Agent;
  onClose: () => void;
  onDelete: () => Promise<void>;
}) {
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
  // Existing shape values remain round-trippable; every bot now uses the candle avatar.
  const avatar = agent.avatar;
  const [color, setColor] = useState(agent.color);
  const [instructions, setInstructions] = useState(agent.instructions);
  const [paused, setPaused] = useState(agent.paused);
  const [error, setError] = useState<unknown>();
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const cancelDeleteRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (confirmDelete) cancelDeleteRef.current?.focus();
  }, [confirmDelete]);
  return (
    <form
      className="tpl-profile-form"
      onSubmit={async (event) => {
        event.preventDefault();
        if (saving || confirmDelete) return;
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
            avatar,
            color,
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
      <div className="tpl-profile-preview">
        <AgentAvatar name={name} shape={avatar} color={color} />
      </div>
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
      <ExecutionModeSettings agent={agent} />
      <AccountAuthoritySettings key={agent.id} agent={agent} />
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
        <details className="tpl-profile-appearance">
          <summary>
            <Trans>Appearance</Trans>
          </summary>
          <div className="tpl-profile-identity">
            <label>
              <Trans>Color</Trans>
              <input
                type="color"
                aria-label={t`Color`}
                value={color}
                onChange={(event) => setColor(event.target.value)}
              />
            </label>
          </div>
        </details>
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
            confirmDelete ||
            (canEditScope &&
              mode === "market" &&
              (!pair.trading_account_id || !pair.trading_symbol))
          }
        >
          <Trans>Save</Trans>
        </button>
      </div>
      {agent.role === "personal" ? (
        <p className="muted">
          <Trans>Your Personal Agent cannot be deleted.</Trans>
        </p>
      ) : (
        <section aria-label={t`Delete agent`}>
          {confirmDelete ? (
            <div
              role="alertdialog"
              aria-modal="false"
              aria-labelledby="agent-delete-title"
              aria-describedby="agent-delete-description"
            >
              <h3 id="agent-delete-title">
                <Trans>Delete agent permanently?</Trans>
              </h3>
              <p id="agent-delete-description">
                <Trans>Permanently delete {agent.name}? This cannot be undone.</Trans>
              </p>
              <div className="actions">
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => setConfirmDelete(false)}
                  ref={cancelDeleteRef}
                >
                  <Trans>Cancel</Trans>
                </button>
                <button
                  type="button"
                  className="danger"
                  disabled={saving}
                  onClick={async () => {
                    if (saving || agent.role === "personal") return;
                    setSaving(true);
                    setError(undefined);
                    try {
                      await onDelete();
                    } catch (failure) {
                      setError(failure);
                      setSaving(false);
                    }
                  }}
                >
                  <Trans>Delete permanently</Trans>
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              className="danger"
              disabled={saving}
              onClick={() => setConfirmDelete(true)}
            >
              <Trans>Delete agent</Trans>
            </button>
          )}
        </section>
      )}
    </form>
  );
}
