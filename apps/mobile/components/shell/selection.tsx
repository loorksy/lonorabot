// The selection's actions (reference selAction), each on the server and each ending the selection.
// «حذف» and «مسح الرسائل» hide the history for the owner (owner decisions Q1, Q44): an agent or a
// group is never deleted; the conversation stays in the list.
import {
  type ChatRow,
  groupDraftName,
  isArchived,
  isPinned,
  PIN_LIMIT,
  pinsAfter,
  selectionSummary,
} from "@lonora/core";
import { useRouter } from "expo-router";
import { Pressable, Text, View } from "react-native";
import { chatsWord, fill } from "../../lib/i18n";
import { useLists } from "../../lib/lists-state";
import { useSession } from "../../lib/session";
import { useShellData } from "../../lib/shell-data";
import { useTheme } from "../../lib/theme";
import { Icon, type IconName } from "./icon";
import { Btn, GroupBox, Row } from "./kit";
import { useListSheets } from "./list-sheets";
import { useSheets } from "./sheets";
import { useToast } from "./toast";

type Act =
  | "pin"
  | "mute"
  | "archive"
  | "delete"
  | "clear"
  | "read"
  | "fav"
  | "list"
  | "group"
  | "all";

export function useSelectionActions(visibleKeys: readonly string[]) {
  const lists = useLists();
  const data = useShellData();
  const toast = useToast();
  const sheets = useSheets();
  const router = useRouter();
  const listSheets = useListSheets();
  const { t, locale, rtl } = useSession();
  const { c } = useTheme();
  const picked = lists.picked;
  const n = picked.length;
  const run = async (work: () => Promise<void>, message?: string) => {
    try {
      await work();
      lists.end();
      if (message) toast(message);
    } catch (error) {
      lists.failed(error);
    }
  };
  const confirm = (act: "clear" | "delete", rows: ChatRow[]) => {
    const groups = rows.filter((row) => row.kind === "group").length;
    const agents = rows.length - groups;
    const word = chatsWord(locale, rows.length);
    const what = fill(
      act === "clear"
        ? t("sh_confClear")
        : !agents
          ? t(groups === 1 ? "sh_confGroup1" : "sh_confGroupN")
          : t(groups ? "sh_confMixed" : "sh_confAgents"),
      word,
    );
    const title = act === "clear" ? t("sh_clearMessagesQ") : t("sh_deleteChatsQ");
    sheets.open({
      id: "sel-confirm",
      title,
      body: (
        <View style={{ gap: 16 }}>
          <Text
            style={{
              color: c.text,
              fontSize: 16,
              lineHeight: 26,
              textAlign: rtl ? "right" : "left",
            }}
          >
            {what}
          </Text>
          <View style={{ flexDirection: rtl ? "row-reverse" : "row", gap: 10 }}>
            <Btn label={t("sh_cancel")} variant="outline" full onPress={() => sheets.close()} />
            <Btn
              label={act === "clear" ? t("sh_clear") : t("sh_delete")}
              variant="danger"
              full
              onPress={() => {
                sheets.close();
                void run(
                  async () => {
                    await lists.clear(rows);
                    // «حذف» also drops the marks, as the reference does; nothing else changes.
                    if (act === "delete")
                      await lists.prefs(
                        rows.filter((row) => row.entry),
                        { pinned: false, muted: false, archived: false, favourite: false },
                      );
                  },
                  act === "delete" ? fill(t("sh_chatsDeleted"), word) : t("sh_messagesCleared"),
                );
              }}
            />
          </View>
        </View>
      ),
    });
  };
  const act = (what: Act) => {
    if (!n) return;
    const summary = selectionSummary(picked, visibleKeys);
    switch (what) {
      case "all":
        lists.selectAll(visibleKeys);
        return;
      case "pin":
        if (summary.allPinned)
          return run(
            () => lists.prefs(picked, { pinned: false }),
            n > 1 ? t("sh_chatsUnpinned") : t("sh_chatUnpinned"),
          );
        if (pinsAfter(lists.rows, picked) > PIN_LIMIT) return toast(t("sh_pin3"));
        // New pins go on top in the order they were picked.
        return run(
          () => lists.prefs(picked.filter((row) => !isPinned(row)).reverse(), { pinned: true }),
          n > 1 ? t("sh_chatsPinned") : t("sh_chatPinned"),
        );
      case "mute":
        return run(
          () => lists.prefs(picked, { muted: !summary.allMuted }),
          summary.allMuted ? t("sh_notifRestored") : t("sh_notifMuted"),
        );
      case "archive": {
        if (picked.every(isArchived))
          return run(
            () => lists.prefs(picked, { archived: false }),
            n > 1 ? t("sh_chatsReturned") : t("sh_chatReturned"),
          );
        const rows = [...picked];
        return run(async () => {
          await lists.prefs(rows, { archived: true });
          toast(fill(t("sh_chatsArchived"), chatsWord(locale, rows.length)), {
            type: "success",
            action: {
              label: t("sh_undo"),
              run: () => void lists.prefs(rows, { archived: false }).catch(lists.failed),
            },
          });
        });
      }
      case "read":
        return run(() =>
          summary.anyUnread ? lists.read(picked) : lists.prefs(picked, { marked_unread: true }),
        );
      case "fav":
        return run(
          () => lists.prefs(picked, { favourite: !summary.allFavourite }),
          summary.allFavourite ? t("sh_removedFav") : t("sh_addedFav"),
        );
      case "list":
        if (data.chatLists.length) listSheets.addToList(picked);
        else listSheets.newList(picked, true);
        return;
      case "group": {
        const members = summary.agentRows;
        const name = groupDraftName(members.map((row) => row.name));
        lists.end();
        router.push({
          pathname: "/new-group",
          params: { members: members.map((row) => row.id).join(","), name },
        });
        return;
      }
      case "clear":
      case "delete":
        return confirm(what, [...picked]);
    }
  };
  return { act, picked, summary: selectionSummary(picked, visibleKeys) };
}

