import type { AgentLiveState } from "@lonora/contracts";
import { useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { AppState, Pressable, Text, View } from "react-native";
import { api } from "../lib/api";
import { useSession } from "../lib/session";
import { Button, colors, ErrorNotice } from "./ui";

export function AgentLiveStatus({ agentId }: { agentId: string }) {
  const { t, errorText } = useSession();
  const [state, setState] = useState<AgentLiveState | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useFocusEffect(
    useCallback(() => {
      let live = true;
      let timer: ReturnType<typeof setTimeout>;
      const refresh = async () => {
        try {
          if (AppState.currentState === "active") {
            const next = await api.get<AgentLiveState>(
              `/agents/${encodeURIComponent(agentId)}/state`,
            );
            if (live) {
              setState(next);
              setError(null);
            }
          }
        } catch (caught) {
          if (live) setError(errorText(caught));
        }
        if (live) timer = setTimeout(() => void refresh(), 3000);
      };
      void refresh();
      return () => {
        live = false;
        clearTimeout(timer);
      };
    }, [agentId, errorText]),
  );
  if (!state) return null;
  return (
    <View style={{ paddingHorizontal: 16, paddingBottom: 6 }} testID="agent-live-state">
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded }}
        onPress={() => setExpanded(!expanded)}
      >
        <Text style={{ color: colors.secondary }}>{t(`live_${state.state}`)}</Text>
      </Pressable>
      {expanded && (
        <View style={{ gap: 8, paddingVertical: 8 }}>
          <ErrorNotice text={error} />
          {state.pending_approval_count > 0 && (
            <Text style={{ color: colors.foreground }}>{t("live_action_required")}</Text>
          )}
          {state.watch_count > 0 && (
            <Text style={{ color: colors.foreground }}>
              {t("activeWatches")}: {state.watch_count}
            </Text>
          )}
          {state.tasks.map((task) => (
            <View key={task.id}>
              <Text style={{ color: colors.foreground }}>{task.title}</Text>
              {(["pause", "resume", "cancel"] as const).map(
                (action) =>
                  task[`can_${action}`] && (
                    <Button
                      key={action}
                      label={t(action)}
                      secondary
                      onPress={() => {
                        void api
                          .post("/tasks/control", {
                            task_id: task.id,
                            action,
                            expected_version: task.version,
                          })
                          .then(() =>
                            api.get<AgentLiveState>(`/agents/${encodeURIComponent(agentId)}/state`),
                          )
                          .then(setState)
                          .catch((caught) => setError(errorText(caught)));
                      }}
                    />
                  ),
              )}
            </View>
          ))}
          {state.health.map((item) => (
            <Text
              key={`${item.account_id}:${item.symbol ?? ""}:${item.reason_code ?? ""}`}
              style={{ color: colors.secondary }}
            >
              {t("live_degraded")} {item.symbol}
            </Text>
          ))}
        </View>
      )}
    </View>
  );
}
