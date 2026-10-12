import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import type { Capability, Model, Routing, Selection } from "../lib/api";
import { capabilities, saveRouting } from "../lib/model_routing";
import { userError } from "../lib/user_error";

const label = (cap: Capability) =>
  ({
    conversation: t`Conversation`,
    reasoning: t`Reasoning`,
    research: t`Research`,
    vision: t`Vision`,
    realtime_voice: t`Realtime voice`,
    stt: t`Speech recognition`,
    tts: t`Speech synthesis`,
    background: t`Background work`,
  })[cap];
function selector(
  value: Selection | null | undefined,
  models: Model[],
  onChange: (v: Selection | undefined) => void,
  cap?: Capability,
) {
  return (
    <select
      id={cap ?? "unified-model"}
      value={value ? `${value.provider}:${value.model}` : ""}
      onChange={(e) => {
        const model = models.find((m) => `${m.provider}:${m.id}` === e.target.value);
        onChange(model ? { provider: model.provider, model: model.id } : undefined);
      }}
    >
      <option value="">{t`Choose a discovered model`}</option>
      {models
        .filter(
          (m) =>
            cap !== "realtime_voice" ||
            (m.provider === "openai" && ["gpt-live-1", "gpt-live-1-mini"].includes(m.id)),
        )
        .filter(
          (m) => !cap || !m.verified || !m.capabilities.length || m.capabilities.includes(cap),
        )
        .map((m) => (
          <option key={`${m.provider}:${m.id}`} value={`${m.provider}:${m.id}`}>
            {m.provider} · {m.name}
          </option>
        ))}
    </select>
  );
}
export function ModelRoutingSettings({
  initial,
  models,
  onSaved,
}: {
  initial: Routing;
  models: Model[];
  onSaved: () => void;
}) {
  const [policy, setPolicy] = useState(initial);
  const [error, setError] = useState<unknown>();
  const [saved, setSaved] = useState(false);
  return (
    <form
      className="card"
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await saveRouting(policy);
          setSaved(true);
          onSaved();
        } catch (err) {
          setError(err);
        }
      }}
    >
      <h2>
        <Trans>Global routing</Trans>
      </h2>
      <p className="muted">
        <Trans>
          These settings apply to every agent and routine. Voice routes require models that support
          audio.
        </Trans>
      </p>
      <label>
        <Trans>Mode</Trans>
        <select
          value={policy.mode}
          onChange={(e) => {
            const mode = e.target.value === "custom" ? "custom" : "unified";
            setPolicy({
              ...policy,
              mode,
              routes:
                mode === "unified"
                  ? Object.fromEntries(
                      Object.entries(policy.routes).filter(([cap]) =>
                        ["stt", "tts", "realtime_voice"].includes(cap),
                      ),
                    )
                  : policy.routes,
            });
            setSaved(false);
          }}
        >
          <option value="unified">
            <Trans>One model for text work</Trans>
          </option>
          <option value="custom">
            <Trans>Route by capability</Trans>
          </option>
        </select>
      </label>
      {policy.mode === "unified" ? (
        <label htmlFor="unified-model">
          <Trans>Unified model</Trans>
          {selector(policy.unified, models, (value) =>
            setPolicy({ ...policy, unified: value ?? null }),
          )}
        </label>
      ) : (
        capabilities.map((cap) => (
          <label key={cap} htmlFor={cap}>
            {label(cap)}
            {selector(
              policy.routes[cap],
              models,
              (value) => {
                const routes = { ...policy.routes };
                if (value) routes[cap] = value;
                else delete routes[cap];
                setPolicy({ ...policy, routes });
              },
              cap,
            )}
          </label>
        ))
      )}
      {policy.mode === "unified" &&
        (["realtime_voice", "stt", "tts"] as Capability[]).map((cap) => (
          <label key={cap} htmlFor={cap}>
            {label(cap)}
            {selector(
              policy.routes[cap],
              models,
              (value) => {
                const routes = { ...policy.routes };
                if (value) routes[cap] = value;
                else delete routes[cap];
                setPolicy({ ...policy, routes });
              },
              cap,
            )}
          </label>
        ))}
      {error != null && <p role="alert">{userError(error)}</p>}
      {saved && (
        <p role="status">
          <Trans>Saved</Trans>
        </p>
      )}
      <button type="submit" className="primary">
        <Trans>Save global routing</Trans>
      </button>
    </form>
  );
}
