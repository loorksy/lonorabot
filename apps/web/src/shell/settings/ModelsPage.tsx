import { i18n } from "@lingui/core";
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { AllowedModels } from "@lonora/contracts";
import { agentModelText } from "@lonora/core";
import { Icon } from "@lonora/ui-web";
import { useState } from "react";
import { api, type Capability, type Model, type Routing, type Selection } from "../../lib/api";
import { providers, readModels } from "../../lib/model_catalog";
import { capabilities, readRouting, saveRouting } from "../../lib/model_routing";
import { userError } from "../../lib/user_error";
import { useToast } from "../Toast";
import { providerName } from "./ConnectionPages";
import { Note, useLoad } from "./ui";

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

/* «النماذج» (route `models`, under التكاملات › الذكاء الاصطناعي): the global routing and the models
   agents may choose on their own (W15-10). Keys are added on the provider form. */
export function ModelsPage() {
  const load = useLoad(
    () =>
      Promise.all([
        readRouting(),
        Promise.all(providers.map(readModels)),
        api.get<AllowedModels>("/settings/models/allowed"),
      ]),
    [],
  );
  if (!load.value) return load.error != null ? <Note>{userError(load.error)}</Note> : null;
  const [routing, catalogs, allowed] = load.value;
  const models = catalogs.flat();
  return (
    <>
      <RoutingForm
        key={JSON.stringify(routing)}
        initial={routing}
        models={models}
        onSaved={load.reload}
      />
      <AllowedList key={JSON.stringify(allowed)} initial={allowed} models={models} />
    </>
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

/** The models agents may choose on their own: the global routes and backups always, plus the
 * owner's additions. Any other model is a one-tap card in the chat. */
function AllowedList({ initial, models }: { initial: AllowedModels; models: Model[] }) {
  const text = agentModelText(i18n.locale);
  const toast = useToast();
  const [value, setValue] = useState(initial);
  const [pick, setPick] = useState("");
  const [busy, setBusy] = useState(false);
  const included = new Set([...value.routed, ...value.added].map(key));
  const name = (item: Selection) =>
    `${providerName(item.provider)} · ${models.find((m) => modelKey(m) === key(item))?.name ?? item.model}`;
  const save = async (added: Selection[]) => {
    setBusy(true);
    try {
      setValue(await api.put<AllowedModels>("/settings/models/allowed", { added }));
      toast(text.saved, { type: "success" });
    } catch (error) {
      toast(userError(error), { type: "error" });
    } finally {
      setBusy(false);
    }
  };
  return (
    <section aria-label={text.allowedTitle} data-allowed-models="">
      <h3>{text.allowedTitle}</h3>
      {included.size > 0 && (
        <div className="group">
          {value.routed.map((item) => (
            <div className="row" key={key(item)}>
              <Icon name="cpu" />
              <span className="body">
                <strong>
                  <bdi>{name(item)}</bdi>
                </strong>
              </span>
            </div>
          ))}
          {value.added.map((item) => (
            <div className="row" key={key(item)}>
              <Icon name="cpu" />
              <span className="body">
                <strong>
                  <bdi>{name(item)}</bdi>
                </strong>
              </span>
              <button
                type="button"
                className="icon"
                aria-label={t`Remove ${name(item)}`}
                disabled={busy}
                onClick={() => void save(value.added.filter((other) => key(other) !== key(item)))}
              >
                <Icon name="close" />
              </button>
            </div>
          ))}
        </div>
      )}
      <label className="field">
        <span>{text.chooseModel}</span>
        <select value={pick} onChange={(event) => setPick(event.target.value)}>
          <option value="">{text.chooseModel}</option>
          {models
            .filter((m) => !included.has(modelKey(m)))
            .map((m) => (
              <option key={modelKey(m)} value={modelKey(m)}>
                {modelName(m)}
              </option>
            ))}
        </select>
      </label>
      <button
        type="button"
        className="btn full outline"
        disabled={busy || !pick}
        onClick={() => {
          const model = models.find((m) => modelKey(m) === pick);
          if (!model) return;
          setPick("");
          void save([...value.added, { provider: model.provider, model: model.id }]);
        }}
      >
        {text.add}
      </button>
      <Note>{text.allowedHint}</Note>
    </section>
  );
}
