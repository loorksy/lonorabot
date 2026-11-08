import type { Agent, SupervisionView } from "@lonora/contracts";
import {
  type SupervisionRow,
  supervisionRows,
  supervisionText,
  unsupervisedAgents,
} from "@lonora/core";
import { useCallback, useEffect, useState } from "react";
import { Pressable, Text, View } from "react-native";
import { api } from "../lib/api";
import { useSession } from "../lib/session";
import { SettingsGroup, SettingsRow } from "./settings-group";
import { colors, ErrorNotice } from "./ui";

/**
 * Who supervises this agent and whom it supervises, each with one-tap Stop; Lonora's
 * profile also offers to supervise again an agent whose grant was stopped. The same
 * labels as the Web (@lonora/core). A grant never carries money authority.
 */
export function SupervisionSettings({ agent }: { agent: Agent }) {
  const { locale, errorText, rtl } = useSession();
  const text = supervisionText(locale);
  const personal = agent.role === "personal";
  const [view, setView] = useState<SupervisionView | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setView(
      await api.get<SupervisionView>(`/supervision?agent_id=${encodeURIComponent(agent.id)}`),
    );
    if (personal) setAgents(await api.get<Agent[]>("/agents"));
  }, [agent.id, personal]);
  useEffect(() => {
    let live = true;
    load().catch((reason: unknown) => {
      if (live) setError(errorText(reason));
    });
    return () => {
      live = false;
    };
  }, [load, errorText]);
  if (agent.role === "delegated") return null;
  const act = async (request: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await request();
      await load();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  };
  const button = (label: string, onPress: () => void, testID: string) => (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={label}
      disabled={busy}
      onPress={onPress}
      style={{ paddingHorizontal: 10, paddingVertical: 6, opacity: busy ? 0.4 : 1 }}
    >
      <Text style={{ color: colors.primary, fontSize: 16 }}>{label}</Text>
    </Pressable>
  );
  const group = (title: string, items: SupervisionRow[]) =>
    items.length > 0 ? (
      <SettingsGroup title={title}>
        {items.map((row) => (
          <SettingsRow
            key={row.grantId}
            title={row.name}
            detail={row.source}
            trailing={button(
              text.stop,
              () => void act(() => api.post(`/supervision/${row.grantId}/revoke`, {})),
              `supervision-stop-${row.agentId}`,
            )}
          />
        ))}
      </SettingsGroup>
    ) : null;
  const rows = view ? supervisionRows(view, locale) : null;
  const offered = view && personal ? unsupervisedAgents(view, agents) : [];
  return (
    <View style={{ gap: 10 }} testID="supervision-settings">
      <Text
        accessibilityRole="header"
        style={{ color: colors.foreground, fontSize: 17, textAlign: rtl ? "right" : "left" }}
      >
        {personal ? text.personalTitle : text.title}
      </Text>
      <Text
        style={{
          color: colors.secondary,
          fontSize: 14,
          lineHeight: 20,
          textAlign: rtl ? "right" : "left",
        }}
      >
        {personal ? text.personalIntro : text.intro}
      </Text>
      {rows && rows.supervises.length + rows.supervisedBy.length === 0 && !personal ? (
        <Text style={{ color: colors.secondary, textAlign: rtl ? "right" : "left" }}>
          {text.none}
        </Text>
      ) : null}
      {rows ? group(text.supervises, rows.supervises) : null}
      {rows ? group(text.supervisedBy, rows.supervisedBy) : null}
      {offered.length > 0 ? (
        <SettingsGroup title={text.notSupervised}>
          {offered.map((other) => (
            <SettingsRow
              key={other.id}
              title={other.name}
              trailing={button(
                text.supervise,
                () =>
                  void act(() =>
                    api.post("/supervision", { supervisor_id: agent.id, supervised_id: other.id }),
                  ),
                `supervision-add-${other.id}`,
              )}
            />
          ))}
        </SettingsGroup>
      ) : null}
      <ErrorNotice text={error} />
    </View>
  );
}
