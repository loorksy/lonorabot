import type { Agent, PerformanceSummary, ShadowTradeSummary } from "@lonora/contracts";
import { useEffect, useState } from "react";
import { Text, View } from "react-native";
import { api } from "../lib/api";
import { useSession } from "../lib/session";
import { SettingsGroup, SettingsRow, SettingsSwitch } from "./settings-group";
import { colors, ErrorNotice } from "./ui";

export function ExecutionModeSettings({
  agent,
  onChange,
}: {
  agent: Agent;
  onChange: (agent: Agent) => void;
}) {
  const { t, errorText, rtl } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<PerformanceSummary | null>(null);
  const [trades, setTrades] = useState<ShadowTradeSummary[]>([]);
  const [expanded, setExpanded] = useState(false);
  const mode = agent.execution_mode ?? "live";
  useEffect(() => {
    let active = true;
    setSummary(null);
    setTrades([]);
    void api
      .get<PerformanceSummary>(`/agents/${agent.id}/performance?execution_mode=${mode}`)
      .then((value) => {
        if (active) setSummary(value);
      })
      .catch((failure) => {
        if (active) setError(errorText(failure));
      });
    void api
      .get<{ trades: ShadowTradeSummary[] }>(`/agents/${agent.id}/shadow-trades`)
      .then((value) => {
        if (active) setTrades(value.trades);
      })
      .catch((failure) => {
        if (active) setError(errorText(failure));
      });
    return () => {
      active = false;
    };
  }, [agent.id, mode, errorText]);
  return (
    <View style={{ gap: 8 }}>
      <SettingsGroup title={t("executionMode")} footer={t("executionModeHint")}>
        <SettingsSwitch
          label={t("shadowTrading")}
          value={mode === "shadow"}
          disabled={busy}
          onChange={async (enabled) => {
            setBusy(true);
            setError(null);
            try {
              const saved = await api.put<Agent>(`/agents/${agent.id}/execution-mode`, {
                execution_mode: enabled ? "shadow" : "live",
              });
              onChange({ ...agent, execution_mode: saved.execution_mode });
            } catch (failure) {
              setError(errorText(failure));
            } finally {
              setBusy(false);
            }
          }}
        />
        {summary && (
          <SettingsRow
            title={mode === "shadow" ? t("shadowObservations") : t("liveObservations")}
            value={String(summary.sample_count)}
            detail={
              summary.sample_state === "insufficient_data"
                ? t("performanceInsufficient")
                : undefined
            }
          />
        )}
        <SettingsRow
          title={t("shadowHistory")}
          value={String(trades.length)}
          onPress={() => setExpanded(!expanded)}
        />
      </SettingsGroup>
      {expanded && (
        <View style={{ gap: 10 }}>
          <Text style={{ color: colors.secondary, textAlign: rtl ? "right" : "left" }}>
            {t("shadowFillHint")}
          </Text>
          {trades.slice(0, 20).map((trade) => (
            <Text key={trade.id} style={{ color: colors.foreground, writingDirection: "ltr" }}>
              {trade.symbol} · {t("virtualTrade")} · {trade.state.entry_price ?? "—"} →{" "}
              {trade.state.exit_price ?? "—"}
            </Text>
          ))}
        </View>
      )}
      <ErrorNotice text={error} />
    </View>
  );
}
