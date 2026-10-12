import { Redirect, useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { Button, colors, ErrorNotice, Header, Loading, Screen, styles } from "../components/ui";
import { api } from "../lib/api";
import { useSession } from "../lib/session";
import type { Routing, Usage } from "../lib/types";

export default function Settings() {
  const { ready, owner, server, rtl, locale, t, errorText, changeLocale, logout } = useSession();
  const router = useRouter();
  const [routing, setRouting] = useState<Routing | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useFocusEffect(
    useCallback(() => {
      if (!owner) return;
      let live = true;
      void Promise.all([api.get<Routing>("/settings/models"), api.get<Usage>("/usage/summary")])
        .then(([nextRouting, nextUsage]) => {
          if (live) {
            setRouting(nextRouting);
            setUsage(nextUsage);
            setError(null);
          }
        })
        .catch((reason) => {
          if (live) setError(errorText(reason));
        });
      return () => {
        live = false;
      };
    }, [owner, errorText]),
  );
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  const signOut = async () => {
    setBusy(true);
    setError(null);
    try {
      await logout();
      router.replace("/sign-in");
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  };
  const labelStyle = {
    color: colors.secondary,
    textAlign: rtl ? ("right" as const) : ("left" as const),
    fontSize: 14,
  };
  return (
    <Screen>
      <Header
        title={t("settings")}
        left={
          <Button
            label={t("back")}
            secondary
            onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))}
          />
        }
      />
      <ScrollView contentContainerStyle={{ padding: 20, gap: 20 }}>
        <ErrorNotice text={error} />
        <View style={styles.card}>
          <Text style={labelStyle}>{t("account")}</Text>
          <Text selectable style={{ color: colors.foreground, writingDirection: "ltr" }}>
            {owner.email}
          </Text>
          <Text selectable style={{ color: colors.secondary, writingDirection: "ltr" }}>
            {server}
          </Text>
        </View>
        <View style={styles.card}>
          <Text style={labelStyle}>{t("language")}</Text>
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
        </View>
        <View style={styles.card}>
          <Text style={labelStyle}>{t("models")}</Text>
          {routing ? (
            <>
              <Text style={{ color: colors.foreground, textAlign: rtl ? "right" : "left" }}>
                {t(routing.mode)}
              </Text>
              {routing.mode === "unified" ? (
                <Text
                  selectable
                  style={{
                    color: colors.secondary,
                    writingDirection: routing.unified ? "ltr" : "auto",
                  }}
                >
                  {routing.unified
                    ? `${routing.unified.provider} · ${routing.unified.model}`
                    : t("notConfigured")}
                </Text>
              ) : (
                Object.entries(routing.routes).map(([capability, selection]) => (
                  <Text
                    key={capability}
                    selectable
                    style={{ color: colors.secondary, writingDirection: "ltr" }}
                  >
                    {capability}: {selection.provider} · {selection.model}
                  </Text>
                ))
              )}
            </>
          ) : (
            <Text style={labelStyle}>{t("connecting")}</Text>
          )}
          <Text style={[labelStyle, { lineHeight: 23 }]}>{t("configureWeb")}</Text>
        </View>
        <View style={styles.card}>
          <Text style={labelStyle}>{t("usage")}</Text>
          {usage ? (
            [
              ["inputTokens", usage.input_tokens],
              ["outputTokens", usage.output_tokens],
              ["cachedTokens", usage.cached_tokens],
            ].map(([key, value]) => (
              <View
                key={String(key)}
                style={{
                  flexDirection: rtl ? "row-reverse" : "row",
                  justifyContent: "space-between",
                }}
              >
                <Text style={labelStyle}>
                  {t(key as "inputTokens" | "outputTokens" | "cachedTokens")}
                </Text>
                <Text style={{ color: colors.foreground }}>
                  {Number(value).toLocaleString(locale)}
                </Text>
              </View>
            ))
          ) : (
            <Text style={labelStyle}>{t("connecting")}</Text>
          )}
        </View>
        <Text style={[labelStyle, { textAlign: "center", lineHeight: 24 }]}>
          {t("threadsPersist")}
        </Text>
        <Button label={t("logout")} secondary disabled={busy} onPress={() => void signOut()} />
      </ScrollView>
    </Screen>
  );
}
