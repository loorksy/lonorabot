import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import type { Capability, Model, Routing, Selection } from "../../lib/api";
import { providers, readModels } from "../../lib/model_catalog";
import { capabilities, readRouting, saveRouting } from "../../lib/model_routing";
import { userError } from "../../lib/user_error";
import { useToast } from "../Toast";
import { providerName } from "./ConnectionPages";
import { NavRow, Note, useLoad } from "./ui";

const capabilityLabel = (cap: Capability) =>
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
const VOICE: Capability[] = ["realtime_voice", "stt", "tts"];
const key = (item: Selection) => `${item.provider}:${item.model}`;
const modelKey = (model: Model) => `${model.provider}:${model.id}`;
const modelName = (model: Model) => `${providerName(model.provider)} · ${model.name}`;

/* «النماذج» (route `models`, under التكاملات › الذكاء الاصطناعي): the global routing. Keys are
   added on the provider form; only the owner assigns an agent's model (Q20 a). */
export function ModelsPage() {
  const load = useLoad(
    () => Promise.all([readRouting(), Promise.all(providers.map(readModels))]),
    [],
  );
  if (!load.value) return load.error != null ? <Note>{userError(load.error)}</Note> : null;
  const [routing, catalogs] = load.value;
  const models = catalogs.flat();
  if (!models.length)
    return (
      <>
        <Note>
          <Trans>Models appear here after you add a model provider.</Trans>
        </Note>
        <div className="group">
          <NavRow icon="cpu" label={t`Model providers`} to="/app/providers" />
        </div>
      </>
    );
  return (
    <RoutingForm
      key={JSON.stringify(routing)}
      initial={routing}
      models={models}
      onSaved={load.reload}
    />
  );
}

function ModelField({
  label,
  value,
  models,
  cap,
  onChange,
}: {
  label: string;
  value: Selection | null | undefined;
  models: Model[];
  cap?: Capability;
  onChange: (value: Selection | undefined) => void;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <select
        value={value ? key(value) : ""}
        onChange={(event) => {
          const model = models.find((m) => modelKey(m) === event.target.value);
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
            <option key={modelKey(m)} value={modelKey(m)}>
              {modelName(m)}
            </option>
          ))}
      </select>
    </label>
  );
}

function RoutingForm({
  initial,
  models,
  onSaved,
}: {
  initial: Routing;
  models: Model[];
  onSaved: () => void;
}) {
  const toast = useToast();
  const [policy, setPolicy] = useState(initial);
  const route = (cap: Capability) => (
    <ModelField
      key={cap}
      label={capabilityLabel(cap)}
      value={policy.routes[cap]}
      models={models}
      cap={cap}
      onChange={(value) => {
        const routes = { ...policy.routes };
        if (value) routes[cap] = value;
        else delete routes[cap];
        setPolicy({ ...policy, routes });
      }}
    />
  );
  return (
    <form
      noValidate
      onSubmit={async (event) => {
        event.preventDefault();
        try {
          await saveRouting(policy);
          toast(t`Saved`, { type: "success" });
          onSaved();
        } catch (error) {
          toast(userError(error), { type: "error" });
        }
      }}
    >
      <h3>
        <Trans>Global routing</Trans>
      </h3>
      <label className="field">
        <span>
          <Trans>Mode</Trans>
        </span>
        <select
          value={policy.mode}
          onChange={(event) => {
            const mode = event.target.value === "custom" ? "custom" : "unified";
            setPolicy({
              ...policy,
              mode,
              routes:
                mode === "unified"
                  ? Object.fromEntries(
                      Object.entries(policy.routes).filter(([cap]) =>
                        VOICE.includes(cap as Capability),
                      ),
                    )
                  : policy.routes,
            });
          }}
        >
          <option value="unified">{t`One model for text work`}</option>
          <option value="custom">{t`Route by capability`}</option>
        </select>
      </label>
      {policy.mode === "unified" ? (
        <>
          <ModelField
            label={t`Unified model`}
            value={policy.unified}
            models={models}
            onChange={(value) => setPolicy({ ...policy, unified: value ?? null })}
          />
          {VOICE.map(route)}
        </>
      ) : (
        capabilities.map(route)
      )}
      <Note>
        <Trans>
          These settings apply to every agent and routine. Voice routes require models that support
          audio.
        </Trans>
      </Note>
      <div className="actions">
        <button type="submit" className="btn primary">
          <Trans>Save global routing</Trans>
        </button>
      </div>
    </form>
  );
}
