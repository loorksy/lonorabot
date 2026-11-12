// يحتاج انتباهك (mandate 11.7): what needs the owner across all agents. A dot on the tab says something is new.

import { Redirect } from "expo-router";
import { ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { AttentionView } from "../../components/attention-view";
import { colors, Loading } from "../../components/ui";
import { useSession } from "../../lib/session";
import { useShellData } from "../../lib/shell-data";
import { useTheme } from "../../lib/theme";

export default function Updates() {
  const { ready, owner, t, rtl } = useSession();
  const { c } = useTheme();
  const data = useShellData();
  const insets = useSafeAreaInsets();
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <Text
        accessibilityRole="header"
        style={{
          color: c.text,
          fontSize: 28,
          fontWeight: "700",
          paddingHorizontal: 20,
          paddingTop: insets.top + 14,
          paddingBottom: 6,
          textAlign: rtl ? "right" : "left",
        }}
      >
        {t("sh_updates")}
      </Text>
      <ScrollView contentContainerStyle={{ paddingBottom: 130 }}>
        {/* The attention view keeps the inbox's own (dark) palette until phase 4 re-skins it. */}
        <View
          style={{
            margin: 16,
            borderRadius: 16,
            overflow: "hidden",
            backgroundColor: colors.background,
          }}
        >
          <AttentionView agents={data.agents} />
        </View>
      </ScrollView>
    </View>
  );
}
