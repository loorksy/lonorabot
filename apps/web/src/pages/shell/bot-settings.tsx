// Modified for Lonora; source attribution in THIRD_PARTY_NOTICES.md. Apache-2.0.
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { AgentAvatar } from "@lonora/ui-web";
import { useState } from "react";
import { type Agent, api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
export function AgentSettings({ agent, onClose }: { agent: Agent; onClose: () => void }) {
  const { refresh } = useClient();
  const [name, setName] = useState(agent.name);
  const [avatar, setAvatar] = useState(agent.avatar);
  const [color, setColor] = useState(agent.color);
  const [instructions, setInstructions] = useState(agent.instructions);
  const [paused, setPaused] = useState(agent.paused);
  const [error, setError] = useState<unknown>();
  const [saving, setSaving] = useState(false);
  return (
    <form
      className="tpl-profile-form"
      onSubmit={async (event) => {
        event.preventDefault();
        setSaving(true);
        setError(undefined);
        try {
          await api.patch(`/agents/${agent.id}`, {
            name: name.trim(),
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
      <label>
        <Trans>Name</Trans>
        <input
          required
          maxLength={80}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <div className="tpl-profile-identity">
        <label>
          <Trans>Avatar</Trans>
          <select
            aria-label={t`Avatar`}
            value={avatar}
            onChange={(event) => setAvatar(event.target.value)}
          >
            <option value="orb">
              <Trans>Orb</Trans>
            </option>
            <option value="square">
              <Trans>Square</Trans>
            </option>
            <option value="diamond">
              <Trans>Diamond</Trans>
            </option>
            <option value="organic">
              <Trans>Organic</Trans>
            </option>
          </select>
        </label>
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
      <label>
        <Trans>Instructions</Trans>
        <textarea
          rows={9}
          value={instructions}
          placeholder={t`What should this agent know about its work?`}
          onChange={(event) => setInstructions(event.target.value)}
        />
      </label>
      <p className="muted">
        <Trans>Models, voice and trading connections are shared workspace settings.</Trans>
      </p>
      <label className="check">
        <input
          type="checkbox"
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
      {error != null && <p role="alert">{userError(error)}</p>}
      <div className="actions">
        <button type="button" onClick={onClose}>
          <Trans>Close</Trans>
        </button>
        <button type="submit" className="primary" disabled={!name.trim() || saving}>
          <Trans>Save</Trans>
        </button>
      </div>
    </form>
  );
}
