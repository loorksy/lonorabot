import type { Provider, Routing } from "@lonora/contracts";
import { Redirect, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { Linking, ScrollView, Text } from "react-native";
import { SettingsGroup } from "../../components/settings-group";
import { SheetHeader } from "../../components/sheet-header";
import { Button, colors, ErrorNotice, Loading, Screen } from "../../components/ui";
import { api } from "../../lib/api";
import { useSession } from "../../lib/session";
export default function Models() {
  const { ready, owner, server, t, errorText } = useSession();
  const [routing, setRouting] = useState<Routing | null>(null);
  const [providers, setProviders] = useState<{ id: Provider; configured: boolean }[]>([]);
  const [error, setError] = useState<string | null>(null);
  useFocusEffect(
    useCallback(() => {
      if (!owner) return;
      let live = true;
      void Promise.all([
        api.get<Routing>("/settings/models"),
        api.get<typeof providers>("/providers"),
      ])
        .then(([policy, list]) => {
          if (live) {
            setRouting(policy);
            setProviders(list);
            setError(null);
          }
        })
        .catch((cause) => {
          if (live) setError(errorText(cause));
        });
      return () => {
        live = false;
      };
    }, [owner, errorText]),
  );
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  return (
    <Screen>
      <SheetHeader title={t("models")} />
      <ScrollView contentContainerStyle={{ padding: 20, gap: 20 }}>
        <ErrorNotice text={error} />
        <SettingsGroup title={t("models")}>
          {routing ? (
            <>
              <Text style={{ color: colors.foreground }}>{t(routing.mode)}</Text>
              {routing.mode === "unified" ? (
                <Text selectable style={{ color: colors.secondary }}>
                  {routing.unified
                    ? `${routing.unified.provider} · ${routing.unified.model}`
                    : t("notConfigured")}
                </Text>
              ) : (
                Object.entries(routing.routes).map(([capability, selection]) => (
                  <Text selectable key={capability} style={{ color: colors.secondary }}>
                    {capability}: {selection?.provider} · {selection?.model}
                  </Text>
                ))
              )}
            </>
          ) : (
            <Text style={{ color: colors.secondary }}>{t("connecting")}</Text>
          )}
        </SettingsGroup>
        <SettingsGroup title={t("providers")}>
          {providers.map((provider) => (
            <Text key={provider.id} style={{ color: colors.foreground }}>
              {provider.id} · {t(provider.configured ? "configured" : "notConfigured")}
            </Text>
          ))}
        </SettingsGroup>
        <Text style={{ color: colors.secondary, lineHeight: 24 }}>{t("configureWeb")}</Text>
        <Button
          label={t("openWebSettings")}
          onPress={() => {
            void Linking.openURL(`${server}/app?settings=models`).catch((cause) =>
              setError(errorText(cause)),
            );
          }}
        />
      </ScrollView>
    </Screen>
  );
}
