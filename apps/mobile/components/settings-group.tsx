// Native grouped-cell structure adapted from the template; see NOTICE.
import type { ReactNode } from "react";
import { Children, Fragment, isValidElement } from "react";
import { Pressable, StyleSheet, Switch, Text, View } from "react-native";
import { useSession } from "../lib/session";
import { NativeSymbol, type SymbolName } from "./native-symbol";
import { colors } from "./ui";
export function SettingsGroup({
  title,
  children,
  footer,
}: {
  title?: string;
  children: ReactNode;
  footer?: string;
}) {
  const { rtl } = useSession();
  const rows = Children.toArray(children).filter(isValidElement);
  return (
    <View style={{ gap: 7 }}>
      {title ? (
        <Text
          accessibilityRole="header"
          style={{
            color: colors.secondary,
            fontSize: 13,
            paddingHorizontal: 16,
            textAlign: rtl ? "right" : "left",
          }}
        >
          {title}
        </Text>
      ) : null}
      <View style={styles.card}>
        {rows.map((row, index) => (
          <Fragment key={row.key}>
            {index ? (
              <View
                style={{
                  height: StyleSheet.hairlineWidth,
                  backgroundColor: colors.border,
                  marginHorizontal: 16,
                }}
              />
            ) : null}
            {row.type === SettingsRow || row.type === SettingsSwitch ? (
              row
            ) : (
              <View style={{ padding: 16 }}>{row}</View>
            )}
          </Fragment>
        ))}
      </View>
      {footer ? (
        <Text
          style={{
            color: colors.secondary,
            fontSize: 13,
            paddingHorizontal: 16,
            lineHeight: 19,
            textAlign: rtl ? "right" : "left",
          }}
        >
          {footer}
        </Text>
      ) : null}
    </View>
  );
}
export function SettingsRow({
  title,
  detail,
  value,
  icon,
  trailing,
  onPress,
  destructive = false,
  disabled = false,
}: {
  title: string;
  detail?: string;
  value?: string;
  icon?: SymbolName;
  trailing?: ReactNode;
  onPress?: () => void;
  destructive?: boolean;
  disabled?: boolean;
}) {
  const { rtl } = useSession();
  const content = (
    <>
      {icon ? (
        <NativeSymbol name={icon} color={destructive ? colors.error : colors.secondary} />
      ) : null}
      <View style={{ flex: 1, gap: 3 }}>
        <Text
          style={{
            color: destructive ? colors.error : colors.foreground,
            fontSize: 17,
            textAlign: rtl ? "right" : "left",
          }}
        >
          {title}
        </Text>
        {detail ? (
          <Text
            style={{
              color: colors.secondary,
              fontSize: 14,
              lineHeight: 20,
              writingDirection: "auto",
              textAlign: rtl ? "right" : "left",
            }}
          >
            {detail}
          </Text>
        ) : null}
      </View>
      {value ? (
        <Text
          numberOfLines={1}
          style={{
            maxWidth: "48%",
            color: colors.secondary,
            fontSize: 16,
            writingDirection: "auto",
          }}
        >
          {value}
        </Text>
      ) : null}
      {trailing}
      {onPress ? (
        <View style={{ transform: [{ scaleX: rtl ? -1 : 1 }] }}>
          <NativeSymbol name="chevron" size={16} color={colors.secondary} />
        </View>
      ) : null}
    </>
  );
  const layout = [
    styles.row,
    {
      flexDirection: rtl ? ("row-reverse" as const) : ("row" as const),
      opacity: disabled ? 0.4 : 1,
    },
  ];
  return onPress ? (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={title}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [...layout, pressed && { backgroundColor: colors.accent }]}
    >
      {content}
    </Pressable>
  ) : (
    <View style={layout}>{content}</View>
  );
}
export function SettingsSwitch({
  label,
  value,
  onChange,
  disabled = false,
}: {
  label: string;
  value: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  const { rtl } = useSession();
  return (
    <View style={[styles.row, { flexDirection: rtl ? "row-reverse" : "row" }]}>
      <Text
        style={{
          flex: 1,
          color: colors.foreground,
          fontSize: 17,
          textAlign: rtl ? "right" : "left",
        }}
      >
        {label}
      </Text>
      <Switch
        accessibilityLabel={label}
        value={value}
        onValueChange={onChange}
        disabled={disabled}
        trackColor={{ true: colors.success }}
      />
    </View>
  );
}
const styles = StyleSheet.create({
  card: { borderRadius: 16, overflow: "hidden", backgroundColor: colors.muted },
  row: { minHeight: 52, paddingHorizontal: 16, paddingVertical: 12, alignItems: "center", gap: 12 },
});
