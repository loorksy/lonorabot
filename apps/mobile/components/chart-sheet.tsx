import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  BackHandler,
  Keyboard,
  PanResponder,
  Platform,
  Pressable,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { ChartWorkspace, type ChartWorkspaceProps } from "../app/charts";
import { useSession } from "../lib/session";
import { useVoiceSession } from "../lib/voice-session";
import { HeaderButton } from "./header-button";
import { NativeSymbol } from "./native-symbol";
import { colors } from "./ui";

type Scope = Pick<ChartWorkspaceProps, "threadId" | "botId" | "chartId">;
const Context = createContext<{ open: (scope: Scope) => void; close: () => void }>({
  open: () => {},
  close: () => {},
});
export const useChartSheet = () => useContext(Context);

/** Sheet state is local presentation; hiding it never cancels a Run or call. */
export function ChartSheetProvider({ children }: { children: ReactNode }) {
  const { t, rtl, owner } = useSession();
  const call = useVoiceSession();
  const insets = useSafeAreaInsets();
  const { height, width } = useWindowDimensions();
  const [scope, setScope] = useState<Scope | null>(null);
  const [mode, setMode] = useState<"rest" | "expanded" | "minimized">("rest");
  const close = useCallback(() => setScope(null), []);
  const back = () => {
    if (mode === "expanded") setMode("rest");
    else close();
    return true;
  };
  useEffect(() => {
    if (!owner) setScope(null);
  }, [owner]);
  useEffect(() => {
    if (!scope) return;
    const listener = BackHandler.addEventListener("hardwareBackPress", back);
    if (Platform.OS !== "web") return () => listener.remove();
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented) {
        event.preventDefault();
        back();
      }
    };
    window.addEventListener("keydown", handleEscape);
    return () => {
      listener.remove();
      window.removeEventListener("keydown", handleEscape);
    };
  });
  useEffect(() => {
    if (!scope) return;
    const listener = Keyboard.addListener("keyboardDidShow", () => setMode("minimized"));
    return () => listener.remove();
  }, [scope]);
  const drag = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: (_, gesture) =>
          Math.abs(gesture.dy) > 12 && Math.abs(gesture.dy) > Math.abs(gesture.dx),
        onPanResponderRelease: (_, gesture) => {
          if (gesture.dy < -45) setMode("expanded");
          if (gesture.dy > 65) {
            if (mode === "expanded") setMode("rest");
            else close();
          }
        },
      }),
    [mode, close],
  );
  const controls = (
    <>
      <HeaderButton
        label={t(mode === "expanded" ? "chartCollapse" : "chartExpand")}
        onPress={() => setMode(mode === "expanded" ? "rest" : "expanded")}
      >
        <NativeSymbol name="chart" />
      </HeaderButton>
      <HeaderButton label={t("chartMinimize")} onPress={() => setMode("minimized")}>
        <NativeSymbol name="minimize" />
      </HeaderButton>
      <HeaderButton label={t("close")} onPress={close}>
        <NativeSymbol name="close" />
      </HeaderButton>
    </>
  );
  return (
    <Context.Provider
      value={{
        open: (next) => {
          Keyboard.dismiss();
          if (call.origin) call.minimize(true);
          setScope(next);
          setMode("rest");
        },
        close,
      }}
    >
      {children}
      {scope && owner ? (
        <View pointerEvents="box-none" style={{ position: "absolute", inset: 0, zIndex: 80 }}>
          {mode === "minimized" ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={t("chartReopen")}
              onPress={() => setMode("rest")}
              style={{
                position: "absolute",
                bottom: insets.bottom + 80,
                alignSelf: "center",
                backgroundColor: colors.accent,
                borderRadius: 22,
                padding: 16,
              }}
            >
              <Text style={{ color: colors.foreground }}>{t("chartReopen")}</Text>
            </Pressable>
          ) : null}
          <View
            accessibilityViewIsModal={mode === "expanded" && !call.origin}
            importantForAccessibility={mode === "minimized" ? "no-hide-descendants" : "auto"}
            style={{
              display: mode === "minimized" ? "none" : "flex",
              position: "absolute",
              bottom: 0,
              right: 0,
              left: width >= 900 && mode !== "expanded" ? width * 0.45 : 0,
              height:
                mode === "expanded"
                  ? height - insets.top - (call.origin ? 58 : 0)
                  : Math.min(height * 0.7, height - insets.top - 60),
              paddingBottom: insets.bottom,
              borderTopLeftRadius: 24,
              borderTopRightRadius: 24,
              borderWidth: 1,
              borderColor: colors.border,
              backgroundColor: colors.background,
              overflow: "hidden",
            }}
          >
            <View
              {...drag.panHandlers}
              style={{
                flexDirection: rtl ? "row-reverse" : "row",
                alignItems: "center",
                paddingHorizontal: 12,
                minHeight: 56,
              }}
            >
              <Text
                accessibilityRole="header"
                style={{
                  flex: 1,
                  color: colors.foreground,
                  fontWeight: "600",
                  textAlign: rtl ? "right" : "left",
                }}
              >
                {t("charts")}
              </Text>
              {controls}
            </View>
            <ChartWorkspace
              key={`${scope.threadId ?? ""}:${scope.botId ?? ""}:${scope.chartId ?? ""}`}
              {...scope}
              embedded
              onEscape={back}
            />
          </View>
        </View>
      ) : null}
    </Context.Provider>
  );
}
