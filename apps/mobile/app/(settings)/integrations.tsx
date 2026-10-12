import type { Resource } from "@lonora/contracts";
import { Redirect, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { Linking, ScrollView, Text } from "react-native";
import { SettingsGroup } from "../../components/settings-group";
import { SheetHeader } from "../../components/sheet-header";
import { Button, colors, ErrorNotice, Loading, Screen } from "../../components/ui";
import { api } from "../../lib/api";
import { useSession } from "../../lib/session";
export default function Integrations() {
  const { ready, owner, server, t, errorText } = useSession();
  const [rows, setRows] = useState<Resource[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useFocusEffect(
    useCallback(() => {
      if (!owner) return;
      let live = true;
      void api
        .get<Resource[]>("/integrations")
        .then((list) => {
          if (live) {
            setRows(list);
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
      <SheetHeader title={t("integrations")} />
      <ScrollView contentContainerStyle={{ padding: 20, gap: 20 }}>
        <ErrorNotice text={error} />
        {rows === null ? (
          <Text style={{ color: colors.secondary }}>{t("connecting")}</Text>
        ) : !rows.length ? (
          <Text style={{ color: colors.secondary }}>{t("notConfigured")}</Text>
        ) : (
          rows.map((row) => (
            <SettingsGroup key={row.id} title={String(row.payload.name)}>
              <Text style={{ color: colors.foreground }}>
                {String(row.payload.type)} · {t(row.payload.enabled ? "enabled" : "paused")}
              </Text>
            </SettingsGroup>
          ))
        )}
        <Text style={{ color: colors.secondary, lineHeight: 24 }}>{t("configureWeb")}</Text>
        <Button
          label={t("openWebSettings")}
          onPress={() => {
            void Linking.openURL(`${server}/app?settings=integrations`).catch((cause) =>
              setError(errorText(cause)),
            );
          }}
        />
      </ScrollView>
    </Screen>
  );
}
