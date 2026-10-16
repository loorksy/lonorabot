import type { DeviceChallenge, SuperBotRequest } from "@lonora/contracts";
import { useEffect, useState } from "react";
import { Linking, Platform, Text, TextInput, View } from "react-native";
import { api } from "../lib/api";
import { deviceProof, deviceSupported } from "../lib/device-proof";
import { useSession } from "../lib/session";
import { Button, colors, ErrorNotice } from "./ui";

export function SuperBotCards({
  agentId,
  threadId,
  revision,
}: {
  agentId: string;
  threadId: string;
  revision: number;
}) {
  const { t, errorText, owner, server } = useSession();
  const [rows, setRows] = useState<SuperBotRequest[]>([]);
  const [supported, setSupported] = useState(false);
  const [password, setPassword] = useState("");
  const [enroll, setEnroll] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    let active = true;
    void Promise.all([
      deviceSupported(),
      api.get<{ android_configured: boolean; ios_configured: boolean }>("/auth/devices/config"),
    ])
      .then(([local, config]) => {
        if (active)
          setSupported(
            Boolean(local) &&
              (Platform.OS === "web" ||
                (Platform.OS === "android" ? config.android_configured : config.ios_configured)),
          );
      })
      .catch(() => {
        if (active) setSupported(false);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    void revision;
    void owner?.id;
    let active = true;
    void api
      .get<SuperBotRequest[]>(`/agents/${encodeURIComponent(agentId)}/super-bot`)
      .then((items) => {
        if (active) setRows(items);
      })
      .catch((cause) => {
        if (active) setError(errorText(cause));
      });
    return () => {
      active = false;
    };
  }, [agentId, revision, owner?.id, errorText]);
  const visible = rows.filter((row) => row.thread_id === threadId).slice(0, 3);
  const statuses = {
    pending: t("devicePending"),
    activated: t("active"),
    expired: t("expired"),
    rejected: t("rejected"),
    cancelled: t("cancelled"),
    paused: t("paused"),
    disabled: t("stopped"),
  };
  async function act(row: SuperBotRequest, action: string) {
    setBusy(true);
    setError(null);
    try {
      if (action === "activate") {
        const challenge = await api.post<DeviceChallenge>(`/super-bot/${row.id}/challenge`, {});
        await api.post("/super-bot/verify", await deviceProof(challenge));
      } else await api.post("/super-bot/control", { request_id: row.id, action });
      setRows(await api.get<SuperBotRequest[]>(`/agents/${agentId}/super-bot`));
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }
  if (!visible.length && !error) return null;
  return (
    <View style={{ padding: 12, gap: 8 }}>
      <ErrorNotice text={error} />
      {visible.map((row) => (
        <View
          key={row.id}
          style={{ backgroundColor: colors.muted, borderRadius: 16, padding: 12, gap: 8 }}
        >
          <Text style={{ color: colors.foreground }}>
            {t("superBot")} · {statuses[row.status]}
          </Text>
          <Text style={{ color: colors.foreground, writingDirection: "ltr" }}>
            {row.envelope.symbol} · {row.envelope.maximum_volume ?? "—"}
          </Text>
          {row.envelope.execution_mode === "shadow" && (
            <Text style={{ color: colors.secondary }}>{t("shadowMode")}</Text>
          )}
          <Text style={{ color: colors.foreground }}>{row.envelope.goal_title}</Text>
          <Text style={{ color: colors.secondary }}>{row.envelope.objective}</Text>
          <Text style={{ color: colors.secondary }}>
            {t(row.mode)} · {t("maxTradeActions")}: {row.envelope.max_trade_actions}
          </Text>
          <Text style={{ color: colors.secondary }}>
            {t(
              row.envelope.allow_manual_positions
                ? "manualManagementAllowed"
                : "manualManagementExcluded",
            )}
          </Text>
          <Button secondary label={t("reviewPlan")} onPress={() => setExpanded(!expanded)} />
          {expanded &&
            row.envelope.steps.map((step) => (
              <Text key={step.id} style={{ color: colors.secondary }}>
                {step.title}
                {step.trade &&
                  ` · ${step.trade.action} ${step.trade.symbol} ${step.trade.volume ?? "—"} @ ${step.trade.price ?? "—"} · ${step.trade.position_id ?? step.trade.order_id ?? step.trade.target_step_id ?? "—"} · ${t("stopLoss")}: ${step.trade.stop_loss ?? "—"} · ${t("takeProfit")}: ${step.trade.take_profit ?? "—"}`}
              </Text>
            ))}
          {row.status === "pending" ? (
            <>
              <Button
                label={t("deviceActivate")}
                disabled={busy || !supported}
                onPress={() => void act(row, "activate")}
              />
              <Button
                secondary
                label={t("deviceRegister")}
                disabled={busy || !supported}
                onPress={() => setEnroll(!enroll)}
              />
              <Button
                secondary
                label={t("reject")}
                disabled={busy}
                onPress={() => void act(row, "reject")}
              />
            </>
          ) : (
            ["activated", "paused"].includes(row.status) && (
              <Button
                label={t("superBotStop")}
                disabled={busy}
                onPress={() => void act(row, "stop")}
              />
            )
          )}
        </View>
      ))}
      {enroll && (
        <View style={{ gap: 8 }}>
          <TextInput
            accessibilityLabel={t("confirmAccountPassword")}
            secureTextEntry
            autoComplete="current-password"
            value={password}
            onChangeText={setPassword}
            style={{
              color: colors.foreground,
              borderWidth: 1,
              borderColor: colors.border,
              borderRadius: 12,
              padding: 12,
            }}
          />
          <Button
            label={t("registerThisDevice")}
            disabled={busy || !password}
            onPress={() => {
              void (async () => {
                setBusy(true);
                setError(null);
                const current = password;
                setPassword("");
                try {
                  const challenge = await api.post<DeviceChallenge>("/auth/devices/enrollment", {
                    password: current,
                    name: t("myDevice"),
                  });
                  await api.post(
                    "/auth/devices/enrollment/verify",
                    await deviceProof(challenge, true),
                  );
                  setEnroll(false);
                } catch (cause) {
                  setError(errorText(cause));
                } finally {
                  setBusy(false);
                }
              })();
            }}
          />
          <Button
            secondary
            label={t("cancel")}
            onPress={() => {
              setEnroll(false);
              setPassword("");
            }}
          />
        </View>
      )}
      {!supported && (
        <>
          <Text style={{ color: colors.secondary }}>{t("device_not_supported")}</Text>
          {Platform.OS !== "web" && (
            <Button
              secondary
              label={t("authorizeOnWeb")}
              onPress={() => {
                void Linking.openURL(`${server}/app/${encodeURIComponent(agentId)}`).catch(
                  (cause) => setError(errorText(cause)),
                );
              }}
            />
          )}
        </>
      )}
    </View>
  );
}
