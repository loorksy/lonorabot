// The network strip under the top bar: «لا يوجد اتصال بالإنترنت» with the count of messages waiting
// in this device's outbox (Q6), then «تم استعادة الاتصال» for a moment once a read succeeds again.
import { useEffect, useRef, useState } from "react";
import { Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLists } from "../../lib/lists-state";
import { useSession } from "../../lib/session";
import { useShellData } from "../../lib/shell-data";
import { useTheme } from "../../lib/theme";

export function NetworkStrip() {
  const { c } = useTheme();
  const { t, rtl, locale } = useSession();
  const data = useShellData();
  const lists = useLists();
  const insets = useSafeAreaInsets();
  const [restored, setRestored] = useState(false);
  const was = useRef(false);
  useEffect(() => {
    if (data.offline) {
      was.current = true;
      setRestored(false);
      return;
    }
    if (!was.current) return;
    was.current = false;
    setRestored(true);
    const timer = setTimeout(() => setRestored(false), 2200);
    return () => clearTimeout(timer);
  }, [data.offline]);
  if (!data.offline && !restored) return null;
  const queued = lists.queued;
  const waiting =
    queued > 0
      ? locale === "ar"
        ? queued === 1
          ? "رسالة واحدة تنتظر"
          : queued === 2
            ? "رسالتان تنتظران"
            : queued <= 10
              ? `${queued} رسائل تنتظر`
              : `${queued} رسالة تنتظر`
        : queued === 1
          ? "one message waiting"
          : `${queued} messages waiting`
      : "";
  return (
    <View
      role="status"
      accessibilityLiveRegion="polite"
      testID="network-strip"
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 40,
        minHeight: 30,
        paddingHorizontal: 14,
        paddingTop: insets.top + 6,
        paddingBottom: 6,
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: data.offline ? c["danger-fill"] : c.accent,
      }}
    >
      <Text
        style={{
          color: data.offline ? "#fff" : c["on-accent"],
          fontSize: 12,
          fontWeight: "600",
          textAlign: rtl ? "right" : "left",
        }}
      >
        {data.offline ? `${t("sh_netOff")}${waiting ? ` · ${waiting}` : ""}` : t("sh_netBack")}
      </Text>
    </View>
  );
}
