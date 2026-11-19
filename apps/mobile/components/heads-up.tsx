// The heads-up, as Web's HeadsUp: an agent's answer that arrives in another chat shows at the
// top for 5.2 s with «رد»; a tap opens that chat; a swipe up, or the time, hides it. Mute,
// archive, the owner's quiet hours and an agent's in-app rule suppress it (Q4, Q47); an urgent
// attention item always shows.
import type { Event } from "@lonora/contracts";
import type { QuietHours } from "@lonora/core";
import { useGlobalSearchParams, usePathname } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { Animated, AppState, PanResponder, Pressable, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "../lib/api";
import { attentionLabels } from "../lib/attention-labels";
import { subscribeOwnerEvents } from "../lib/events";
import { attentionBanner, type Banner, messageBanner } from "../lib/heads-up";
import { useLists } from "../lib/lists-state";
import { useSession } from "../lib/session";
import { useShellData } from "../lib/shell-data";
import { useTheme } from "../lib/theme";
import { useOpenChat } from "./shell/chat-list";
import { RowAvatar } from "./shell/kit";

/**
 * The owner's quiet hours and the agents whose in-app rule is off. Read at sign-in, again when
 * the app returns to the foreground, and at most once a minute on the shell's poll (`tick`),
 * so a change made on Web, or a read that failed offline, is not kept for the whole session.
 */
function useDeliveryRules(ownerId: string | undefined, tick: unknown) {
  const [quiet, setQuiet] = useState<QuietHours | null>(null);
  const [off, setOff] = useState<ReadonlySet<string>>(new Set());
  const [revision, setRevision] = useState(0);
  const lastRead = useRef(0);
  useEffect(() => {
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") setRevision((value) => value + 1);
    });
    return () => subscription.remove();
  }, []);
  // biome-ignore lint/correctness/useExhaustiveDependencies: `tick` is the shell's poll
  useEffect(() => {
    if (Date.now() - lastRead.current >= 60_000) setRevision((value) => value + 1);
  }, [tick]);
  // biome-ignore lint/correctness/useExhaustiveDependencies: `revision` asks for a fresh read
  useEffect(() => {
    if (!ownerId) return;
    lastRead.current = Date.now();
    let live = true;
    api
      .get<{ reach_me: QuietHours }>("/owner/profile")
      .then((profile) => live && setQuiet(profile.reach_me))
      .catch(() => undefined);
    api
      .get<Record<string, { in_app: boolean }>>("/agents/notifications")
      .then(
        (rules) =>
          live &&
          setOff(
            new Set(
              Object.entries(rules)
                .filter(([, rule]) => !rule.in_app)
                .map(([id]) => id),
            ),
          ),
      )
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [ownerId, revision]);
  return { quiet, off };
}

