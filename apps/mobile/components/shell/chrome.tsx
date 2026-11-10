// The phone's chrome: the glass top bar (chats header with its search pill and «+», the selection
// toolbar), bare inner pages with a floating back, the floating tab bar with its badges, the
// network strip and the update/permission places. Notifications' permission flow stays hidden (Q10).
import { useRouter } from "expo-router";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { Animated, Pressable, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useSession } from "../../lib/session";
import { radius, useTheme } from "../../lib/theme";
import { Icon, type IconName } from "./icon";

export type RootTab = "chats" | "updates" | "tasks" | "settings";
export const ROOTS: RootTab[] = ["chats", "updates", "tasks", "settings"];
const icons: Record<RootTab, IconName> = { chats: "chat", updates: "bell", tasks: "task", settings: "settings" };
export const rootPath = (root: RootTab) => (root === "chats" ? "/" : `/${root}`);

/** A glass circle (the reference's `.icon` on bare pages). */
export function CircleButton({ icon, label, onPress, active }: { icon: IconName; label: string; onPress: () => void; active?: boolean }) {
  const { c } = useTheme();
  const { rtl } = useSession();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={({ pressed }) => ({ width: 42, height: 42, borderRadius: 21, alignItems: "center", justifyContent: "center", backgroundColor: active || pressed ? c.lens : c["glass-bar"], borderWidth: 1, borderColor: c["glass-line"] })}
    >
      <View style={{ transform: [{ scaleX: icon === "back" && rtl ? -1 : 1 }] }}>
        <Icon name={icon} size={22} color={c.text} />
      </View>
    </Pressable>
  );
}

/** The chats header: «Lonora», the search pill that expands over the title, and «+». */
export function ChatsHeader({
  expanded,
  query,
  onQuery,
  onExpand,
  onClear,
  onNewChat,
}: {
  expanded: boolean;
  query: string;
  onQuery: (query: string) => void;
  onExpand: () => void;
  onClear: () => void;
  onNewChat: () => void;
}) {
  const { c } = useTheme();
  const { t, rtl } = useSession();
  const input = useRef<TextInput>(null);
  useEffect(() => {
    if (expanded) input.current?.focus();
  }, [expanded]);
  const dir = rtl ? "row-reverse" : "row";
  return (
    <View style={{ height: 60, flexDirection: dir, alignItems: "center", gap: 6, paddingHorizontal: 10 }}>
      {!expanded ? (
        <Text accessibilityRole="header" style={{ color: c.text, fontSize: 28, fontWeight: "700", flexShrink: 0 }}>
          Lonora
        </Text>
      ) : null}
      <View style={{ flex: 1, height: 42, borderRadius: radius.pill, backgroundColor: c.fill, flexDirection: dir, alignItems: "center", maxWidth: expanded ? undefined : 520, marginStart: expanded ? 0 : 6 }}>
        <View style={{ paddingHorizontal: 13 }}>
          <Icon name="search" size={18} color={c.muted} />
        </View>
        <TextInput
          ref={input}
          accessibilityRole="search"
          accessibilityLabel={t("sh_searchPh")}
          placeholder={t("sh_searchPh")}
          placeholderTextColor={c.muted}
          value={query}
          autoCorrect={false}
          onFocus={onExpand}
          onChangeText={onQuery}
          style={{ flex: 1, height: 42, color: c.text, fontSize: 14, textAlign: rtl ? "right" : "left", writingDirection: rtl ? "rtl" : "ltr", padding: 0, outlineStyle: "none" } as never}
        />
        {expanded || query ? (
          <Pressable accessibilityRole="button" accessibilityLabel={t("sh_closeSearch")} onPress={onClear} style={{ width: 30, height: 30, marginHorizontal: 6, alignItems: "center", justifyContent: "center" }}>
            <Icon name="close" size={16} color={c.muted} />
          </Pressable>
        ) : null}
      </View>
      {!expanded ? <CircleButton icon="plus" label={t("sh_newChat")} onPress={onNewChat} /> : null}
    </View>
  );
}

/** The top bar: absolute, content scrolls beneath; `bare` pages carry only floating circles. */
export function TopBar({ children, solid = false }: { children: ReactNode; solid?: boolean }) {
  const { c } = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <View style={{ paddingTop: insets.top, backgroundColor: solid ? c.bg : c.glass, borderBottomWidth: solid ? 1 : 0, borderBottomColor: c.line, zIndex: 20 }}>{children}</View>
  );
}