function Tool({ icon, label, onPress }: { icon: IconName; label: string; onPress: () => void }) {
  const { c } = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={({ pressed }) => ({
        width: 42,
        height: 42,
        borderRadius: 21,
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: pressed ? c.hover : "transparent",
      })}
    >
      <Icon name={icon} size={22} color={c.text} />
    </Pressable>
  );
}

/* The header while selecting: ✕ · count | pin · mute · archive · delete · ⋮ (a toolbar). */
export function SelBar({ visibleKeys }: { visibleKeys: readonly string[] }) {
  const { c } = useTheme();
  const { t, rtl } = useSession();
  const lists = useLists();
  const sheets = useSheets();
  const { act, picked, summary } = useSelectionActions(visibleKeys);
  const n = picked.length;
  const archived = n > 0 && picked.every(isArchived);
  const menu = () => {
    const run = (what: Act) => () => {
      sheets.close();
      act(what);
    };
    sheets.open({
      id: "sel-menu",
      title: t("sh_more"),
      body: (
        <GroupBox>
          {!summary.allVisiblePicked ? (
            <Row
              lead={<Icon name="checks" size={22} color={c.text} />}
              title={t("sh_selectAll")}
              onPress={run("all")}
            />
          ) : null}
          <Row
            lead={<Icon name={summary.anyUnread ? "checks" : "chat"} size={22} color={c.text} />}
            title={summary.anyUnread ? t("sh_markRead") : t("sh_markUnread")}
            onPress={run("read")}
          />
          <Row
            lead={<Icon name="heart" size={22} color={c.text} />}
            title={summary.allFavourite ? t("sh_removeFav") : t("sh_addFav")}
            onPress={run("fav")}
          />
          <Row
            lead={<Icon name="layers" size={22} color={c.text} />}
            title={t("sh_addToList")}
            onPress={run("list")}
          />
          {summary.agentRows.length >= 2 ? (
            <Row
              lead={<Icon name="users" size={22} color={c.text} />}
              title={t("sh_groupFromSelected")}
              onPress={run("group")}
            />
          ) : null}
          <Row
            last
            lead={<Icon name="trash" size={22} color={c.red} />}
            title={t("sh_clearMessages")}
            onPress={run("clear")}
          />
        </GroupBox>
      ),
    });
  };
  return (
    <View
      accessibilityRole="toolbar"
      accessibilityLabel={t("sh_selectedChats")}
      style={{
        height: 60,
        flexDirection: rtl ? "row-reverse" : "row",
        alignItems: "center",
        gap: 2,
        paddingHorizontal: 6,
      }}
    >
      <Tool icon="close" label={t("sh_cancelSelection")} onPress={lists.end} />
      <Text
        accessibilityLiveRegion="polite"
        accessibilityLabel={`${n} ${t("sh_selected")}`}
        style={{ minWidth: 30, paddingStart: 6, color: c.text, fontSize: 22, fontWeight: "700" }}
      >
        {n}
      </Text>
      <View style={{ flex: 1 }} />
      {!archived ? (
        <Tool
          icon={summary.allPinned ? "pinOff" : "pin"}
          label={summary.allPinned ? t("sh_unpin") : t("sh_pin")}
          onPress={() => act("pin")}
        />
      ) : null}
      <Tool
        icon={summary.allMuted ? "bell" : "bellOff"}
        label={summary.allMuted ? t("sh_unmute") : t("sh_muteNotifications")}
        onPress={() => act("mute")}
      />
      <Tool
        icon={archived ? "unarchive" : "archive"}
        label={archived ? t("sh_unarchive") : t("sh_archive")}
        onPress={() => act("archive")}
      />
      <Tool icon="trash" label={t("sh_delete")} onPress={() => act("delete")} />
      <Tool icon="more" label={t("sh_more")} onPress={menu} />
    </View>
  );
}
