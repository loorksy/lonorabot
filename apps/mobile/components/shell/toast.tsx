// The reference's toast: a glass pill above the tab bar; one at a time; «تراجع» as its action.
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
import { Animated, Pressable, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useSession } from "../../lib/session";
import { radius, useTheme } from "../../lib/theme";

type ToastOptions = {
  type?: "success" | "error" | "warn";
  action?: { label: string; run: () => void };
};
type Item = { id: number; message: string } & ToastOptions;
type Show = (message: string, options?: ToastOptions) => void;
const Context = createContext<Show>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const { c } = useTheme();
  const { rtl } = useSession();
  const insets = useSafeAreaInsets();
  const [item, setItem] = useState<Item | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const opacity = useRef(new Animated.Value(0)).current;
  const next = useRef(0);
  const show = useCallback<Show>((message, options = {}) => {
    clearTimeout(timer.current);
    next.current += 1;
    setItem({ id: next.current, message, ...options });
    timer.current = setTimeout(() => setItem(null), options.action ? 6000 : 3200);
  }, []);
  useEffect(() => {
    Animated.timing(opacity, {
      toValue: item ? 1 : 0,
      duration: 180,
      useNativeDriver: true,
    }).start();
  }, [item, opacity]);
  useEffect(() => () => clearTimeout(timer.current), []);
  const value = useMemo(() => show, [show]);
  const tone =
    item?.type === "error"
      ? c.red
      : item?.type === "success"
        ? c["accent-ink"]
        : item?.type === "warn"
          ? c.amber
          : c.text;
  return (
    <Context.Provider value={value}>
      {children}
      <View
        pointerEvents="box-none"
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: insets.bottom + 92,
          alignItems: "center",
          zIndex: 60,
        }}
      >
        {item ? (
          <Animated.View
            role="status"
            accessibilityLiveRegion="polite"
            style={{
              opacity,
              flexDirection: rtl ? "row-reverse" : "row",
              alignItems: "center",
              gap: 12,
              maxWidth: "90%",
              paddingVertical: 11,
              paddingHorizontal: 16,
              borderRadius: radius.md,
              backgroundColor: c["glass-pop"],
              borderWidth: 1,
              borderColor: c["glass-line"],
            }}
          >
            <Text
              style={{
                color: tone,
                fontSize: 14,
                flexShrink: 1,
                textAlign: rtl ? "right" : "left",
              }}
            >
              {item.message}
            </Text>
            {item.action ? (
              <Pressable
                accessibilityRole="button"
                onPress={() => {
                  const run = item.action?.run;
                  setItem(null);
                  run?.();
                }}
              >
                <Text style={{ color: c["accent-ink"], fontSize: 14, fontWeight: "600" }}>
                  {item.action.label}
                </Text>
              </Pressable>
            ) : null}
          </Animated.View>
        ) : null}
      </View>
    </Context.Provider>
  );
}

export const useToast = () => useContext(Context);
