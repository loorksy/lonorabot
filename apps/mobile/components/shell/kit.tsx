// Small pieces of the reference's look: grouped rows, buttons, empty states, the switch, skeletons.
import type { Agent, Group as GroupResource } from "@lonora/contracts";
import type { ChatRow } from "@lonora/core";
import { type ReactNode, useEffect, useRef } from "react";
import { Animated, Pressable, Text, View, type ViewStyle } from "react-native";
import { useSession } from "../../lib/session";
import { radius, useTheme } from "../../lib/theme";
import { BotAvatar } from "../bot-avatar";
import { GroupAvatar } from "../group-avatar";
import { Icon, type IconName } from "./icon";

/** An agent's role line: its title or description; the personal agent's is «مساعدك الشخصي». */
export function useAgentRole() {
  const { t } = useSession();
  return (agent: Agent) =>
    agent.title || agent.description || (agent.role === "personal" ? t("sh_personalRole") : "");
}

/** A group's faces, the lead first (the reference's cluster; Lonora's avatar). */
export function groupMembers(group: GroupResource | undefined, agents: readonly Agent[]) {
  const ids = (group?.payload.member_ids ?? []) as string[];
  const lead = (group?.payload as { lead_agent_id?: unknown } | undefined)?.lead_agent_id;
  const ordered =
    typeof lead === "string" && ids.includes(lead)
      ? [lead, ...ids.filter((id) => id !== lead)]
      : ids;
  return ordered
    .map((id) => agents.find((agent) => agent.id === id))
    .filter((agent): agent is Agent => Boolean(agent));
}

export function AgentFace({
  agent,
  working = false,
  size = 50,
}: {
  agent: Agent;
  working?: boolean;
  size?: number;
}) {
  return (
    <BotAvatar
      tradesOnItsOwn={agent.trades_on_its_own}
      identity={agent.id}
      color={agent.color}
      variant={agent.avatar}
      working={working}
      size={size}
    />
  );
}

export function RowAvatar({
  row,
  agents,
  working = false,
  size = 50,
}: {
  row: ChatRow;
  agents: readonly Agent[];
  working?: boolean;
  size?: number;
}) {
  if (row.agent) return <AgentFace agent={row.agent} working={working} size={size} />;
  return (
    <GroupAvatar
      members={groupMembers(row.group as GroupResource | undefined, agents)}
      size={size}
    />
  );
}

export function IconDisc({ name, size = 44 }: { name: IconName; size?: number }) {
  const { c } = useTheme();
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: c.fill,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Icon name={name} size={size * 0.46} color={c.text} />
    </View>
  );
}

export function GroupBox({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  const { c } = useTheme();
  return (
    <View
      style={[
        {
          backgroundColor: c.surface,
          borderRadius: radius.md,
          overflow: "hidden",
          marginVertical: 8,
        },
        style,
      ]}
    >
      {children}
    </View>
  );
}

export function SectionTitle({ children }: { children: ReactNode }) {
  const { c } = useTheme();
  const { rtl } = useSession();
  return (
    <Text
      accessibilityRole="header"
      style={{
        color: c.muted,
        fontSize: 12,
        fontWeight: "600",
        marginTop: 14,
        marginBottom: 2,
        paddingHorizontal: 4,
        textAlign: rtl ? "right" : "left",
      }}
    >
      {children}
    </Text>
  );
}

/** One row of a group: lead, a body of title and subtitle, then trailing content. */
export function Row({
  lead,
  title,
  sub,
  trailing,
  onPress,
  last = false,
  accessibilityLabel,
  testID,
  role,
  checked,
}: {
  lead?: ReactNode;
  title: string;
  sub?: string;
  trailing?: ReactNode;
  onPress?: () => void;
  last?: boolean;
  accessibilityLabel?: string;
  testID?: string;
  role?: "button" | "checkbox";
  checked?: boolean;
}) {
  const { c } = useTheme();
  const { rtl } = useSession();
  const layout = {
    flexDirection: rtl ? "row-reverse" : "row",
    alignItems: "center",
    gap: 12,
    minHeight: 60,
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderBottomWidth: last ? 0 : 1,
    borderBottomColor: c.line,
  } as const;
  const inner = (
    <>
      {lead}
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text
          numberOfLines={1}
          style={{
            color: c.text,
            fontSize: 16,
            fontWeight: "600",
            textAlign: rtl ? "right" : "left",
          }}
        >
          {title}
        </Text>
        {sub ? (
          <Text
            numberOfLines={2}
            style={{
              color: c.muted,
              fontSize: 14,
              lineHeight: 21,
              textAlign: rtl ? "right" : "left",
            }}
          >
            {sub}
          </Text>
        ) : null}
      </View>
      {trailing}
    </>
  );
  // A row with nothing to press is a plain view: its trailing control (a switch) must not sit
  // inside a disabled button.
  if (!onPress)
    return (
      <View testID={testID} style={layout}>
        {inner}
      </View>
    );
  return (
    <Pressable
      accessibilityRole={role ?? "button"}
      accessibilityLabel={accessibilityLabel ?? title}
      accessibilityState={checked === undefined ? undefined : { checked }}
      testID={testID}
      onPress={onPress}
      style={({ pressed }) => ({ ...layout, backgroundColor: pressed ? c.hover : "transparent" })}
    >
      {inner}
    </Pressable>
  );
}

export function Btn({
  label,
  onPress,
  variant = "fill",
  disabled,
  full,
  icon,
}: {
  label: string;
  onPress: () => void;
  variant?: "primary" | "fill" | "outline" | "danger" | "ghost";
  disabled?: boolean;
  full?: boolean;
  icon?: IconName;
}) {
  const { c } = useTheme();
  const fg = variant === "primary" ? c["on-primary"] : variant === "danger" ? c.red : c.text;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: Boolean(disabled) }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => ({
        minHeight: 44,
        paddingHorizontal: 18,
        borderRadius: radius.pill,
        flexDirection: "row",
        gap: 8,
        alignItems: "center",
        justifyContent: "center",
        alignSelf: full ? "stretch" : "flex-start",
        flexGrow: full ? 1 : 0,
        backgroundColor:
          variant === "primary" ? c.primary : variant === "fill" ? c.fill : "transparent",
        borderWidth: variant === "outline" || variant === "danger" ? 1 : 0,
        borderColor: variant === "danger" ? c.red : c["line-strong"],
        opacity: disabled ? 0.45 : pressed ? 0.8 : 1,
      })}
    >
      {icon ? <Icon name={icon} size={18} color={fg} /> : null}
      <Text
        style={{
          color: fg,
          fontSize: 14,
          fontWeight: "600",
          textDecorationLine: variant === "ghost" ? "underline" : "none",
        }}
      >
        {label}
      </Text>
    </Pressable>
  );
}

