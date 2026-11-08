import { i18n } from "@lingui/core";
import type { AllowedModels, Model, Selection } from "@lonora/contracts";
import { agentModelText } from "@lonora/core";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { userError } from "../lib/user_error";

const key = (item: Selection) => `${item.provider}:${item.model}`;

/**
 * The models agents may choose on their own (W15-10): the global routes and backups
 * always, plus the owner's additions. Any other model is a one-tap card in the chat.
 */
export function AllowedModelsSettings({ models }: { models: Model[] }) {
  const text = agentModelText(i18n.locale);
  const [value, setValue] = useState<AllowedModels>();
  const [pick, setPick] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    void api.get<AllowedModels>("/settings/models/allowed").then(setValue).catch(setError);
  }, []);
  if (!value) return error != null ? <p role="alert">{userError(error)}</p> : null;
  const included = new Set([...value.routed, ...value.added].map(key));
  const name = (item: Selection) =>
    models.find((model) => key({ provider: model.provider, model: model.id }) === key(item))
      ?.name ?? item.model;
  const save = async (added: Selection[]) => {
    setBusy(true);
    setError(undefined);
    try {
      setValue(await api.put<AllowedModels>("/settings/models/allowed", { added }));
      setSaved(true);
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="card" aria-label={text.allowedTitle} data-allowed-models="">
      <h2>{text.allowedTitle}</h2>
      <p className="muted">{text.allowedHint}</p>
      <ul>
        {value.routed.map((item) => (
          <li key={key(item)}>
            <bdi>
              {item.provider} · {name(item)}
            </bdi>
          </li>
        ))}
        {value.added.map((item) => (
          <li key={key(item)}>
            <bdi>
              {item.provider} · {name(item)}
            </bdi>{" "}
            <button
              type="button"
              disabled={busy}
              onClick={() => void save(value.added.filter((other) => key(other) !== key(item)))}
            >
              {text.remove}
            </button>
          </li>
        ))}
      </ul>
      <label>
        {text.chooseModel}
        <select value={pick} onChange={(event) => setPick(event.target.value)}>
          <option value="">{text.chooseModel}</option>
          {models
            .filter((model) => !included.has(`${model.provider}:${model.id}`))
            .map((model) => (
              <option key={`${model.provider}:${model.id}`} value={`${model.provider}:${model.id}`}>
                {model.provider} · {model.name}
              </option>
            ))}
        </select>
      </label>
      <button
        type="button"
        disabled={busy || !pick}
        onClick={() => {
          const model = models.find((item) => `${item.provider}:${item.id}` === pick);
          if (!model) return;
          setPick("");
          void save([...value.added, { provider: model.provider, model: model.id }]);
        }}
      >
        {text.add}
      </button>
      {saved && <p role="status">{text.saved}</p>}
      {error != null && <p role="alert">{userError(error)}</p>}
    </section>
  );
}