/** A bare inner page's header: a floating back at the start, optional actions at the end, then the large title. */
export function PageHeader({ title, actions }: { title: string; actions?: ReactNode }) {
  const { c } = useTheme();
  const { t, rtl } = useSession();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  return (
    <View style={{ paddingTop: insets.top + 6, paddingHorizontal: 12, gap: 8 }}>
      <View style={{ flexDirection: rtl ? "row-reverse" : "row", justifyContent: "space-between" }}>
        <CircleButton icon="back" label={t("sh_back")} onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))} />
        <View style={{ flexDirection: rtl ? "row-reverse" : "row", gap: 8 }}>{actions}</View>
      </View>
      <Text accessibilityRole="header" style={{ color: c.text, fontSize: 28, fontWeight: "700", paddingHorizontal: 4, paddingVertical: 6, textAlign: rtl ? "right" : "left" }}>
        {title}
      </Text>
    </View>
  );
}

/** Telegram-style floating tab bar: a glass pill, a lens under the active tab, badges. */
export function FloatingTabBar({ section, chatsBadge, updatesDot, onTab }: { section: RootTab; chatsBadge: number; updatesDot: boolean; onTab: (root: RootTab) => void }) {
  const { c } = useTheme();
  const { t, rtl } = useSession();
  const insets = useSafeAreaInsets();
  const [barWidth, setBarWidth] = useState(0);
  const tabWidth = (barWidth - 10) / ROOTS.length;
  const lens = useRef(new Animated.Value(0)).current;
  const labels: Record<RootTab, string> = { chats: t("sh_chats"), updates: t("sh_updates"), tasks: t("sh_tasks"), settings: t("sh_settings") };
  const order = rtl ? [...ROOTS].reverse() : ROOTS;
  useEffect(() => {
    Animated.spring(lens, { toValue: order.indexOf(section), useNativeDriver: false, bounciness: 6, speed: 18 }).start();
  }, [section, lens, order]);
  return (
    <View pointerEvents="box-none" style={{ position: "absolute", left: 0, right: 0, bottom: Math.max(insets.bottom, 12), alignItems: "center", zIndex: 30 }}>
      <View
        accessibilityLabel={t("sh_mainNav")}
        role="navigation"
        onLayout={(event) => setBarWidth(event.nativeEvent.layout.width)}
        style={{ width: "88%", maxWidth: 420, height: 66, borderRadius: radius.bar, flexDirection: "row", padding: 5, backgroundColor: c["glass-bar"], borderWidth: 1, borderColor: c["glass-line"] }}
      >
        <Animated.View
          pointerEvents="none"
          style={{
            position: "absolute",
            top: 5,
            bottom: 5,
            width: tabWidth > 0 ? tabWidth : 0,
            left: lens.interpolate({ inputRange: [0, 1, 2, 3], outputRange: [0, 1, 2, 3].map((i) => 5 + i * Math.max(tabWidth, 0)) }),
            borderRadius: 28,
            backgroundColor: c.lens,
          }}
        />
        {order.map((root) => {
          const active = section === root;
          const badge = root === "chats" ? chatsBadge : 0;
          const dot = root === "updates" && updatesDot;
          return (
            <Pressable
              key={root}
              accessibilityRole="button"
              aria-current={active ? "page" : undefined}
              accessibilityState={{ selected: active }}
              accessibilityLabel={labels[root] + (dot ? ` · ${t("sh_newBadge")}` : badge ? ` · ${badge}` : "")}
              testID={`tab-${root}`}
              onPress={() => onTab(root)}
              style={{ flex: 1, alignItems: "center", justifyContent: "center", gap: 1 }}
            >
              <View style={{ height: 28, alignItems: "center", justifyContent: "center" }}>
                <Icon name={icons[root]} size={24} color={active ? c.text : c.muted} />
                {dot ? (
                  <View style={{ position: "absolute", top: 1, right: -3, width: 8, height: 8, borderRadius: 4, backgroundColor: c.accent, borderWidth: 2, borderColor: c.surface }} />
                ) : badge ? (
                  <View style={{ position: "absolute", top: -4, right: -10, minWidth: 18, height: 18, paddingHorizontal: 5, borderRadius: 9, backgroundColor: c.accent, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: c.surface }}>
                    <Text style={{ color: c["on-accent"], fontSize: 11, fontWeight: "700" }}>{badge}</Text>
                  </View>
                ) : null}
              </View>
              <Text style={{ color: active ? c.text : c.muted, fontSize: 12, fontWeight: active ? "600" : "400" }}>{labels[root]}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}
