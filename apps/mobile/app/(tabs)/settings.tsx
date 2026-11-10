import { Redirect, useRouter } from "expo-router";
import { ScrollView, Text, View } from "react-native";
import { SettingsGroup, SettingsRow } from "../../components/settings-group";
import { colors, Loading } from "../../components/ui";
import { useSession } from "../../lib/session";
import { useTheme } from "../../lib/theme";
export default function Settings() {
  const { ready, owner, t, rtl } = useSession();
  const router = useRouter();
  const { mode, setMode } = useTheme();
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <Text
        accessibilityRole="header"
        style={{
          color: colors.foreground,
          fontSize: 28,
          fontWeight: "700",
          paddingHorizontal: 20,
          paddingTop: 14,
          textAlign: rtl ? "right" : "left",
        }}
      >
        {t("settings")}
      </Text>
      <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 130, gap: 24 }}>
        <View style={{ alignItems: "center", gap: 8, paddingVertical: 16 }}>
          <View
            style={{
              width: 64,
              height: 64,
              borderRadius: 32,
              backgroundColor: colors.accent,
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Text style={{ color: colors.foreground, fontSize: 23, fontWeight: "600" }}>
              {owner.email.slice(0, 2).toUpperCase()}
            </Text>
          </View>
          <Text
            selectable
            style={{ color: colors.secondary, fontSize: 14, writingDirection: "ltr" }}
          >
            {owner.email}
          </Text>
        </View>
        <SettingsGroup>
          <SettingsRow title={t("account")} icon="agent" onPress={() => router.push("/account")} />
          <SettingsRow title={t("models")} icon="settings" onPress={() => router.push("/models")} />
          <SettingsRow
            title={t("capabilities")}
            icon="layers"
            onPress={() => router.push("/integrations")}
          />
          <SettingsRow title={t("voice")} icon="activity" onPress={() => router.push("/voice")} />
        </SettingsGroup>
        <SettingsGroup>
          <SettingsRow
            title={t("sh_appearance")}
            value={mode === "dark" ? t("sh_dark") : t("sh_light")}
            icon="settings"
            onPress={() => setMode(mode === "dark" ? "light" : "dark")}
          />
          <SettingsRow title={t("server")} icon="globe" onPress={() => router.push("/server")} />
        </SettingsGroup>
      </ScrollView>
    </View>
  );
}
