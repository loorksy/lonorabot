import type { Agent, AgentModelChange, AgentModelSummary } from "@lonora/contracts";
import { agentModelLines, agentModelText, offersDefaultModel } from "@lonora/core";
import { useCallback, useEffect, useState } from "react";
import { Text, View } from "react-native";
import { api } from "../lib/api";
import { useSession } from "../lib/session";
import { SettingsGroup, SettingsRow } from "./settings-group";
import { colors, ErrorNotice } from "./ui";

/**
 * One agent's model, the same choice as on the Web: the model answering now, the owner's
 * choice among the connected providers' models, and this agent's usage. Only the owner
 * assigns a model (here, or by naming one in chat). It never grants authority or repeats
 * anything.
 */
export function AgentModelSettings({ agent }: { agent: Agent }) {
  const { locale, rtl, errorText } = useSession();
  const text = agentModelText(locale);
  const [summary, setSummary] = useState<AgentModelSummary | null>(null);
  const [picking, setPicking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setSummary(await api.get<AgentModelSummary>(`/agents/${agent.id}/model/summary`));
  }, [agent.id]);
  useEffect(() => {
    void load().catch((failure) => setError(errorText(failure)));
  }, [load, errorText]);
  if (!summary) return error ? <ErrorNotice text={error} /> : null;
  const record = summary.record;
  const choose = async (body: AgentModelChange) => {
    setBusy(true);
    setError(null);
    try {
      await api.put(`/agents/${agent.id}/model`, {
        ...body,
        expected_revision: record.revision,
      });
      await load();
      setPicking(false);
    } catch (failure) {
      setError(errorText(failure));
    } finally {
      setBusy(false);
    }
  };
  const primary = record.preference.primary;
  return (
    <View style={{ gap: 8 }} testID="agent-model-settings">
      <SettingsGroup title={text.title}>
        {agentModelLines(summary, locale).map((line) => (
          <Text
            key={line}
            style={{
              color: colors.secondary,
              fontSize: 14,
              lineHeight: 20,
              paddingHorizontal: 16,
              paddingVertical: 4,
              writingDirection: "auto",
              textAlign: rtl ? "right" : "left",
            }}
          >
            {line}
          </Text>
        ))}
        {offersDefaultModel(summary) && (
          <SettingsRow
            testID="agent-model-default"
            title={text.backToDefault}
            disabled={busy}
            onPress={() => void choose({ primary: null })}
          />
        )}
        <SettingsRow
          testID="agent-model-choose"
          title={text.chooseModel}
          detail={summary.available.length ? text.ownerOnly : text.noModels}
          disabled={busy || !summary.available.length}
          onPress={() => setPicking((open) => !open)}
        />
        {picking &&
          summary.available.map((item) => (
            <SettingsRow
              key={`${item.provider}:${item.model}`}
              title={item.name}
              detail={item.provider}
              value={
                primary?.provider === item.provider && primary.model === item.model
                  ? "✓"
                  : undefined
              }
              disabled={busy}
              onPress={() =>
                void choose({ primary: { provider: item.provider, model: item.model } })
              }
            />
          ))}
      </SettingsGroup>
      <ErrorNotice text={error} />
    </View>
  );
}
