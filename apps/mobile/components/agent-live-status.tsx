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
          {(state.runtime_waits ?? []).map((wait) => (
            <Text key={wait.run_id} style={{ color: colors.secondary }}>
              {wait.kind === "read_retry" ? t("retryScheduled") : t("live_waiting")}
              {wait.retry_at ? ` · ${new Date(wait.retry_at).toLocaleTimeString()}` : ""}
            </Text>
          ))}
          {state.pending_approval_count > 0 && (
            <Text style={{ color: colors.foreground }}>{t("live_action_required")}</Text>
          )}
          {state.watch_count > 0 && (
            <Text style={{ color: colors.foreground }}>
              {t("activeWatches")}: {state.watch_count}
            </Text>
          )}
          {(state.pending_authorization_count ?? 0) > 0 && (
            <Text style={{ color: colors.foreground }}>{t("devicePending")}</Text>
          )}
          {(state.super_bot ?? []).map((grant) => (
            <View key={grant.request_id}>
              <Text style={{ color: colors.foreground }}>
                {t("superBot")} · {t(grant.mode)}
              </Text>
              <Text style={{ color: colors.foreground }}>{grant.title}</Text>
              {grant.execution_mode === "shadow" && (
                <Text style={{ color: colors.secondary }}>{t("shadowMode")}</Text>
              )}
              {grant.review_status === "failed" && (
                <Text style={{ color: colors.foreground }}>{t("live_action_required")}</Text>
              )}
              <Text style={{ color: colors.secondary }}>
                {grant.authorization_status === "pending"
                  ? t("devicePending")
                  : grant.authorization_status === "paused"
                    ? t("paused")
                    : t("active")}
                {" · "}
                {(
                  {
                    active: t("active"),
                    waiting: t("live_waiting"),
                    paused: t("paused"),
                    blocked: t("taskNeedsReview"),
                    completed: t("completed"),
                    cancelled: t("cancelled"),
                  } as Record<string, string>
                )[grant.goal_status] ?? t("live_action_required")}
              </Text>
            </View>
          ))}
          {state.tasks.map((task) => (
            <View key={task.id}>
              <Text style={{ color: colors.foreground }}>{task.title}</Text>
              {task.retry_at ? (
                <Text style={{ color: colors.secondary }}>
                  {t("retryScheduled")} · {new Date(task.retry_at).toLocaleTimeString()}
                </Text>
              ) : task.recovery === "reconcile" ? (
                <Text style={{ color: colors.secondary }}>{t("waitingReconciliation")}</Text>
              ) : task.status === "failed" ? (
                <Text style={{ color: colors.secondary }}>{t("taskNeedsReview")}</Text>
              ) : null}
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
              {item.reason_code === "broker_reconciliation_pending"
                ? t("brokerVerificationPending")
                : item.kind === "broker" || !item.symbol
                  ? t("brokerNeedsAttention")
                  : `${t("marketDataUnavailable")} ${item.symbol}`}
            </Text>
          ))}
        </View>
      )}
    </View>
  );
}
