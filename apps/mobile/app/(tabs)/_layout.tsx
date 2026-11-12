// The four root tabs (chats, updates, tasks, settings) under one floating tab bar, with the
// network strip beneath the status bar. Inner pages are stacked above this group.
import { inAttentionView } from "@lonora/contracts";
import { unreadBadgeTotal } from "@lonora/core";
import { Redirect, Tabs, useRouter } from "expo-router";
import { View } from "react-native";
import { FloatingTabBar, ROOTS, type RootTab } from "../../components/shell/chrome";
import { NetworkStrip } from "../../components/shell/network-strip";
import { Loading } from "../../components/ui";
import { useLists } from "../../lib/lists-state";
import { useSession } from "../../lib/session";
import { useShellData } from "../../lib/shell-data";
import { useTheme } from "../../lib/theme";

export default function TabsLayout() {
  const { ready, owner } = useSession();
  const { c } = useTheme();
  const data = useShellData();
  const lists = useLists();
  const router = useRouter();
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <NetworkStrip />
      <Tabs
        screenOptions={{ headerShown: false, sceneStyle: { backgroundColor: c.bg } }}
        tabBar={({ state }) => (
          <FloatingTabBar
            section={ROOTS[state.index] ?? "chats"}
            chatsBadge={unreadBadgeTotal(data.inbox)}
            updatesDot={data.attention.some((item) => inAttentionView(item.code))}
            onTab={(root: RootTab) => {
              lists.end();
              router.navigate(root === "chats" ? "/" : (`/${root}` as never));
            }}
          />
        )}
      >
        <Tabs.Screen name="index" />
        <Tabs.Screen name="updates" />
        <Tabs.Screen name="tasks" />
        <Tabs.Screen name="settings" />
      </Tabs>
    </View>
  );
}