export function Empty({ icon = "folder", children }: { icon?: IconName; children: ReactNode }) {
  const { c } = useTheme();
  return (
    <View style={{ alignItems: "center", paddingVertical: 56, paddingHorizontal: 16, gap: 12 }}>
      <Icon name={icon} size={32} color={c.muted} />
      <Text style={{ color: c.muted, fontSize: 16, textAlign: "center", lineHeight: 24 }}>
        {children}
      </Text>
    </View>
  );
}

export function Switch({
  value,
  onChange,
  label,
  disabled,
}: {
  value: boolean;
  onChange: (value: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  const { c } = useTheme();
  return (
    <Pressable
      role="switch"
      accessibilityRole="switch"
      accessibilityLabel={label}
      accessibilityState={{ checked: value, disabled: Boolean(disabled) }}
      aria-checked={value}
      disabled={disabled}
      onPress={() => onChange(!value)}
      style={{
        width: 46,
        height: 28,
        borderRadius: 14,
        padding: 3,
        backgroundColor: value ? c.accent : c["fill-2"],
        opacity: disabled ? 0.5 : 1,
        alignItems: value ? "flex-end" : "flex-start",
      }}
    >
      <View
        style={{
          width: 22,
          height: 22,
          borderRadius: 11,
          backgroundColor: value ? c["on-accent"] : c.text,
        }}
      />
    </Pressable>
  );
}

/** The skeleton shimmer: a pulsing block (a moving layer in the reference). */
export function Sk({
  width,
  height = 14,
  round = 8,
  style,
}: {
  width: number | `${number}%`;
  height?: number;
  round?: number;
  style?: ViewStyle;
}) {
  const { c } = useTheme();
  const pulse = useRef(new Animated.Value(0.45)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 700, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0.45, duration: 700, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [pulse]);
  return (
    <Animated.View
      style={[
        { width, height, borderRadius: round, backgroundColor: c.fill, opacity: pulse },
        style,
      ]}
    />
  );
}

export function SkRows({ count = 6, size = 50 }: { count?: number; size?: number }) {
  const { rtl, t } = useSession();
  return (
    <View
      role="status"
      aria-busy
      accessibilityLabel={t("sh_loading")}
      style={{ paddingVertical: 8 }}
    >
      {Array.from({ length: count }, (_, index) => (
        <View
          // biome-ignore lint/suspicious/noArrayIndexKey: a static placeholder list
          key={index}
          style={{
            flexDirection: rtl ? "row-reverse" : "row",
            alignItems: "center",
            gap: 12,
            paddingHorizontal: 16,
            paddingVertical: 9,
          }}
        >
          <Sk width={size} height={size} round={size / 2} />
          <View style={{ flex: 1, gap: 8 }}>
            <Sk width={`${46 + ((index * 13) % 30)}%`} />
            <Sk width={`${60 + ((index * 7) % 30)}%`} height={12} />
          </View>
        </View>
      ))}
    </View>
  );
}
