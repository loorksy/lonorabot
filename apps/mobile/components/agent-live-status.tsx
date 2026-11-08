import type { AgentLiveState } from "@lonora/contracts";
import { useState } from "react";
import { Pressable, Text, View } from "react-native";
import { api } from "../lib/api";
import { useSession } from "../lib/session";
import { NativeSymbol } from "./native-symbol";
import { Button, colors, ErrorNotice } from "./ui";

/** The thread's background-activity strip; the screen polls the live state once for it
 * and the header's safety pill (``useAgentLiveState``). */
export function AgentLiveStatus({
  state,
  error: readError,
  refresh,
}: {
  state: AgentLiveState | null;
  error: unknown;
  refresh: () => Promise<void>;
}) {
  const { t, errorText, rtl } = useSession();
  const [expanded, setExpanded] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  if (!state) return null;
  const error = actionError ?? (readError ? errorText(readError) : null);
  const attention = state.state === "degraded" || state.state === "action_required";
  const tint = attention
    ? colors.warning
    : state.state === "working"
      ? colors.foreground
      : colors.secondary;
  return (
    <View style={{ paddingHorizontal: 16, paddingBottom: 6 }} testID="agent-live-state">
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded }}
        onPress={() => setExpanded(!expanded)}
        style={({ pressed }) => ({
          minHeight: 44,
          paddingHorizontal: 11,
          paddingVertical: 7,
          borderRadius: 12,
          borderWidth: 1,
          borderColor: attention ? `${tint}44` : colors.border,
          backgroundColor: pressed ? colors.accent : colors.muted,
          flexDirection: rtl ? "row-reverse" : "row",
          alignItems: "center",
          alignSelf: rtl ? "flex-end" : "flex-start",
          gap: 8,
          maxWidth: "100%",
        })}
      >
        <View
          accessible={false}
          style={{ width: 5, height: 5, borderRadius: 3, backgroundColor: tint }}
        />
        <Text
          style={{ color: tint, fontSize: 12, flexShrink: 1, textAlign: rtl ? "right" : "left" }}
        >
          {t("backgroundActivity")} · {t(`live_${state.state}`)}
        </Text>
        <View style={{ transform: [{ rotate: expanded ? "90deg" : rtl ? "180deg" : "0deg" }] }}>
          <NativeSymbol name="chevron" size={11} color={tint} />
        </View>
      </Pressable>
      {expanded && (
        <View style={{ gap: 8, paddingVertical: 8 }}>
          <ErrorNotice text={error} />
          {(state.runtime_waits ?? []).map((wait) => (
            <Text key={wait.run_id} style={{ color: colors.secondary }}>
              {wait.kind === "read_retry"
                ? t("retryScheduled")
                : wait.kind === "model_retry"
                  ? t("modelRetryScheduled")
                  : t("live_waiting")}
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
          {(state.account_authorities ?? []).some((grant) => grant.review_status === "failed") && (
            <Text style={{ color: colors.foreground }}>{t("grantReviewFailed")}</Text>
          )}
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
                          .then(() => {
                            setActionError(null);
                            return refresh();
                          })
                          .catch((caught) => setActionError(errorText(caught)));
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
