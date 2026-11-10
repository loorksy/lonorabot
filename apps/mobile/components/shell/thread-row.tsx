// One conversation row of the reference's list: avatar, name, time, preview with the owner's
// ticks (Q2: one grey tick = accepted by the server; two accent ticks = the agent's run started on
// it), muted and pinned marks, the paused badge, and the count or the 12px dot.
import type { Agent, InboxMessageKind } from "@lonora/contracts";
import { type ChatRow, isMuted, isPinned, rowCount, rowIsUnread, rowMarkedOnly } from "@lonora/core";
import { memo } from "react";
import { Pressable, Text, View } from "react-native";
import { fill } from "../../lib/i18n";
import type { OutgoingIntent } from "../../lib/outgoing-messages";
import { useSession } from "../../lib/session";
import { radius, useTheme } from "../../lib/theme";
import { Icon, type IconName } from "./icon";
import { RowAvatar, useAgentRole } from "./kit";

/** HH:mm with Latin digits, as the reference's fmtTime. */
export const clockTime = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });

const kindIcon: Partial<Record<InboxMessageKind, IconName>> = { voice: "mic", file: "file", image: "image", card: "shield" };

function Preview({ row, agents, outgoing, color }: { row: ChatRow; agents: readonly Agent[]; outgoing?: OutgoingIntent; color: string }) {
  const { c } = useTheme();
  const { t, rtl } = useSession();
  const role = useAgentRole();
  const style = { color, fontSize: 14, flexShrink: 1, textAlign: (rtl ? "right" : "left") as "right" | "left" };
  if (outgoing) {
    const failed = outgoing.message.delivery === "failed";
    return (
      <>
        <View accessibilityLabel={failed ? t("sh_notSent") : t("sh_waitingNetwork")} accessibilityRole="image">
          <Icon name={failed ? "alert" : "clock"} size={16} color={failed ? c.red : c.muted} />
        </View>
        <Text numberOfLines={1} style={style}>
          {fill(t("sh_youPrefix"), outgoing.message.content)}
        </Text>
      </>
    );
  }
  const last = row.entry?.last_message;
  if (!last) {
    const subtitle = row.agent ? role(row.agent) : row.subtitle;
    return (
      <Text numberOfLines={1} style={style}>
        {subtitle || t("sh_startChat")}
      </Text>
    );
  }
  const mine = last.role === "user";
  const speaker = !mine && row.kind === "group" && last.agent_id ? agents.find((agent) => agent.id === last.agent_id)?.name : undefined;
  const text = last.preview || last.content;
  const icon = kindIcon[last.kind];
  return (
    <>
      {mine ? (
        last.consumed ? (
          <Icon name="checks" size={16} color={c["accent-ink"]} />
        ) : (
          <Icon name="check" size={16} color={c.muted} />
        )
      ) : null}
      {icon ? <Icon name={icon} size={16} color={color} /> : null}
      <Text numberOfLines={1} style={style}>
        {mine ? fill(t("sh_youPrefix"), text) : speaker ? `${speaker}: ${text}` : text}
      </Text>
    </>
  );
}

export const ThreadRow = memo(function ThreadRow({
  row,
  agents,
  selecting,
  picked,
  working,
  outgoing,
  onOpen,
  onSelect,
}: {
  row: ChatRow;
  agents: readonly Agent[];
  selecting: boolean;
  picked: boolean;
  working: boolean;
  outgoing?: OutgoingIntent;
  onOpen: (row: ChatRow) => void;
  /** A long press starts the selection; while selecting a press toggles. */
  onSelect: (row: ChatRow) => void;
}) {
  const { c } = useTheme();
  const { t, rtl } = useSession();
  const unread = rowIsUnread(row);
  const muted = isMuted(row);
  const count = rowCount(row);
  const at = outgoing?.message.created_at ?? row.entry?.last_message?.created_at;
  const dir = rtl ? "row-reverse" : "row";
  const align = rtl ? "right" : "left";
  const countBg = muted ? c.faint : c.accent;
  const countFg = muted ? c.bg : c["on-accent"];
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={row.name}
      accessibilityState={{ selected: selecting ? picked : undefined }}
      testID={`thread-row-${row.key}`}
      {...({ dataSet: { key: row.key, inboxAgentId: row.kind === "agent" ? row.id : undefined, inboxGroupId: row.kind === "group" ? row.id : undefined } } as object)}
      delayLongPress={430}
      onPress={() => (selecting ? onSelect(row) : onOpen(row))}
      onLongPress={() => !selecting && onSelect(row)}
      style={({ pressed }) => ({
        flexDirection: dir,
        alignItems: "center",
        gap: 12,
        minHeight: 72,
        paddingVertical: 8,
        paddingHorizontal: 16,
        backgroundColor: picked ? `${c.accent}21` : pressed ? c.hover : "transparent",
      })}
    >
      <View>
        <View style={{ transform: [{ scale: picked ? 0.92 : 1 }] }}>
          <RowAvatar row={row} agents={agents} working={working} />
        </View>
        {picked ? (
          <View
            style={{
              position: "absolute",
              bottom: -2,
              [rtl ? "left" : "right"]: -3,
              width: 22,
              height: 22,
              borderRadius: 11,
              backgroundColor: c.accent,
              borderWidth: 2.5,
              borderColor: c.bg,
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Icon name="check" size={14} color={c["on-accent"]} />
          </View>
        ) : null}
      </View>
      <View style={{ flex: 1, minWidth: 0, gap: 2 }}>
        <View style={{ flexDirection: dir, alignItems: "center", gap: 8 }}>
          <Text numberOfLines={1} style={{ flex: 1, color: c.text, fontSize: 16, fontWeight: unread ? "700" : "600", textAlign: align }}>
            {row.name}
          </Text>
          {at ? (
            <Text style={{ color: unread && !muted ? c["accent-ink"] : c.muted, fontSize: 12, fontWeight: unread && !muted ? "600" : "400" }}>{clockTime(at)}</Text>
          ) : null}
        </View>
        <View style={{ flexDirection: dir, alignItems: "center", gap: 8 }}>
          <View style={{ flex: 1, minWidth: 0, flexDirection: dir, alignItems: "center", gap: 4 }}>
            <Preview row={row} agents={agents} outgoing={outgoing} color={unread ? c.text : c.muted} />
          </View>
          {row.paused ? (
            <View style={{ paddingHorizontal: 8, paddingVertical: 1, borderRadius: radius.pill, backgroundColor: c.fill }}>
              <Text style={{ color: c.muted, fontSize: 12 }}>{t("sh_paused")}</Text>
            </View>
          ) : null}
          {muted ? (
            <View accessibilityLabel={t("sh_muted")} accessibilityRole="image">
              <Icon name="bellOff" size={16} color={c.faint} />
            </View>
          ) : null}
          {isPinned(row) ? (
            <View accessibilityLabel={t("sh_pinned")} accessibilityRole="image">
              <Icon name="pin" size={16} color={c.faint} />
            </View>
          ) : null}
          {count > 0 ? (
            <View accessibilityLabel={fill(t("sh_unreadN"), { count })} style={{ minWidth: 22, height: 22, paddingHorizontal: 7, borderRadius: radius.pill, backgroundColor: countBg, alignItems: "center", justifyContent: "center" }}>
              <Text style={{ color: countFg, fontSize: 12, fontWeight: "700" }}>{count}</Text>
            </View>
          ) : rowMarkedOnly(row) ? (
            <View accessibilityRole="image" accessibilityLabel={t("sh_unreadMarked")} style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: countBg }} />
          ) : null}
        </View>
      </View>
    </Pressable>
  );
});
