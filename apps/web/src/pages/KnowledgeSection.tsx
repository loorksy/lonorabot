import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { useEffect, useRef, useState } from "react";
import { api, type Model } from "../lib/api";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";

type Memory = { content: string; version: number };
export function KnowledgeSection({ agentId }: { agentId: string }) {
  const { revision, refresh } = useClient();
  const [memory, setMemory] = useState<Memory | null>(null);
  const [content, setContent] = useState("");
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const dirty = useRef(false);
  useEffect(() => {
    void revision;
    let live = true;
    void api
      .get<Memory>(`/agents/${agentId}/memory`)
      .then((value) => {
        if (live && !dirty.current) {
          setMemory(value);
          setContent(value.content);
          setError(undefined);
        }
      })
      .catch((cause) => {
        if (live) setError(cause);
      });
    return () => {
      live = false;
    };
  }, [agentId, revision]);
  return (
    <>
      {error != null && (
        <div role="alert">
          <p>{userError(error)}</p>
          <button
            type="button"
            onClick={() => {
              dirty.current = false;
              refresh();
            }}
          >
            <Trans>Reload</Trans>
          </button>
        </div>
      )}
      <form
        className="card"
        onSubmit={async (event) => {
          event.preventDefault();
          if (!memory || busy) return;
          setBusy(true);
          setError(undefined);
          setSaved(false);
          try {
            const value = await api.put<Memory>(`/agents/${agentId}/memory`, {
              content,
              version: memory.version,
            });
            setMemory(value);
            dirty.current = false;
            setSaved(true);
          } catch (cause) {
            setError(cause);
          } finally {
            setBusy(false);
          }
        }}
      >
        <p className="muted">
          <Trans>Stable facts and preferences kept separately from conversation history.</Trans>
        </p>
        <textarea
          aria-label={t`Long-term memory`}
          rows={18}
          value={content}
          disabled={!memory || busy}
          onChange={(event) => {
            dirty.current = true;
            setContent(event.target.value);
            setSaved(false);
          }}
        />
        <div className="actions">
          {saved && (
            <span role="status">
              <Trans>Saved</Trans>
            </span>
          )}
          <button type="submit" className="primary" disabled={!memory || busy}>
            <Trans>Save memory</Trans>
          </button>
        </div>
      </form>
      <SemanticKnowledge agentId={agentId} />
    </>
  );
}

function SemanticKnowledge({ agentId }: { agentId: string }) {
  const [configuration, setConfiguration] = useState<{ enabled: boolean; model: string | null }>({
    enabled: false,
    model: null,
  });
  const [models, setModels] = useState<Model[]>([]);
  const [note, setNote] = useState("");
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    void Promise.all([
      api.get<typeof configuration>("/memory/semantic/config"),
      api.get<Model[]>("/providers/openai/models"),
    ])
      .then(([config, catalog]) => {
        setConfiguration(config);
        setModels(catalog);
      })
      .catch(setError);
  }, []);
  return (
    <details className="card">
      <summary>
        <Trans>Semantic memory · optional</Trans>
      </summary>
      <p className="muted">
        <Trans>
          Search separate knowledge notes using real embeddings from a globally selected OpenAI
          model.
        </Trans>
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await api.put("/memory/semantic/config", configuration);
          } catch (err) {
            setError(err);
          }
        }}
      >
        <label className="check">
          <input
            type="checkbox"
            checked={configuration.enabled}
            onChange={(e) => setConfiguration({ ...configuration, enabled: e.target.checked })}
          />
          <Trans>Enable semantic retrieval</Trans>
        </label>
        <label>
          <Trans>Global embedding model</Trans>
          <select
            value={configuration.model ?? ""}
            onChange={(e) => setConfiguration({ ...configuration, model: e.target.value || null })}
          >
            <option value="">
              <Trans>Choose a discovered model</Trans>
            </option>
            {models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.name}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={configuration.enabled && !configuration.model}>
          <Trans>Save</Trans>
        </button>
      </form>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await api.post(`/agents/${agentId}/memory/semantic`, { text: note });
            setNote("");
          } catch (err) {
            setError(err);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          <Trans>Knowledge note</Trans>
          <textarea rows={4} required value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        <button type="submit" disabled={!configuration.enabled || !configuration.model || busy}>
          <Trans>Index note</Trans>
        </button>
      </form>
      {error != null && <p role="alert">{userError(error)}</p>}
    </details>
  );
}
