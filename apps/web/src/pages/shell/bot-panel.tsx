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
  create: (
    name: string,
    avatar: string,
    color: string,
    profile?: { title?: string; description?: string },
  ) => Promise<Agent>;
  onCreated: (agent: Agent) => void;
}) {
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
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
          onCreated(
            await create(name.trim(), avatar, color, {
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
      <details className="tpl-profile-appearance">
        <summary>
          <Trans>Appearance</Trans>
        </summary>
        <div className="tpl-profile-preview">
          <AgentAvatar name={name || "L"} color={color} shape={avatar} />
        </div>
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
      </details>
      {error != null && <p role="alert">{userError(error)}</p>}
      <button className="primary" type="submit" disabled={!name.trim() || busy}>
        <Trans>Create agent</Trans>
      </button>
    </form>
  );
}
