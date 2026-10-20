import type { SkillCatalog, SkillCatalogEntry, SkillVersionControls } from "@lonora/contracts";
import { Redirect, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { SettingsGroup } from "../components/settings-group";
import { SheetHeader } from "../components/sheet-header";
import { ExactVersionBlock } from "../components/skills/exact-version-block";
import { availabilityLabel, reasons, styles } from "../components/skills/shared";
import { SkillCreate } from "../components/skills/skill-create";
import { SkillDetails } from "../components/skills/skill-details";
import { Button, ErrorNotice, Loading, Screen } from "../components/ui";
import { api, SessionRequestCancelled } from "../lib/api";
import { useSession } from "../lib/session";

export default function SkillsScreen() {
  const { botId } = useLocalSearchParams<{ botId: string }>();
  const { ready, owner, server } = useSession();
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  if (!botId) return <Redirect href="/" />;
  // An old Agent/account response must never repopulate a replacement screen.
  return <SkillManagement key={JSON.stringify([server, owner.id, botId])} agentId={botId} />;
}

function SkillManagement({ agentId }: { agentId: string }) {
  const { t, rtl, errorText } = useSession();
  const [catalog, setCatalog] = useState<SkillCatalog | null>(null);
  const [controls, setControls] = useState<SkillVersionControls | null>(null);
  const [error, setError] = useState<unknown>();
  const [selected, setSelected] = useState<SkillCatalogEntry | null>(null);
  const [loading, setLoading] = useState(false);
  const sequence = useRef(0);
  const prefix = `/agents/${encodeURIComponent(agentId)}/skills`;
  const load = useCallback(
    async (offset = 0) => {
      const request = ++sequence.current;
      setLoading(true);
      setError(undefined);
      try {
        const [page, currentControls] = await Promise.all([
          api.get<SkillCatalog>(`${prefix}/catalog?offset=${offset}&limit=50`),
          api.get<SkillVersionControls>(`${prefix}/revocations`),
        ]);
        if (request !== sequence.current) return;
        if (page.agent_id !== agentId || currentControls.agent_id !== agentId) return;
        setCatalog((current) => ({
          ...page,
          items:
            offset && current
              ? [
                  ...current.items,
                  ...page.items.filter((row) => !current.items.some((old) => old.id === row.id)),
                ]
              : page.items,
        }));
        setControls(currentControls);
      } catch (cause) {
        if (request === sequence.current && !(cause instanceof SessionRequestCancelled))
          setError(cause);
      } finally {
        if (request === sequence.current) setLoading(false);
      }
    },
    [prefix, agentId],
  );
  useEffect(() => {
    void load();
    return () => {
      sequence.current++;
    };
  }, [load]);
  const textAlign = rtl ? "right" : "left";
  return (
    <Screen>
      <SheetHeader title={t("skills")} />
      <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
        <Text style={[styles.hint, { textAlign }]}>{t("skillsCatalogHint")}</Text>
        <ErrorNotice text={error ? errorText(error) : null} />
        <Button label={t("refresh")} secondary onPress={() => void load()} disabled={loading} />
        {catalog ? <SkillCreate agentId={agentId} onChanged={() => void load()} /> : null}
        {!catalog && loading ? <Loading /> : null}
        <Text accessibilityRole="header" style={[styles.heading, { textAlign }]}>
          {t("skillsCurrentCatalog")}
        </Text>
        {catalog?.items.length === 0 ? <Text style={styles.hint}>{t("skillsNone")}</Text> : null}
        {catalog?.items.map((item) => (
          <Pressable
            key={item.id}
            accessibilityRole="button"
            accessibilityLabel={item.title}
            testID={`skill-entry-${item.id}`}
            onPress={() => setSelected(item)}
            style={({ pressed }) => [styles.card, pressed && { opacity: 0.65 }]}
          >
            <View style={[styles.row, { flexDirection: rtl ? "row-reverse" : "row" }]}>
              <Text style={[styles.heading, { flex: 1, textAlign }]}>{item.title}</Text>
              <Text style={styles.technical}>{item.version ?? "—"}</Text>
            </View>
            <Text style={[styles.hint, { textAlign }]}>{item.description}</Text>
            <Text style={[styles.caption, { textAlign }]}>
              {t(
                item.source === "builtin"
                  ? "skillsBuiltin"
                  : item.source === "legacy"
                    ? "skillsLegacy"
                    : "skillsOwner",
              )}
              {" · "}
              {t(item.available ? "skillsAvailable" : "skillsUnavailable")}
            </Text>
            {item.code ? (
              <Text style={[styles.hint, { textAlign }]}>{availabilityLabel(item.code, t)}</Text>
            ) : null}
          </Pressable>
        ))}
        {catalog?.next_offset != null ? (
          <Button
            label={t("skillsMore")}
            secondary
            disabled={loading}
            onPress={() => void load(catalog.next_offset ?? 0)}
          />
        ) : null}
        {controls ? (
          <ExactVersionBlock agentId={agentId} controls={controls} onChanged={() => void load()} />
        ) : null}
        <SettingsGroup title={t("skillsRevocations")}>
          {controls?.revoked.length ? (
            controls.revoked.map((row) => (
              <View key={`${row.skill_id}:${row.version}`} style={{ gap: 5 }}>
                <Text style={styles.technical}>
                  {row.skill_id} · {row.version}
                </Text>
                <Text style={[styles.hint, { textAlign }]}>
                  {t(
                    reasons.find((reason) => reason.id === row.reason)?.label ??
                      "skillsReasonOwner",
                  )}
                </Text>
                <Text style={styles.technical}>{new Date(row.revoked_at).toLocaleString()}</Text>
              </View>
            ))
          ) : (
            <Text style={[styles.hint, { textAlign }]}>{t("skillsNoRevocations")}</Text>
          )}
        </SettingsGroup>
      </ScrollView>
      {selected && controls ? (
        <SkillDetails
          key={selected.id}
          agentId={agentId}
          entry={selected}
          controls={controls}
          onClose={() => setSelected(null)}
          onChanged={() => void load()}
        />
      ) : null}
    </Screen>
  );
}
