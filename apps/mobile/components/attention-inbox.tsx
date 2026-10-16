import type {
  Agent,
  AttentionCode,
  AttentionNotification,
  AttentionPolicy,
} from "@lonora/contracts";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Text, View } from "react-native";
import { api } from "../lib/api";
import type { Label } from "../lib/i18n";
import { useSession } from "../lib/session";
import { SettingsGroup, SettingsSwitch } from "./settings-group";
import { Button, colors, ErrorNotice } from "./ui";

const labels: Record<AttentionCode, Label> = {
  emergency_stop: "attentionEmergency",
  approval_required: "attentionApproval",
  approval_resolved: "attentionRequestUpdated",
  broker_degraded: "attentionBrokerDegraded",
  broker_recovered: "attentionBrokerRecovered",
  external_broker_activity: "attentionAccountChanged",
  setup_confirmed: "attentionSetupConfirmed",
  thesis_invalidated: "attentionThesisChanged",
  watch_condition_met: "attentionWatchChanged",
  goal_changed: "attentionGoalChanged",
  collaboration_completed: "attentionCollaborationCompleted",
  task_review: "taskNeedsReview",
  task_completed: "attentionTaskCompleted",
  internal_update: "attentionUpdated",
};
export function AttentionInbox({
  items,
  agents,
  onSeen,
}: {
  items: AttentionNotification[];
  agents: Agent[];
  onSeen: (id: string) => Promise<void>;
}) {
  const { t, locale, errorText, rtl } = useSession();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState<AttentionPolicy>();
  const [saving, setSaving] = useState(false);
  const [clock, setClock] = useState(Date.now());
  useEffect(() => {
    let active = true;
    void api
      .get<AttentionPolicy>("/attention/policy")
      .then((row) => {
        if (active) setSettings(row);
      })
      .catch((cause) => {
        if (active) setError(errorText(cause));
      });
    return () => {
      active = false;
    };
  }, [errorText]);
  useEffect(() => {
    const deadlines = items
      .filter((row) => row.importance === "opportunity" && row.parameters.valid_until)
      .map((row) => new Date(row.parameters.valid_until as string).getTime())
      .filter((value) => value > clock);
    if (!deadlines.length) return;
    const timer = setTimeout(
      () => setClock(Date.now()),
      Math.max(0, Math.min(2_147_483_647, Math.min(...deadlines) - Date.now())),
    );
    return () => clearTimeout(timer);
  }, [items, clock]);
  const visible = items.filter(
    (item) =>
      item.importance !== "opportunity" ||
      (item.parameters.valid_until && new Date(item.parameters.valid_until).getTime() > Date.now()),
  );
  return (
    <View style={{ padding: 16, gap: 12 }}>
      <Text
        accessibilityRole="header"
        style={{ color: colors.foreground, fontSize: 19, textAlign: rtl ? "right" : "left" }}
      >
        {t("notifications")}
      </Text>
      <ErrorNotice text={error} />
      {settings && (
        <SettingsGroup>
          <SettingsSwitch
            label={t("attentionOpportunityPreference")}
            disabled={saving}
            value={settings.opportunities}
            onChange={async (opportunities) => {
              setSaving(true);
              try {
                setSettings(
                  await api.put<AttentionPolicy>("/attention/policy", {
                    ...settings,
                    opportunities,
                    locale,
                  }),
                );
              } catch (cause) {
                setError(errorText(cause));
              } finally {
                setSaving(false);
              }
            }}
          />
        </SettingsGroup>
      )}
      {visible.length === 0 && (
        <Text style={{ color: colors.secondary }}>{t("noNotifications")}</Text>
      )}
      {visible.map((item) => (
        <View
          key={item.id}
          style={{ backgroundColor: colors.muted, padding: 14, borderRadius: 16, gap: 8 }}
        >
          <Text style={{ color: colors.foreground, textAlign: rtl ? "right" : "left" }}>
            {t(labels[item.code])}
          </Text>
          <Text style={{ color: colors.secondary, textAlign: rtl ? "right" : "left" }}>
            {agents.find((agent) => agent.id === item.agent_id)?.name}
          </Text>
          {item.parameters.symbol && (
            <Text style={{ color: colors.foreground, writingDirection: "ltr" }}>
              {item.parameters.symbol}
            </Text>
          )}
          <Button
            secondary
            label={t("openConversation")}
            onPress={() => {
              void onSeen(item.id)
                .then(() => {
                  router.push({
                    pathname: item.parameters.group_id ? "/group-thread" : "/thread",
                    params: item.parameters.group_id
                      ? { groupId: item.parameters.group_id }
                      : { id: item.thread_id },
                  });
                })
                .catch((cause) => setError(errorText(cause)));
            }}
          />
          <Button
            secondary
            label={t("markAsRead")}
            onPress={() => {
              void onSeen(item.id).catch((cause) => setError(errorText(cause)));
            }}
          />
        </View>
      ))}
    </View>
  );
}
