// Modified for Lonora; source attribution in THIRD_PARTY_NOTICES.md. Apache-2.0.
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { AgentAvatar } from "@lonora/ui-web";
import { useState } from "react";
import type { Agent } from "../../lib/api";
import { userError } from "../../lib/user_error";

const colors = ["#ee8555", "#818cf8", "#4fb8a7", "#e2ba58", "#ce77ae", "#8a9eae"];
export function AgentCreatePanel({
  create,
  onCreated,
}: {
  create: (name: string, avatar: string, color: string) => Promise<Agent>;
  onCreated: (agent: Agent) => void;
}) {
  const [name, setName] = useState("");
  const [color, setColor] = useState(colors[0]);
  const [avatar, setAvatar] = useState("orb");
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
          onCreated(await create(name.trim(), avatar, color));
        } catch (failure) {
          setError(failure);
        } finally {
          setBusy(false);
        }
      }}
    >
      <div className="tpl-profile-preview">
        <AgentAvatar name={name || "L"} color={color} shape={avatar} />
      </div>
      <h2>
        <Trans>A new teammate</Trans>
      </h2>
      <p className="muted">
        <Trans>Give your persistent agent an identity. Add instructions after creating it.</Trans>
      </p>
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
        </select>
      </label>
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
      {error != null && <p role="alert">{userError(error)}</p>}
      <button className="primary" type="submit" disabled={!name.trim() || busy}>
        <Trans>Create agent</Trans>
      </button>
    </form>
  );
}
