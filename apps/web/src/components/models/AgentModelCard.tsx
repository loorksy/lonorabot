import { i18n } from "@lingui/core";
import type { Agent, AgentModelChange, AgentModelSummary, Selection } from "@lonora/contracts";
import { agentModelLines, agentModelText, offersDefaultModel } from "@lonora/core";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";

const key = (item: Selection) => `${item.provider}:${item.model}`;

/**
 * One agent's model (W15-10): Automatic (Lonora chooses among your allowed models) or
 * Fixed (one model only you change), the model answering now and this agent's usage.
 * Choosing a model never grants authority and never repeats anything.
 */
export function AgentModelCard({ agent }: { agent: Agent }) {
  const { revision } = useClient();
  const locale = i18n.locale;
  const text = agentModelText(locale);
  const [summary, setSummary] = useState<AgentModelSummary>();
  const [mode, setMode] = useState<"automatic" | "fixed">("automatic");
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
      setMode(value.record.mode);
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
  const dirty =
    mode !== summary.record.mode ||
    (mode === "fixed" &&
      choice !== (summary.record.preference.primary ? key(summary.record.preference.primary) : ""));
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
    <fieldset
      className="lonora-agent-model"
      disabled={busy}
      data-agent-model-mode={summary.record.mode}
    >
      <legend>{text.title}</legend>
      {agentModelLines(summary, locale).map((line) => (
        <p key={line} dir="auto" className="muted">
          {line}
        </p>
      ))}
      <div className="lonora-agent-model-choice">
        <label className="check">
          <input
            type="radio"
            name={`model-mode-${agent.id}`}
            checked={mode === "automatic"}
            onChange={() => {
              setMode("automatic");
              setSaved(false);
            }}
          />
          {text.automatic}
        </label>
        <p className="muted" dir="auto">
          {text.automaticHint}
        </p>
        <label className="check">
          <input
            type="radio"
            name={`model-mode-${agent.id}`}
            checked={mode === "fixed"}
            disabled={!options.length}
            onChange={() => {
              setMode("fixed");
              setSaved(false);
            }}
          />
          {text.fixed}
        </label>
        <p className="muted" dir="auto">
          {options.length ? text.fixedHint : text.noModels}
        </p>
        {mode === "fixed" && (
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
          disabled={!dirty || (mode === "fixed" && !selected)}
          onClick={() =>
            void save(
              mode === "fixed" && selected
                ? { mode, primary: { provider: selected.provider, model: selected.model } }
                : { mode: "automatic" },
            )
          }
        >
          {text.save}
        </button>
        {offersDefaultModel(summary) && mode === "automatic" && (
          <button type="button" onClick={() => void save({ mode: "automatic" })}>
            {text.backToDefault}
          </button>
        )}
      </div>
      {saved && <p role="status">{text.saved}</p>}
      {error != null && <p role="alert">{userError(error)}</p>}
    </fieldset>
  );
}
