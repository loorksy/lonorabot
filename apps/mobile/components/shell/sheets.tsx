// The sheet system: one bottom sheet at a time (grabber, bar header with in-sheet pages, a
// full-height variant, keyboard avoidance). Bodies are components, so they read the live data.
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Animated,
  BackHandler,
  Keyboard,
  Platform,
  Pressable,
  ScrollView,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useSession } from "../../lib/session";
import { radius, useTheme } from "../../lib/theme";
import { Icon } from "./icon";

export type SheetSpec = {
  id: string;
  title: string;
  body: ReactNode;
  /** The bar header: a back chevron (when `back` is given) and a close, the title centred. */
  bar?: boolean;
  /** Full height (the new-list sheet). */
  full?: boolean;
  back?: () => void;
  /** Keep the body out of the scroll view (it scrolls itself). */
  fixed?: boolean;
};
type Sheets = { open: (spec: SheetSpec) => void; close: () => void; current: string | null };
const Context = createContext<Sheets>({
  open: () => undefined,
  close: () => undefined,
  current: null,
});

export function SheetProvider({ children }: { children: ReactNode }) {
  const { c } = useTheme();
  const { rtl, t } = useSession();
  const insets = useSafeAreaInsets();
  const { height } = useWindowDimensions();
  const [spec, setSpec] = useState<SheetSpec | null>(null);
  const [mounted, setMounted] = useState(false);
  const [keyboard, setKeyboard] = useState(0);
  useEffect(() => {
    const show = Keyboard.addListener(
      Platform.OS === "ios" ? "keyboardWillShow" : "keyboardDidShow",
      (event) => setKeyboard(event.endCoordinates.height),
    );
    const hide = Keyboard.addListener(
      Platform.OS === "ios" ? "keyboardWillHide" : "keyboardDidHide",
      () => setKeyboard(0),
    );
    return () => {
      show.remove();
      hide.remove();
    };
  }, []);
  const slide = useRef(new Animated.Value(0)).current;
  const open = useCallback((next: SheetSpec) => {
    setSpec(next);
    setMounted(true);
  }, []);
  const close = useCallback(() => setSpec(null), []);
  useEffect(() => {
    Animated.timing(slide, {
      toValue: spec ? 1 : 0,
      duration: spec ? 280 : 200,
      useNativeDriver: true,
    }).start(({ finished }) => {
      if (finished && !spec) setMounted(false);
    });
  }, [spec, slide]);
  useEffect(() => {
    if (!spec) return;
    const sub = BackHandler.addEventListener("hardwareBackPress", () => {
      if (spec.back) spec.back();
      else setSpec(null);
      return true;
    });
    return () => sub.remove();
  }, [spec]);
  const value = useMemo(
    () => ({ open, close, current: spec?.id ?? null }),
    [open, close, spec?.id],
  );
  const last = useRef<SheetSpec | null>(null);
  if (spec) last.current = spec;
  const shown = spec ?? last.current;
  // The panel shrinks by the keyboard's height instead of being pushed above the screen.
  const room = height - keyboard - insets.top - 12;
  const panelHeight = shown?.full ? room : undefined;
  return (
    <Context.Provider value={value}>
      {children}
      {mounted && shown ? (
        <View
          style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0, zIndex: 50 }}
          pointerEvents="box-none"
        >
          <Animated.View
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              opacity: slide,
              backgroundColor: "rgba(0,0,0,0.5)",
            }}
          >
            {/* A tap outside closes; the sheet's own buttons are the accessible way. */}
            <Pressable accessible={false} style={{ flex: 1 }} onPress={close} />
          </Animated.View>
          <View
            style={{ flex: 1, justifyContent: "flex-end", paddingBottom: keyboard }}
            pointerEvents="box-none"
          >
            <Animated.View
              role="dialog"
              aria-modal
              accessibilityLabel={shown.title}
              style={{
                height: panelHeight,
                maxHeight: room,
                backgroundColor: c.bg,
                borderTopLeftRadius: radius.lg,
                borderTopRightRadius: radius.lg,
                borderWidth: 1,
                borderBottomWidth: 0,
                borderColor: c["glass-line"],
                paddingBottom: insets.bottom + 12,
                transform: [
                  {
                    translateY: slide.interpolate({ inputRange: [0, 1], outputRange: [height, 0] }),
                  },
                ],
              }}
            >
              {shown.bar ? (
                <View
                  style={{
                    flexDirection: rtl ? "row-reverse" : "row",
                    alignItems: "center",
                    paddingHorizontal: 10,
                    paddingTop: 10,
                    paddingBottom: 6,
                    minHeight: 52,
                  }}
                >
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={shown.back ? t("sh_back") : t("sh_cancel")}
                    onPress={() => (shown.back ? shown.back() : close())}
                    style={{
                      width: 40,
                      height: 40,
                      borderRadius: 20,
                      alignItems: "center",
                      justifyContent: "center",
                      backgroundColor: c.fill,
                    }}
                  >
                    <View
                      style={{
                        transform: [{ scaleX: shown.back && !rtl ? -1 : 1 }],
                      }}
                    >
                      <Icon name={shown.back ? "back" : "close"} size={20} color={c.text} />
                    </View>
                  </Pressable>
                  <Text
                    accessibilityRole="header"
                    numberOfLines={1}
                    style={{
                      flex: 1,
                      textAlign: "center",
                      color: c.text,
                      fontSize: 16,
                      fontWeight: "600",
                    }}
                  >
                    {shown.title}
                  </Text>
                  <View style={{ width: 40 }} />
                </View>
              ) : (
                <View style={{ paddingTop: 8, paddingBottom: 6, alignItems: "center" }}>
                  <View
                    style={{
                      width: 36,
                      height: 5,
                      borderRadius: 3,
                      backgroundColor: c["line-strong"],
                    }}
                  />
                  <Text
                    accessibilityRole="header"
                    style={{
                      color: c.text,
                      fontSize: 17,
                      fontWeight: "700",
                      marginTop: 12,
                      textAlign: "center",
                    }}
                  >
                    {shown.title}
                  </Text>
                </View>
              )}
              {shown.fixed ? (
                <View style={{ flex: shown.full ? 1 : undefined, paddingHorizontal: 16 }}>
                  {shown.body}
                </View>
              ) : (
                <ScrollView
                  keyboardShouldPersistTaps="handled"
                  style={{ flexGrow: 0 }}
                  contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 8, gap: 12 }}
                >
                  {shown.body}
                </ScrollView>
              )}
            </Animated.View>
          </View>
        </View>
      ) : null}
    </Context.Provider>
  );
}

export const useSheets = () => useContext(Context);