export function HeadsUp() {
  const { owner, server, t, rtl } = useSession();
  const { c } = useTheme();
  const insets = useSafeAreaInsets();
  const data = useShellData();
  const lists = useLists();
  const openChat = useOpenChat();
  const rules = useDeliveryRules(owner?.id, data.inbox);
  const pathname = usePathname();
  const params = useGlobalSearchParams<{ id?: string | string[]; groupId?: string | string[] }>();
  const first = (value?: string | string[]) => (Array.isArray(value) ? value[0] : value);
  const current =
    pathname === "/thread"
      ? first(params.id)
      : pathname === "/group-thread"
        ? data.groups.find((group) => group.id === first(params.groupId))?.state?.thread_id
        : undefined;
  const [banner, setBanner] = useState<(Banner & { serial: number }) | null>(null);
  const offset = useRef(new Animated.Value(-160)).current;
  // News is what arrives after this owner signed in (or the app opened).
  const openedAt = useRef(Date.now());
  const serial = useRef(0);
  const announced = useRef(new Set<string>());
  const live = useRef({ rows: lists.rows, agents: data.agents, current, rules, t });
  live.current = { rows: lists.rows, agents: data.agents, current, rules, t };

  const hide = useCallback(() => {
    const shown = serial.current;
    // A banner that arrives while this one slides out is not cleared with it.
    Animated.timing(offset, { toValue: -160, duration: 220, useNativeDriver: true }).start(
      ({ finished }) => {
        if (finished && serial.current === shown) setBanner(null);
      },
    );
  }, [offset]);
  const show = useCallback(
    (next: Banner) => {
      serial.current += 1;
      setBanner({ ...next, serial: serial.current });
      offset.setValue(-160);
      Animated.spring(offset, { toValue: 0, useNativeDriver: true }).start();
    },
    [offset],
  );
  useEffect(() => {
    if (!banner) return;
    const timer = setTimeout(hide, 5200);
    return () => clearTimeout(timer);
  }, [banner, hide]);

  useEffect(() => {
    openedAt.current = Date.now();
    announced.current = new Set();
    if (!owner) setBanner(null);
  }, [owner]);

  // Answers in other chats, from the owner's live stream.
  useEffect(() => {
    if (!owner) return;
    return subscribeOwnerEvents(
      server,
      (event: Event) => {
        const context = live.current;
        const next = messageBanner(event, {
          rows: context.rows,
          agents: context.agents,
          current: context.current,
          quiet: context.rules.quiet,
          off: context.rules.off,
          // After a reconnect the stream replays what was missed in the background: only an
          // answer from the last moments is news (push covers the rest).
          openedAt: Math.max(openedAt.current, Date.now() - 15_000),
          now: new Date(),
          newMessage: context.t("newMessage"),
        });
        if (next) show(next);
      },
      () => undefined,
    );
  }, [owner, server, show]);

  // Urgent attention items, from the shell's attention list.
  useEffect(() => {
    for (const item of data.attention) {
      if (announced.current.has(item.id)) continue;
      announced.current.add(item.id);
      const labels = Object.fromEntries(
        Object.entries(attentionLabels).map(([code, label]) => [code, live.current.t(label)]),
      );
      const next = attentionBanner(item, {
        rows: live.current.rows,
        openedAt: openedAt.current,
        labels,
      });
      if (next) show(next);
    }
  }, [data.attention, show]);

  const swipe = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, gesture) => gesture.dy < -8,
      onPanResponderRelease: (_, gesture) => {
        if (gesture.dy < -24) hide();
      },
    }),
  ).current;
  if (!banner || !owner) return null;
  const open = () => {
    hide();
    void openChat(banner.row);
  };
  return (
    <Animated.View
      key={banner.serial}
      testID="heads-up"
      role="status"
      accessibilityLiveRegion="polite"
      {...swipe.panHandlers}
      style={{
        position: "absolute",
        top: insets.top + 6,
        left: 10,
        right: 10,
        zIndex: 50,
        transform: [{ translateY: offset }],
      }}
    >
      <View
        style={{
          flexDirection: rtl ? "row-reverse" : "row",
          alignItems: "center",
          gap: 10,
          padding: 10,
          borderRadius: 18,
          backgroundColor: c.raised,
          borderWidth: 1,
          borderColor: c.line,
          shadowColor: "#000",
          shadowOpacity: 0.3,
          shadowRadius: 12,
          shadowOffset: { width: 0, height: 4 },
          elevation: 8,
        }}
      >
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`${banner.row.name}: ${banner.text}`}
          onPress={open}
          style={{
            flex: 1,
            flexDirection: rtl ? "row-reverse" : "row",
            alignItems: "center",
            gap: 10,
            minWidth: 0,
          }}
        >
          <RowAvatar row={banner.row} agents={data.agents} size={40} />
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text
              numberOfLines={1}
              style={{
                color: c.text,
                fontSize: 15,
                fontWeight: "700",
                textAlign: rtl ? "right" : "left",
              }}
            >
              {banner.row.name}
            </Text>
            <Text
              numberOfLines={2}
              style={{
                color: c.muted,
                fontSize: 13,
                lineHeight: 18,
                writingDirection: "auto",
                textAlign: rtl ? "right" : "left",
              }}
            >
              {banner.text}
            </Text>
          </View>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          onPress={open}
          style={{
            paddingHorizontal: 14,
            paddingVertical: 8,
            borderRadius: 14,
            borderWidth: 1,
            borderColor: c["line-strong"],
          }}
        >
          <Text style={{ color: c.text, fontSize: 13, fontWeight: "600" }}>{t("reply")}</Text>
        </Pressable>
      </View>
    </Animated.View>
  );
}
