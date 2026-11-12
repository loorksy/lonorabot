// The message menu, as on Web's conversation menu: a long press on a message opens the six quick
// reactions and the message's actions; a failed message offers «إعادة المحاولة» and «حذف»; the
// reactions under a bubble list who reacted, and the owner's own one is removed with a tap.
import { type Message, REACTION_EMOJIS, type ReactionEmoji } from "@lonora/contracts";
import { useCallback } from "react";
import { Pressable, Text, View } from "react-native";
import { fill } from "../lib/i18n";
import { canEditAndResend, canTurnIntoTask, ownerReaction } from "../lib/message-actions";
import { isOutgoingMessage } from "../lib/outgoing-messages";
import { useSession } from "../lib/session";
import { useTheme } from "../lib/theme";
import { Icon, type IconName } from "./shell/icon";
import { GroupBox, Row } from "./shell/kit";
import { useSheets } from "./shell/sheets";

export type MessageMenuActions = {
  onReply?: (message: Message) => void;
  onCopy: (message: Message) => void;
  onEdit: (message: Message) => void;
  onTask: (message: Message) => void;
  onReact: (message: Message, emoji: ReactionEmoji | null) => void;
  onRetry: (nonce: string) => void;
  onDrop: (nonce: string) => void;
  /** Who reacted: an agent's name for its id. */
  reactorName: (reactor: string) => string;
};

function ReactRow({ message, react }: { message: Message; react: (emoji: ReactionEmoji) => void }) {
  const { c } = useTheme();
  const { rtl, t } = useSession();
  const mine = ownerReaction(message.reactions);
  return (
    <View
      role="group"
      accessibilityLabel={t("quickReaction")}
      style={{
        flexDirection: rtl ? "row-reverse" : "row",
        justifyContent: "space-between",
        paddingHorizontal: 4,
      }}
    >
      {REACTION_EMOJIS.map((emoji) => (
        <Pressable
          key={emoji}
          accessibilityRole="button"
          accessibilityLabel={fill(t("reactWith"), emoji)}
          accessibilityState={{ selected: mine === emoji }}
          aria-pressed={mine === emoji}
          onPress={() => react(emoji)}
          style={({ pressed }) => ({
            width: 48,
            height: 48,
            borderRadius: 24,
            alignItems: "center",
            justifyContent: "center",
            backgroundColor: mine === emoji ? c.fill : pressed ? c.hover : "transparent",
          })}
        >
          <Text style={{ fontSize: 26 }}>{emoji}</Text>
        </Pressable>
      ))}
    </View>
  );
}

/** `actions` is read at the moment a menu opens or a row is tapped, so the caller may set its
 * handlers after its early returns. */
export function useMessageMenu(read: () => MessageMenuActions) {
  const sheets = useSheets();
  const { t } = useSession();
  const { c } = useTheme();
  const item = useCallback(
    (icon: IconName, title: string, run: () => void, last = false, danger = false) => (
      <Row
        key={title}
        lead={<Icon name={icon} size={22} color={danger ? c.red : c.text} />}
        title={title}
        last={last}
        onPress={() => {
          sheets.close();
          run();
        }}
      />
    ),
    [sheets, c],
  );
  const open = useCallback(
    (message: Message) => {
      if (isOutgoingMessage(message)) {
        if (message.delivery !== "failed") return;
        sheets.open({
          id: "message-menu",
          title: t("messageNotSent"),
          body: (
            <GroupBox>
              {item("refresh", t("retry"), () => read().onRetry(message.retry_nonce))}
              {item(
                "trash",
                t("deleteMessage"),
                () => read().onDrop(message.retry_nonce),
                true,
                true,
              )}
            </GroupBox>
          ),
        });
        return;
      }
      const rows = [
        read().onReply ? item("reply", t("reply"), () => read().onReply?.(message)) : null,
        message.content.trim() ? item("copy", t("copyText"), () => read().onCopy(message)) : null,
        canEditAndResend(message)
          ? item("edit", t("editAndResend"), () => read().onEdit(message))
          : null,
        canTurnIntoTask(message)
          ? item("task", t("turnIntoTask"), () => read().onTask(message))
          : null,
      ].filter(Boolean);
      sheets.open({
        id: "message-menu",
        title: t("messageOptions"),
        body: (
          <View style={{ gap: 14 }}>
            <ReactRow
              message={message}
              react={(emoji) => {
                sheets.close();
                read().onReact(message, ownerReaction(message.reactions) === emoji ? null : emoji);
              }}
            />
            {rows.length ? <GroupBox>{rows}</GroupBox> : null}
          </View>
        ),
      });
    },
    [read, item, sheets, t],
  );
  const reactions = useCallback(
    (message: Message) => {
      sheets.open({
        id: "message-reactions",
        title: t("reactionsTitle"),
        body: (
          <GroupBox>
            {(message.reactions ?? []).map((row, index, all) => {
              const owner = row.reactor === "owner";
              return (
                <Row
                  key={row.reactor}
                  lead={<Text style={{ fontSize: 24 }}>{row.emoji}</Text>}
                  title={owner ? t("reactionYou") : read().reactorName(row.reactor)}
                  sub={owner ? t("tapToRemove") : undefined}
                  last={index === all.length - 1}
                  onPress={
                    owner
                      ? () => {
                          sheets.close();
                          read().onReact(message, null);
                        }
                      : undefined
                  }
                />
              );
            })}
          </GroupBox>
        ),
      });
    },
    [read, sheets, t],
  );
  return { open, reactions };
}

/** The reactions under a bubble: one chip per emoji with its count; a tap lists who reacted. */
export function ReactionChips({ message, onPress }: { message: Message; onPress: () => void }) {
  const { c } = useTheme();
  const { rtl, t } = useSession();
  const rows = message.reactions ?? [];
  if (!rows.length) return null;
  const counts = new Map<string, number>();
  for (const row of rows) counts.set(row.emoji, (counts.get(row.emoji) ?? 0) + 1);
  const mine = ownerReaction(rows);
  return (
    <Pressable
      testID="message-reactions"
      accessibilityRole="button"
      accessibilityLabel={`${t("reactionsTitle")}: ${[...counts.keys()].join(" ")}`}
      onPress={onPress}
      style={{
        flexDirection: rtl ? "row-reverse" : "row",
        alignSelf: rtl ? "flex-end" : "flex-start",
        gap: 4,
        paddingHorizontal: 8,
        paddingVertical: 3,
        borderRadius: 14,
        borderWidth: 1,
        borderColor: mine ? c.accent : c.line,
        backgroundColor: c.raised,
      }}
    >
      {[...counts].map(([emoji, count]) => (
        <Text key={emoji} style={{ fontSize: 14, color: c.text }}>
          {emoji}
          {count > 1 ? ` ${count}` : ""}
        </Text>
      ))}
    </Pressable>
  );
}
