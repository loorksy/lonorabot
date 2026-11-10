// المستجدات: what needs the owner (the attention inbox). A dot on the tab says something is new.
import { Redirect } from "expo-router";
import { ScrollView, Text, View } from "react-native";
import { AttentionInbox } from "../../components/attention-inbox";
import { Empty } from "../../components/shell/kit";
import { Loading } from "../../components/ui";
import { api } from "../../lib/api";
import { useSession } from "../../lib/session";
import { useShellData } from "../../lib/shell-data";
import { useTheme } from "../../lib/theme";

export default function Updates() {
  const { ready, owner, t, rtl } = useSession();
  const { c } = useTheme();
  const data = useShellData();
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <Text accessibilityRole="header" style={{ color: c.text, fontSize: 28, fontWeight: "700", paddingHorizontal: 20, paddingTop: 14, paddingBottom: 6, textAlign: rtl ? "right" : "left" }}>
        {t("sh_updates")}
      </Text>
      <ScrollView contentContainerStyle={{ paddingBottom: 130 }}>
        {data.attention.length ? (
          <AttentionInbox
            items={data.attention}
            agents={data.agents}
            onSeen={async (id) => {
              await api.post("/attention/seen", { notification_id: id });
              data.clearAttention(id);
            }}
          />
        ) : (
          <Empty icon="bell">{t("sh_browseEmpty")}</Empty>
        )}
      </ScrollView>
    </View>
  );
}
