import { i18n } from "@lingui/core";
import type { Agent, AgentModelChange, AgentModelSummary } from "@lonora/contracts";
import { agentModelLines, agentModelText, offersDefaultModel } from "@lonora/core";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";

const key = (item: { provider: string; model: string }) => `${item.provider}:${item.model}`;

/**
 * One agent's model: the model answering now, the owner's choice among the connected
 * providers' models, and this agent's usage. Only the owner assigns a model (here, or by
 * naming one in chat). Choosing a model never grants authority and never repeats anything.
 */
export function AgentModelCard({ agent }: { agent: Agent }) {
  const { revision } = useClient();
  const locale = i18n.locale;
  const text = agentModelText(locale);
  const [summary, setSummary] = useState<AgentModelSummary>();
  const [choice, setChoice] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<unknown>();
  // The record revision the owner's unsaved choice started from: a background refresh
  // keeps that choice unless the record itself changed.
  const loaded = useRef<number | null>(null);
  const load = useCallback(async () => {
    const value = await api.get<AgentModelSummary>(`/agents/${agent.id}/model/summary`);
    setSummary(value);
    if (loaded.current !== value.record.revision) {
      loaded.current = value.record.revision;
      const primary = value.record.preference.primary;
      setChoice(primary ? key(primary) : "");
    }
  }, [agent.id]);
  useEffect(() => {
    void revision;
    void load().catch(setError);
  }, [load, revision]);
  if (!summary) return error != null ? <p role="alert">{userError(error)}</p> : null;
  const options = summary.available;
  const selected = options.find((item) => key(item) === choice);
  const primary = summary.record.preference.primary;
  const dirty = choice !== (primary ? key(primary) : "");
  const save = async (body: AgentModelChange) => {
    setBusy(true);
    setError(undefined);
    try {
      await api.put(`/agents/${agent.id}/model`, {
        ...body,
        expected_revision: summary.record.revision,
      });
      await load();
      setSaved(true);
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  };
  return (
    <fieldset className="lonora-agent-model" disabled={busy}>
      <legend>{text.title}</legend>
      {agentModelLines(summary, locale).map((line) => (
        <p key={line} dir="auto" className="muted">
          {line}
        </p>
      ))}
      <div className="lonora-agent-model-choice">
        <p className="muted" dir="auto">
          {options.length ? text.ownerOnly : text.noModels}
        </p>
        {options.length > 0 && (
          <label>
            {text.chooseModel}
            <select
              value={choice}
              onChange={(event) => {
                setChoice(event.target.value);
                setSaved(false);
              }}
            >
              <option value="">{text.chooseModel}</option>
              {options.map((item) => (
                <option key={key(item)} value={key(item)}>
                  {item.provider} · {item.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <button
          type="button"
          disabled={!dirty || !selected}
          onClick={() => {
            if (selected)
              void save({ primary: { provider: selected.provider, model: selected.model } });
          }}
        >
          {text.save}
        </button>
        {offersDefaultModel(summary) && (
          <button type="button" onClick={() => void save({ primary: null })}>
            {text.backToDefault}
          </button>
        )}
      </div>
      {saved && <p role="status">{text.saved}</p>}
      {error != null && <p role="alert">{userError(error)}</p>}
    </fieldset>
  );
}
