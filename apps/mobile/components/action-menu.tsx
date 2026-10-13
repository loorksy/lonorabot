// Native sheets where available, with a portable modal fallback for Expo Web/Android.
import { useEffect, useRef } from "react";
import {
  ActionSheetIOS,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { useSession } from "../lib/session";
import { NativeSymbol, type SymbolName } from "./native-symbol";
import { colors } from "./ui";

export type MenuAction = {
  label: string;
  icon: SymbolName;
  onPress: () => void;
  destructive?: boolean;
  disabled?: boolean;
};
export function ActionMenu({
  visible,
  onClose,
  actions,
}: {
  visible: boolean;
  onClose: () => void;
  actions: MenuAction[];
}) {
  const { rtl, t } = useSession();
  const { height } = useWindowDimensions();
  const latest = useRef({ actions, onClose, t });
  latest.current = { actions, onClose, t };
  useEffect(() => {
    if (!visible || Platform.OS !== "ios") return;
    const { actions, onClose, t } = latest.current;
    const destructiveIndex = actions.findIndex((item) => item.destructive);
    ActionSheetIOS.showActionSheetWithOptions(
      {
        options: [...actions.map((item) => item.label), t("back")],
        cancelButtonIndex: actions.length,
        destructiveButtonIndex: destructiveIndex < 0 ? undefined : destructiveIndex,
        disabledButtonIndices: actions.flatMap((item, index) => (item.disabled ? [index] : [])),
        userInterfaceStyle: "dark",
      },
      (index) => {
        onClose();
        actions[index]?.onPress();
      },
    );
  }, [visible]);
  if (Platform.OS === "ios") return null;
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View
        style={{
          flex: 1,
          backgroundColor: colors.overlay,
          justifyContent: "flex-end",
          padding: 12,
        }}
      >
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("back")}
          onPress={onClose}
          style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0 }}
        />
        <View
          accessibilityRole="menu"
          accessibilityViewIsModal
          style={{
            borderRadius: 18,
            backgroundColor: colors.accent,
            overflow: "hidden",
            marginBottom: 12,
          }}
        >
          <ScrollView style={{ maxHeight: height * 0.7 }} keyboardShouldPersistTaps="handled">
            {actions.map((action, index) => (
              <Pressable
                key={action.label}
                accessibilityRole="button"
                accessibilityLabel={action.label}
                disabled={action.disabled}
                onPress={() => {
                  onClose();
                  action.onPress();
                }}
                style={({ pressed }) => ({
                  flexDirection: rtl ? "row-reverse" : "row",
                  alignItems: "center",
                  gap: 14,
                  minHeight: 54,
                  paddingHorizontal: 20,
                  backgroundColor: pressed ? colors.muted : "transparent",
                  borderTopWidth: index ? 0.5 : 0,
                  borderTopColor: colors.border,
                  opacity: action.disabled ? 0.4 : 1,
                })}
              >
                <NativeSymbol
                  name={action.icon}
                  color={action.destructive ? colors.error : colors.foreground}
                />
                <Text
                  style={{
                    color: action.destructive ? colors.error : colors.foreground,
                    fontSize: 17,
                  }}
                >
                  {action.label}
                </Text>
              </Pressable>
            ))}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}
