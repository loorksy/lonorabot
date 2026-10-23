// Agent profile sheet follows Tampletgrok's native profile structure; see NOTICE.

import type { Agent } from "@lonora/contracts";
import { Redirect, useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { AccountAuthoritySettings } from "../components/account-authority-settings";
import { AvatarPicker } from "../components/avatar-picker";
import { ExecutionModeSettings } from "../components/execution-mode-settings";
import { PersonalAgentBadge } from "../components/personal-agent-badge";
import { SettingsGroup, SettingsRow, SettingsSwitch } from "../components/settings-group";
import { SheetHeader } from "../components/sheet-header";
import { colors, ErrorNotice, Field, Loading, Screen } from "../components/ui";
import { agents } from "../lib/agents";
import { api } from "../lib/api";
import { useSession } from "../lib/session";

type Memory = { content: string; version: number };
export default function BotSettings() {
  const { botId } = useLocalSearchParams<{ botId: string }>();
  const { ready, owner, rtl, t, errorText } = useSession();
  const router = useRouter();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [memory, setMemory] = useState<Memory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  useEffect(() => {
    if (!owner || !botId) return;
    let live = true;
    void agents
      .list()
      .then((rows) => {
        if (live) {
          const value = rows.find((row) => row.id === botId);
          if (value) setAgent(value);
          else setError(t("agentMissing"));
        }
      })
      .catch((reason) => {
        if (live) setError(errorText(reason));
      });
    void api
      .get<Memory>(`/agents/${encodeURIComponent(botId)}/memory`)
      .then((value) => {
        if (live) setMemory(value);
      })
      .catch((reason) => {
        if (live) setError(errorText(reason));
      });
    return () => {
      live = false;
    };
  }, [botId, owner, errorText, t]);
  const save = async () => {
    if (!agent || busy || confirmDelete) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      setAgent(
        await agents.update(agent.id, {
          name: agent.name.trim(),
          title: agent.title ?? "",
          description: agent.description ?? "",
          avatar: agent.avatar,
          color: agent.color,
          instructions: agent.instructions,
          paused: agent.paused,
        }),
      );
      if (memory)
        setMemory(
          await api.put<Memory>(`/agents/${encodeURIComponent(botId)}/memory`, {
            content: memory.content,
            version: memory.version,
          }),
        );
      setSaved(true);
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  };
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  return (
    <Screen>
      <SheetHeader
        title={t("agentSettings")}
        onClose={() => {
          if (!busy) router.back();
        }}
        action={t("save")}
        onAction={() => void save()}
        disabled={busy || confirmDelete || !agent?.name.trim()}
      />
      <ErrorNotice text={error} />
      {agent ? (
        <ScrollView
          contentContainerStyle={{ padding: 20, gap: 22 }}
          keyboardShouldPersistTaps="handled"
        >
          <AvatarPicker
            name={agent.name}
            color={agent.color}
            avatar={agent.avatar}
            onChange={(avatar, color) => {
              setAgent({ ...agent, avatar, color });
              setSaved(false);
            }}
          />
          <View
            style={{ flexDirection: rtl ? "row-reverse" : "row", alignItems: "center", gap: 6 }}
          >
            <Text style={{ color: colors.foreground, fontSize: 17 }}>{agent.name}</Text>
            <PersonalAgentBadge agent={agent} />
          </View>
          {agent.trading_symbol && (
            <SettingsGroup footer={t("immutableTradingPair")}>
              <SettingsRow title={t("symbol")} value={agent.trading_symbol} />
            </SettingsGroup>
          )}
          <Field
            label={t("name")}
            value={agent.name}
            maxLength={80}
            onChangeText={(name) => {
              setAgent({ ...agent, name });
              setSaved(false);
            }}
          />
          <ExecutionModeSettings agent={agent} onChange={setAgent} />
          <AccountAuthoritySettings key={agent.id} agent={agent} />
          <Field
            label={t("title")}
            value={agent.title ?? ""}
            maxLength={160}
            onChangeText={(title) => {
              setAgent({ ...agent, title });
              setSaved(false);
            }}
          />
          <Field
            label={t("description")}
            value={agent.description ?? ""}
            maxLength={2000}
            multiline
            onChangeText={(description) => {
              setAgent({ ...agent, description });
              setSaved(false);
            }}
            style={{ minHeight: 90, textAlignVertical: "top" }}
          />
          <Field
            label={t("instructions")}
            value={agent.instructions}
            onChangeText={(instructions) => setAgent({ ...agent, instructions })}
            maxLength={16000}
            multiline
            style={{ minHeight: 130, textAlignVertical: "top" }}
          />
          <SettingsGroup>
            <SettingsSwitch
              label={t("paused")}
              value={agent.paused}
              onChange={(paused) => {
                setAgent({ ...agent, paused });
                setSaved(false);
              }}
            />
            <SettingsRow
              title={t("skills")}
              detail={t("skillsHint")}
              icon="layers"
              onPress={() => router.push({ pathname: "/skills", params: { botId } })}
            />
            <SettingsRow
              title={t("routines")}
              icon="clock"
              onPress={() => router.push({ pathname: "/routine", params: { botId } })}
            />
          </SettingsGroup>
          {memory ? (
            <View style={{ gap: 8 }}>
              <Field
                label={t("memory")}
                value={memory.content}
                onChangeText={(content) => setMemory({ ...memory, content })}
                maxLength={30000}
                multiline
                style={{ minHeight: 180, textAlignVertical: "top" }}
              />
              <Text
                style={{
                  color: colors.secondary,
                  lineHeight: 22,
                  textAlign: rtl ? "right" : "left",
                }}
              >
                {t("memoryHint")}
              </Text>
            </View>
          ) : null}
          {agent.role === "personal" ? (
            <Text style={{ color: colors.secondary, textAlign: rtl ? "right" : "left" }}>
              {t("personal_agent_cannot_delete")}
            </Text>
          ) : (
            <View style={{ gap: 12 }}>
              {confirmDelete ? (
                <>
                  <Text
                    accessibilityRole="header"
                    style={{
                      color: colors.foreground,
                      fontSize: 17,
                      textAlign: rtl ? "right" : "left",
                    }}
                  >
                    {t("deleteAgentConfirm")}
                  </Text>
                  <Text style={{ color: colors.secondary, textAlign: rtl ? "right" : "left" }}>
                    {agent.name}
                    {"\n"}
                    {t("deleteAgentWarning")}
                  </Text>
                </>
              ) : null}
              <SettingsGroup>
                {confirmDelete ? (
                  <SettingsRow
                    title={t("deleteAgentCancel")}
                    disabled={busy}
                    onPress={() => setConfirmDelete(false)}
                  />
                ) : null}
                <SettingsRow
                  title={t(confirmDelete ? "deleteAgentPermanently" : "deleteAgent")}
                  destructive
                  disabled={busy}
                  onPress={async () => {
                    if (busy || agent.role === "personal") return;
                    if (!confirmDelete) {
                      setConfirmDelete(true);
                      return;
                    }
                    setBusy(true);
                    setError(null);
                    try {
                      await agents.remove(agent.id);
                      router.dismissAll();
                      router.replace("/");
                    } catch (reason) {
                      setError(errorText(reason));
                      setBusy(false);
                    }
                  }}
                />
              </SettingsGroup>
            </View>
          )}
          {saved ? (
            <Text style={{ color: colors.success, textAlign: "center" }}>{t("saved")}</Text>
          ) : null}
        </ScrollView>
      ) : error ? null : (
        <Loading />
      )}
    </Screen>
  );
}
