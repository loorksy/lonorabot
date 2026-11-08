import type {
  CapabilityReport,
  CapabilitySkill,
  SkillVersionControls,
  TrustedSource,
} from "@lonora/contracts";
import {
  builtInLine,
  capabilityText,
  integrationLine,
  serverLine,
  skillLine,
  sourceLine,
} from "@lonora/core";
import { Redirect, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { SettingsGroup } from "../../components/settings-group";
import { SheetHeader } from "../../components/sheet-header";
import { colors, ErrorNotice, Loading, Screen } from "../../components/ui";
import { api } from "../../lib/api";
import { useSession } from "../../lib/session";

/**
 * Capabilities: everything agents can use now, the same report and labels as the Web
 * (GET /capabilities, @lonora/core). Undo goes to the existing owner routes; trusting an
 * MCP server's tools happens on its card in the chat. Nothing here carries money authority.
 */
export default function Capabilities() {
  const { ready, owner, locale, rtl, errorText } = useSession();
  const text = capabilityText(locale);
  const [report, setReport] = useState<CapabilityReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setReport(await api.get<CapabilityReport>("/capabilities"));
  }, []);
  useFocusEffect(
    useCallback(() => {
      if (!owner) return;
      let live = true;
      load().catch((cause: unknown) => {
        if (live) setError(errorText(cause));
      });
      return () => {
        live = false;
      };
    }, [owner, load, errorText]),
  );
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  const act = async (request: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await request();
      await load();
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  };
  const align = { textAlign: rtl ? ("right" as const) : ("left" as const) };
  const line = (value: string, key: string, action?: { label: string; run: () => void }) => (
    <View
      key={key}
      testID={key}
      style={{ flexDirection: rtl ? "row-reverse" : "row", alignItems: "center", gap: 10 }}
    >
      <Text style={[{ color: colors.foreground, flex: 1 }, align]}>{value}</Text>
      {action ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={action.label}
          disabled={busy}
          onPress={action.run}
        >
          <Text style={{ color: colors.foreground, fontWeight: "600" }}>{action.label}</Text>
        </Pressable>
      ) : null}
    </View>
  );
  const none = <Text style={[{ color: colors.secondary }, align]}>{text.none}</Text>;
  const toggle = (source: TrustedSource) =>
    act(() =>
      api.post(`/trusted-sources/${source.id}/${source.active ? "revoke" : "restore"}`, {}),
    );
  const undo = (skill: CapabilitySkill) =>
    act(async () => {
      if (!skill.agent_id || !skill.version) return;
      const controls = await api.get<SkillVersionControls>(
        `/agents/${skill.agent_id}/skills/revocations`,
      );
      await api.post(`/agents/${skill.agent_id}/skills/revocations`, {
        skill_id: skill.skill_id,
        version: skill.version,
        expected_revision: controls.revision,
      });
    });
  const skills = report?.skills.filter((skill) => skill.provenance !== "bundled") ?? [];
  return (
    <Screen>
      <SheetHeader title={text.title} />
      <ScrollView contentContainerStyle={{ padding: 20, gap: 20 }}>
        <Text style={[{ color: colors.secondary, lineHeight: 22 }, align]}>{text.intro}</Text>
        <ErrorNotice text={error} />
        {report === null ? (
          <Loading />
        ) : (
          <>
            <SettingsGroup title={text.builtIn}>
              <View style={{ gap: 8 }}>
                {report.built_in.map((item) =>
                  line(builtInLine(item, locale), `capability-${item.capability}`),
                )}
              </View>
            </SettingsGroup>
            <SettingsGroup title={text.trustedSources}>
              <View style={{ gap: 8 }}>
                {report.trusted_sources.length
                  ? report.trusted_sources.map((source) =>
                      line(sourceLine(source, locale), `trusted-source-${source.id}`, {
                        label: source.active ? text.remove : text.restore,
                        run: () => void toggle(source),
                      }),
                    )
                  : none}
              </View>
            </SettingsGroup>
            <SettingsGroup title={text.servers}>
              <View style={{ gap: 8 }}>
                {report.mcp_servers.length
                  ? report.mcp_servers.map((server) =>
                      line(
                        serverLine(server, locale),
                        `mcp-server-${server.connection_id}`,
                        server.trust_source_id
                          ? {
                              label: text.remove,
                              run: () =>
                                void act(() =>
                                  api.post(`/trusted-sources/${server.trust_source_id}/revoke`, {}),
                                ),
                            }
                          : undefined,
                      ),
                    )
                  : none}
              </View>
            </SettingsGroup>
            <SettingsGroup title={text.skills}>
              <View style={{ gap: 8 }}>
                {skills.length
                  ? skills.map((skill) =>
                      line(
                        skillLine(skill, locale),
                        `capability-skill-${skill.resource_id}`,
                        skill.provenance === "external" || skill.provenance === "agent_authored"
                          ? { label: text.undo, run: () => void undo(skill) }
                          : undefined,
                      ),
                    )
                  : none}
              </View>
            </SettingsGroup>
            <SettingsGroup title={text.integrations}>
              <View style={{ gap: 8 }}>
                {report.integrations.length
                  ? report.integrations.map((item) =>
                      line(integrationLine(item, locale), `integration-${item.id}`, {
                        label: text.remove,
                        run: () => void act(() => api.delete(`/integrations/${item.id}`)),
                      }),
                    )
                  : none}
              </View>
            </SettingsGroup>
          </>
        )}
      </ScrollView>
    </Screen>
  );
}
