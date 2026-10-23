import { Redirect, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { Linking, ScrollView, Text } from "react-native";
import { IncomingCallSettings } from "../../components/incoming-call-settings";
import { SettingsGroup } from "../../components/settings-group";
import { SheetHeader } from "../../components/sheet-header";
import { Button, colors, ErrorNotice, Loading, Screen } from "../../components/ui";
import { api } from "../../lib/api";
import { useSession } from "../../lib/session";
export default function Voice() {
  const { ready, owner, server, t, errorText } = useSession();
  const [status, setStatus] = useState<{ transport_configured: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useFocusEffect(
    useCallback(() => {
      if (!owner) return;
      let live = true;
      void api
        .get<typeof status>("/voice/status")
        .then((value) => {
          if (live) {
            setStatus(value);
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
      <SheetHeader title={t("voice")} />
      <ScrollView contentContainerStyle={{ padding: 20, gap: 20 }}>
        <ErrorNotice text={error} />
        <SettingsGroup title="GPT-Live">
          <Text style={{ color: colors.foreground }}>
            {status
              ? t(status.transport_configured ? "configured" : "notConfigured")
              : t("connecting")}
          </Text>
        </SettingsGroup>
        <Text style={{ color: colors.secondary, lineHeight: 24 }}>{t("nativeCallHint")}</Text>
        <IncomingCallSettings />
        <Button
          label={t("openWebSettings")}
          onPress={() => {
            void Linking.openURL(`${server}/app?settings=voice`).catch((cause) =>
              setError(errorText(cause)),
            );
          }}
        />
      </ScrollView>
    </Screen>
  );
}
