import type { Usage } from "@lonora/contracts";
import { Redirect, useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { SettingsGroup } from "../../components/settings-group";
import { SheetHeader } from "../../components/sheet-header";
import { Button, colors, ErrorNotice, Loading, Screen } from "../../components/ui";
import { api } from "../../lib/api";
import { useSession } from "../../lib/session";

export default function Account() {
  const { ready, owner, server, locale, rtl, t, errorText, changeLocale, logout } = useSession();
  const router = useRouter();
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useFocusEffect(
    useCallback(() => {
      if (!owner) return;
      let live = true;
      void api
        .get<Usage>("/usage/summary")
        .then((value) => {
          if (live) {
            setUsage(value);
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
      <SheetHeader title={t("account")} />
      <ScrollView contentContainerStyle={{ padding: 20, gap: 20 }}>
        <ErrorNotice text={error} />
        <SettingsGroup title={t("account")}>
          <Text selectable style={{ color: colors.foreground, writingDirection: "ltr" }}>
            {owner.email}
          </Text>
          <Text selectable style={{ color: colors.secondary, writingDirection: "ltr" }}>
            {server}
          </Text>
        </SettingsGroup>
        <SettingsGroup title={t("language")}>
          <View style={{ flexDirection: rtl ? "row-reverse" : "row", gap: 12 }}>
            <Button
              label="العربية"
              secondary={locale !== "ar"}
              onPress={() => void changeLocale("ar")}
            />
            <Button
              label="English"
              secondary={locale !== "en"}
              onPress={() => void changeLocale("en")}
            />
          </View>
        </SettingsGroup>
        <SettingsGroup title={t("usage")}>
          {usage ? (
            (
              [
                ["inputTokens", usage.input_tokens],
                ["outputTokens", usage.output_tokens],
                ["cachedTokens", usage.cached_tokens],
              ] as const
            ).map(([label, value]) => (
              <View
                key={label}
                style={{
                  flexDirection: rtl ? "row-reverse" : "row",
                  justifyContent: "space-between",
                }}
              >
                <Text style={{ color: colors.secondary }}>{t(label)}</Text>
                <Text style={{ color: colors.foreground }}>{value.toLocaleString(locale)}</Text>
              </View>
            ))
          ) : (
            <Text style={{ color: colors.secondary }}>{t("connecting")}</Text>
          )}
        </SettingsGroup>
        <Button
          label={t("logout")}
          secondary
          disabled={busy}
          onPress={() => {
            setBusy(true);
            void logout()
              .then(() => router.replace("/sign-in"))
              .catch((cause) => setError(errorText(cause)))
              .finally(() => setBusy(false));
          }}
        />
      </ScrollView>
    </Screen>
  );
}
