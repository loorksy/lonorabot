import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { useCallback, useEffect, useState } from "react";
import { api, type Model, type Provider, type Routing } from "../../lib/api";
import { discoverModels, providers, readModels } from "../../lib/model_catalog";
import { readRouting } from "../../lib/model_routing";
import { userError } from "../../lib/user_error";
import { ModelRoutingSettings } from "./ModelRoutingSettings";
export function ModelsSettings() {
  const [configured, setConfigured] = useState<{ id: Provider; configured: boolean }[]>([]);
  const [provider, setProvider] = useState<Provider>("openai");
  const [key, setKey] = useState("");
  const [models, setModels] = useState<Model[]>([]);
  const [policy, setPolicy] = useState<Routing>();
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    const [c, p, catalogs] = await Promise.all([
      api.get<{ id: Provider; configured: boolean }[]>("/providers"),
      readRouting(),
      Promise.all(providers.map(readModels)),
    ]);
    setConfigured(c);
    setPolicy(p);
    setModels(catalogs.flat());
  }, []);
  useEffect(() => {
    void load().catch(setError);
  }, [load]);
  return (
    <>
      <form
        className="card"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            if (key) {
              await api.put(`/providers/${provider}/credential`, { api_key: key });
              setKey("");
            }
            await discoverModels(provider);
            await load();
            setError(undefined);
          } catch (err) {
            setError(err);
          } finally {
            setBusy(false);
          }
        }}
      >
        <h2>
          <Trans>Providers and official catalog</Trans>
        </h2>
        <label>
          <Trans>Provider</Trans>
          <select
            aria-label={t`Provider`}
            value={provider}
            onChange={(e) => setProvider(e.target.value as Provider)}
          >
            {providers.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <p>
          {configured.find((p) => p.id === provider)?.configured ? (
            <Trans>Credential configured</Trans>
          ) : (
            <Trans>Add a provider credential</Trans>
          )}
        </p>
        <label>
          <Trans>API key</Trans>
          <input
            type="password"
            autoComplete="off"
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
        </label>
        <button
          type="submit"
          className="primary"
          disabled={busy || (!key && !configured.find((p) => p.id === provider)?.configured)}
        >
          <Trans>Save and discover models</Trans>
        </button>
        <p className="muted">
          <Trans>
            The catalog is read from the provider. Unknown capabilities are shown as unverified.
          </Trans>
        </p>
        {error != null && <p role="alert">{userError(error)}</p>}
      </form>
      {policy && (
        <ModelRoutingSettings
          key={JSON.stringify(policy)}
          initial={policy}
          models={models}
          onSaved={() => void load().catch(setError)}
        />
      )}
      <details className="card">
        <summary>
          <Trans>Discovered models</Trans> ({models.length})
        </summary>
        {models.map((m) => (
          <div className="row" key={`${m.provider}:${m.id}`}>
            <bdi>
              {m.provider} · {m.name}
            </bdi>
            <span className="badge">
              {m.verified ? (
                <Trans>Verified metadata</Trans>
              ) : (
                <Trans>Capabilities unverified</Trans>
              )}
            </span>
          </div>
        ))}
      </details>
    </>
  );
}
