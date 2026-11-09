import type {
  CapabilityReport,
  CapabilitySkill,
  EffectTier,
  McpTrustPreview,
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
import { Linking, Pressable, ScrollView, Text, View } from "react-native";
import { SettingsGroup } from "../../components/settings-group";
import { SheetHeader } from "../../components/sheet-header";
import { Button, colors, ErrorNotice, Loading, Screen } from "../../components/ui";
import { api } from "../../lib/api";
import { useSession } from "../../lib/session";

/**
 * Capabilities: everything agents can use now, the same report and labels as the Web
 * (GET /capabilities, @lonora/core). Undo goes to the existing owner routes; a server whose
 * tools are not trusted yet is reviewed and trusted here (or on its card in the chat), and
 * setting up a new integration opens the web settings. Nothing here carries money authority.
 */
export default function Capabilities() {
  const { ready, owner, locale, rtl, errorText, server: origin } = useSession();
  const text = capabilityText(locale);
  const [report, setReport] = useState<CapabilityReport | null>(null);
  const [preview, setPreview] = useState<{ id: string; tools: McpTrustPreview } | null>(null);
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
  const review = (connectionId: string) =>
    act(async () => {
      setPreview({
        id: connectionId,
        tools: await api.post<McpTrustPreview>(`/trusted-sources/mcp/${connectionId}/preview`, {}),
      });
    });
  const trust = (tier: EffectTier) =>
    act(async () => {
      if (!preview) return;
      await api.post(`/trusted-sources/mcp/${preview.id}`, { tier, digest: preview.tools.digest });
      setPreview(null);
    });
  const names = (values: string[]) =>
    values.map((name) => `\u2068${name}\u2069`).join(rtl ? "، " : ", ");
  const previewBlock = (connectionId: string) =>
    preview?.id === connectionId ? (
      <View key={`mcp-preview-${connectionId}`} testID="mcp-preview" style={{ gap: 6 }}>
        <Text style={[{ color: colors.foreground }, align]}>
          {text.tools}: {names(preview.tools.tools)}
        </Text>
        {preview.tools.writes.length ? (
          <Text style={[{ color: colors.foreground }, align]}>
            {text.writes}: {names(preview.tools.writes)}
          </Text>
        ) : null}
        {preview.tools.blocked.length ? (
          <Text style={[{ color: colors.foreground }, align]}>
            {text.blocked}: {names(preview.tools.blocked)}
          </Text>
        ) : null}
        <Text style={[{ color: colors.secondary }, align]}>{text.neverMoney}</Text>
        <Button
          label={
            preview.tools.writes.length && !preview.tools.blocked.length
              ? text.trustRead
              : text.trust
          }
          disabled={busy || !preview.tools.tools.length}
          onPress={() => void trust("read")}
        />
        {/* A server with a blocked money tool is trusted to read only. */}
        {preview.tools.writes.length && !preview.tools.blocked.length ? (
          <Button
            label={text.trustWrite}
            secondary
            disabled={busy}
            onPress={() => void trust("write_nonfinancial")}
          />
        ) : null}
      </View>
    ) : null;
  const undo = (skill: CapabilitySkill) =>
    act(async () => {
      if (!skill.can_undo || !skill.agent_id || !skill.version) return;
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
                  ? report.mcp_servers.flatMap((server) => [
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
                          : { label: text.review, run: () => void review(server.connection_id) },
                      ),
                      previewBlock(server.connection_id),
                    ])
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
                        skill.can_undo
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
            <Button
              label={text.setUp}
              secondary
              onPress={() => {
                void Linking.openURL(`${origin}/app?settings=integrations`).catch((cause) =>
                  setError(errorText(cause)),
                );
              }}
            />
          </>
        )}
      </ScrollView>
    </Screen>
  );
}
