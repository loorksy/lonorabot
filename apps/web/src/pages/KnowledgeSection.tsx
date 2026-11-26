import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";
import { MemoryRevisions } from "./MemoryRevisions";

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
          <Trans>
            This agent's own knowledge and working notes, kept apart from conversation history. What
            agents know about you is in About you.
          </Trans>
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
      <MemoryRevisions
        url={`/agents/${encodeURIComponent(agentId)}/memory/revisions`}
        revision={revision}
        version={() => memory?.version}
        onRestored={() => {
          dirty.current = false;
          refresh();
        }}
      />
      <SemanticKnowledge agentId={agentId} />
    </>
  );
}

// OpenAI's embedding models (lonora_memory.semantic posts to /v1/embeddings), which
// Lonora's list of chat models (VISION 12.4) does not hold.
const EMBEDDING_MODELS = ["text-embedding-3-small", "text-embedding-3-large"];

function SemanticKnowledge({ agentId }: { agentId: string }) {
  const [configuration, setConfiguration] = useState<{ enabled: boolean; model: string | null }>({
    enabled: false,
    model: null,
  });
  const [note, setNote] = useState("");
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    void api.get<typeof configuration>("/memory/semantic/config").then(setConfiguration, setError);
  }, []);
  // A saved model stays selectable.
  const models = [
    ...new Set([...EMBEDDING_MODELS, ...(configuration.model ? [configuration.model] : [])]),
  ];
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
            role="switch"
            data-lonora-switch="true"
            aria-checked={configuration.enabled}
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
              <Trans>Choose a model</Trans>
            </option>
            {models.map((model) => (
              <option key={model} value={model}>
                {model}
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
