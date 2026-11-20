import type { ReactNode } from "react";
import { Text, View } from "react-native";
import { useSession } from "../lib/session";
import { useTheme } from "../lib/theme";
import { Icon, type IconName } from "./shell/icon";

/**
 * A fixed card's facts as label/value rows in one tinted box (v38 `.oa-dl`), as on Web: the
 * label on the reading side and wrapping, the value on the other side; a number stays whole
 * and left-to-right.
 */
export function FactRows({
  rows,
  testID,
}: {
  rows: { label: string; value: string; ltr?: boolean }[];
  testID?: string;
}) {
  const { c } = useTheme();
  const { rtl } = useSession();
  if (!rows.length) return null;
  return (
    <View
      testID={testID}
      style={{
        borderRadius: 10,
        backgroundColor: c.fill,
        paddingHorizontal: 10,
        paddingVertical: 2,
      }}
    >
      {rows.map((row, index) => (
        <View
          // biome-ignore lint/suspicious/noArrayIndexKey: a card's rows never reorder
          key={index}
          style={{
            flexDirection: rtl ? "row-reverse" : "row",
            alignItems: "baseline",
            justifyContent: "space-between",
            gap: 12,
            paddingVertical: 6,
            borderBottomWidth: index < rows.length - 1 ? 1 : 0,
            borderBottomColor: c.line,
          }}
        >
          <Text
            style={{
              flexShrink: 1,
              color: c.muted,
              fontSize: 12,
              textAlign: rtl ? "right" : "left",
            }}
          >
            {row.label}
          </Text>
          <Text
            style={{
              flexShrink: 0,
              color: c.text,
              fontSize: 14,
              ...(row.ltr ? { writingDirection: "ltr" as const } : null),
            }}
          >
            {row.value}
          </Text>
        </View>
      ))}
    </View>
  );
}

/**
 * One evidence line of a fixed card (v38 `.od-ev`): its end state, a broker result or the
 * agent's words. Only "ok" carries the success tint; "warn" the amber one; "bad" and "plain"
 * stay neutral, "bad" with a red icon.
 */
export function EvidenceLine({
  tone,
  icon,
  testID,
  children,
}: {
  tone: "ok" | "warn" | "bad" | "plain";
  icon: IconName;
  testID?: string;
  children: ReactNode;
}) {
  const { c } = useTheme();
  const { rtl } = useSession();
  return (
    <View
      testID={testID}
      style={{
        flexDirection: rtl ? "row-reverse" : "row",
        alignItems: "flex-start",
        gap: 6,
        paddingVertical: 8,
        paddingHorizontal: 10,
        borderRadius: 10,
        backgroundColor:
          tone === "ok" ? `${c.accent}17` : tone === "warn" ? `${c.amber}1c` : c.fill,
      }}
    >
      <Icon
        name={icon}
        size={15}
        color={
          tone === "ok"
            ? c["accent-ink"]
            : tone === "warn"
              ? c.amber
              : tone === "bad"
                ? c.red
                : c.muted
        }
      />
      <View style={{ flex: 1, gap: 2 }}>{children}</View>
    </View>
  );
}
