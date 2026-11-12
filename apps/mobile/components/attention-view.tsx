// «يحتاج انتباهك» (mandate 11.7): what needs the owner, across all agents, from one
// server projection (GET /attention/view), the same list the web shows. A row opens its
// conversation, where the fixed card or the question stands; opening it decides nothing.

import type { Agent, AttentionViewKind, AttentionViewRow } from "@lonora/contracts";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { AppState, Text, View } from "react-native";
import { api } from "../lib/api";
import type { Label } from "../lib/i18n";
import { useSession } from "../lib/session";
import { textDirection } from "../lib/text-direction";
import { Button, colors, ErrorNotice } from "./ui";

const labels: Record<AttentionViewKind, Label> = {
  trade_approval: "attentionApproval",
  settle_operation: "attentionOperationUncertain",
  secret_request: "attentionSecretRequested",
  mandate_card: "attentionMandateProposed",
  broker_health: "attentionBrokerConnectionLost",
  owner_question: "attentionOwnerQuestion",
  task_review: "taskNeedsReview",
  agent_alert: "attentionAgentAlert",
};
// The three broker problems each say which one it is.
const brokerLabels: Record<string, Label> = {
  broker_token_rejected: "attentionBrokerTokenRejected",
  broker_account_undeployed: "attentionBrokerUndeployed",
  broker_connection_lost: "attentionBrokerConnectionLost",
};
const POLL_MS = 5000;

export function AttentionView({ agents }: { agents: Agent[] }) {
  const { t, errorText, rtl } = useSession();
  const router = useRouter();
  const [rows, setRows] = useState<AttentionViewRow[]>();
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(
    async (active: () => boolean) => {
      try {
        const value = await api.get<AttentionViewRow[]>("/attention/view");
        if (active()) {
          setRows(value);
          setError(null);
        }
      } catch (cause) {
        if (active()) setError(errorText(cause));
      }
    },
    [errorText],
  );
  useEffect(() => {
    let disposed = false;
    const active = () => !disposed;
    void load(active);
    const timer = setInterval(() => {
      if (AppState.currentState === "active") void load(active);
    }, POLL_MS);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [load]);
  const align = rtl ? "right" : "left";
  return (
    <View style={{ padding: 16, gap: 12 }} testID="attention-view">
      <ErrorNotice text={error} />
      {rows && rows.length === 0 && (
        <Text style={{ color: colors.secondary, textAlign: align }}>{t("attentionNothing")}</Text>
      )}
      {(rows ?? []).map((row) => (
        <View
          key={row.id}
          testID={`attention-row-${row.kind}`}
          style={{ backgroundColor: colors.muted, padding: 14, borderRadius: 16, gap: 8 }}
        >
          <Text style={{ color: colors.foreground, textAlign: align }}>
            {t((row.code && brokerLabels[row.code]) || labels[row.kind])}
          </Text>
          {row.summary ? (
            <Text
              testID="attention-summary"
              style={{
                color: colors.foreground,
                textAlign:
                  textDirection(row.summary, rtl ? "rtl" : "ltr") === "rtl" ? "right" : "left",
                writingDirection: textDirection(row.summary, rtl ? "rtl" : "ltr"),
              }}
            >
              {row.summary}
            </Text>
          ) : null}
          <Text style={{ color: colors.secondary, textAlign: align }}>
            {agents.find((agent) => agent.id === row.agent_id)?.name}
            {row.symbol ? (
              <>
                {" · "}
                <Text style={{ writingDirection: "ltr" }}>{row.symbol}</Text>
              </>
            ) : null}
          </Text>
          <Button
            secondary
            label={t("openConversation")}
            onPress={() => {
              // Opening an agent's alert reads it; a card or a question stays until answered.
              if (row.kind === "agent_alert")
                void api
                  .post("/attention/seen", { notification_id: row.id })
                  .catch((cause) => setError(errorText(cause)));
              router.push({
                pathname: row.group_id ? "/group-thread" : "/thread",
                params: row.group_id ? { groupId: row.group_id } : { id: row.thread_id },
              });
            }}
          />
        </View>
      ))}
    </View>
  );
}
