import type { Usage } from "@lonora/contracts";
import { Redirect, useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { ScrollView, Text } from "react-native";
import { NativeSymbol } from "../../components/native-symbol";
import { SettingsGroup, SettingsRow } from "../../components/settings-group";
import { SheetHeader } from "../../components/sheet-header";
import { colors, ErrorNotice, Loading, Screen } from "../../components/ui";
import { api } from "../../lib/api";
import { useSession } from "../../lib/session";

export default function Account() {
  const { ready, owner, server, locale, t, errorText, changeLocale, logout } = useSession();
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
          <SettingsRow title={t("email")} detail={owner.email} />
          <SettingsRow title={t("server")} detail={server} onPress={() => router.push("/server")} />
        </SettingsGroup>
        <SettingsGroup title={t("language")}>
          <SettingsRow
            title="العربية"
            onPress={() => void changeLocale("ar")}
            trailing={locale === "ar" ? <NativeSymbol name="check" size={17} /> : undefined}
          />
          <SettingsRow
            title="English"
            onPress={() => void changeLocale("en")}
            trailing={locale === "en" ? <NativeSymbol name="check" size={17} /> : undefined}
          />
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
              <SettingsRow key={label} title={t(label)} value={value.toLocaleString(locale)} />
            ))
          ) : (
            <Text style={{ color: colors.secondary }}>{t("connecting")}</Text>
          )}
        </SettingsGroup>
        <SettingsGroup>
          <SettingsRow
            title={t("logout")}
            destructive
            disabled={busy}
            onPress={() => {
              setBusy(true);
              void logout()
                .then(() => router.replace("/sign-in"))
                .catch((cause) => setError(errorText(cause)))
                .finally(() => setBusy(false));
            }}
          />
        </SettingsGroup>
      </ScrollView>
    </Screen>
  );
}
