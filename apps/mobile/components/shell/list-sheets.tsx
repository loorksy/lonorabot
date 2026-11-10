// Custom lists (WhatsApp «القوائم»): «قائمة جديدة» is a full-height sheet in two pages, the name
// (😊 opens the emoji panel) then the agents and groups; a list chip's menu edits or deletes it
// (with undo); the selection adds chats to a list. Lists live on the server.
import type { ChatList } from "@lonora/contracts";
import { type ChatRow, foldSearch, listMemberRows, rowKey } from "@lonora/core";
import { type ReactNode, useMemo, useRef, useState } from "react";
import { Keyboard, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { ApiError } from "../../lib/api";
import { chatsWord, fill } from "../../lib/i18n";
import { listsApi } from "../../lib/lists-api";
import { useLists } from "../../lib/lists-state";
import { useSession } from "../../lib/session";
import { useShellData } from "../../lib/shell-data";
import { useTheme } from "../../lib/theme";
import { EmojiPanel } from "./emoji-panel";
import { Icon } from "./icon";
import { Btn, GroupBox, Row, RowAvatar, useAgentRole } from "./kit";
import { useSheets } from "./sheets";
import { useToast } from "./toast";

type Draft = { id?: string; name: string; keys: Set<string>; fromSelection: boolean };

function NameStep({
  draft,
  onNext,
  onLimit,
}: {
  draft: Draft;
  onNext: () => void;
  onLimit: () => void;
}) {
  const { c } = useTheme();
  const { t, rtl } = useSession();
  const [name, setName] = useState(draft.name);
  const [emoji, setEmoji] = useState(false);
  const update = (value: string) => {
    draft.name = value;
    setName(value);
  };
  const append = (value: string) => {
    const next = `${name}${value}`;
    if ([...next].length > 30) return onLimit();
    update(next);
  };
  return (
    <View style={{ flex: 1, justifyContent: "space-between" }}>
      <View style={{ gap: 8 }}>
        <Text style={{ color: c.muted, fontSize: 14, textAlign: rtl ? "right" : "left" }}>
          {t("sh_listName")}
        </Text>
        <View style={{ flexDirection: rtl ? "row-reverse" : "row", alignItems: "center", gap: 8 }}>
          <TextInput
            accessibilityLabel={t("sh_listName")}
            placeholder={t("sh_listNamePlaceholder")}
            placeholderTextColor={c.muted}
            maxLength={30}
            autoFocus
            value={name}
            onChangeText={update}
            onFocus={() => setEmoji(false)}
            returnKeyType="next"
            onSubmitEditing={() => name.trim() && onNext()}
            style={{
              flex: 1,
              minHeight: 48,
              borderRadius: 12,
              backgroundColor: c.fill,
              color: c.text,
              paddingHorizontal: 14,
              fontSize: 16,
              textAlign: rtl ? "right" : "left",
              writingDirection: rtl ? "rtl" : "ltr",
            }}
          />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={emoji ? t("sh_keyboard") : t("sh_addEmoji")}
            accessibilityState={{ expanded: emoji }}
            onPress={() => {
              if (!emoji) Keyboard.dismiss();
              setEmoji(!emoji);
            }}
            style={{
              width: 44,
              height: 44,
              borderRadius: 22,
              alignItems: "center",
              justifyContent: "center",
              backgroundColor: c.fill,
            }}
          >
            <Icon name={emoji ? "keyboard" : "smile"} size={22} color={c.text} />
          </Pressable>
        </View>
        <Text
          style={{
            color: c.muted,
            fontSize: 12,
            lineHeight: 22,
            textAlign: rtl ? "right" : "left",
          }}
        >
          {t("sh_listHint")}
        </Text>
      </View>
      <View style={{ paddingVertical: 12 }}>
        <Btn
          full
          variant="primary"
          disabled={!name.trim()}
          label={draft.id ? t("sh_nextChats") : t("sh_addAgentsOrGroups")}
          onPress={() => {
            setEmoji(false);
            onNext();
          }}
        />
      </View>
      {emoji ? (
        <EmojiPanel onPick={append} onDelete={() => update([...name].slice(0, -1).join(""))} />
      ) : null}
    </View>
  );
}

function PickStep({ draft, onSave }: { draft: Draft; onSave: () => Promise<void> }) {
  const { c } = useTheme();
  const { t, rtl } = useSession();
  const data = useShellData();
  const lists = useLists();
  const role = useAgentRole();
  const [keys, setKeys] = useState(() => new Set(draft.keys));
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const choices = useMemo(
    () =>
      [
        ...data.agents.map((agent) => rowKey("agent", agent.id)),
        ...data.groups.map((group) => rowKey("group", group.id)),
      ]
        .map((key) => lists.rows.find((row) => row.key === key))
        .filter((row): row is ChatRow => Boolean(row)),
    [data.agents, data.groups, lists.rows],
  );
  const sub = (row: ChatRow) =>
    (row.agent ? role(row.agent) : row.subtitle) || (row.kind === "group" ? t("sh_group") : "");
  const q = foldSearch(query);
  const shown = choices.filter((row) => !q || foldSearch(`${row.name} ${sub(row)}`).includes(q));
  const count = keys.size;
  return (
    <View style={{ flex: 1 }}>
      <View
        style={{
          height: 40,
          borderRadius: 20,
          backgroundColor: c.fill,
          justifyContent: "center",
          marginBottom: 8,
        }}
      >
        <TextInput
          accessibilityLabel={t("sh_searchAgentsGroups")}
          placeholder={t("sh_search")}
          placeholderTextColor={c.muted}
          value={query}
          onChangeText={setQuery}
          style={{
            color: c.text,
            paddingHorizontal: 16,
            fontSize: 14,
            textAlign: rtl ? "right" : "left",
          }}
        />
      </View>
      <ScrollView
        style={{ flex: 1 }}
        keyboardShouldPersistTaps="handled"
        accessibilityLabel={t("sh_agentsAndGroups")}
      >
        <GroupBox>
          {shown.map((row, index) => (
            <Row
              key={row.key}
              role="checkbox"
              checked={keys.has(row.key)}
              last={index === shown.length - 1}
              lead={<RowAvatar row={row} agents={data.agents} size={44} />}
              title={row.name}
              sub={sub(row)}
              trailing={
                <View
                  style={{
                    width: 24,
                    height: 24,
                    borderRadius: 12,
                    borderWidth: 1.5,
                    borderColor: keys.has(row.key) ? c.accent : c["line-strong"],
                    backgroundColor: keys.has(row.key) ? c.accent : "transparent",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  {keys.has(row.key) ? (
                    <Icon name="check" size={14} color={c["on-accent"]} />
                  ) : null}
                </View>
              }
              onPress={() => {
                const next = new Set(keys);
                if (next.has(row.key)) next.delete(row.key);
                else next.add(row.key);
                draft.keys = next;
                setKeys(next);
              }}
            />
          ))}
          {!shown.length ? (
            <Text style={{ color: c.muted, padding: 20, textAlign: "center" }}>
              {t("sh_noResults")}
            </Text>
          ) : null}
        </GroupBox>
      </ScrollView>
      <View style={{ paddingVertical: 12 }}>
        <Btn
          full
          variant="primary"
          disabled={busy}
          label={
            draft.id
              ? count
                ? fill(t("sh_saveListN"), { count })
                : t("sh_saveList")
              : count
                ? fill(t("sh_createListN"), { count })
                : t("sh_createList")
          }
          onPress={async () => {
            setBusy(true);
            try {
              await onSave();
            } finally {
              setBusy(false);
            }
          }}
        />
      </View>
    </View>
  );
}

const listSize = (locale: "ar" | "en", count: number, empty: string) =>
  count ? chatsWord(locale, count) : empty;

export function useListSheets() {
  const sheets = useSheets();
  const data = useShellData();
  const lists = useLists();
  const toast = useToast();
  const { t, locale } = useSession();
  const { c } = useTheme();
  const { setChatLists, chatLists } = data;
  const rowsRef = useRef(lists.rows);
  rowsRef.current = lists.rows;

  async function save(draft: Draft) {
    const name = draft.name.trim().slice(0, 30);
    if (!name) return;
    const taken = () => toast(fill(t("sh_listTaken"), { name }), { type: "warn" });
    if (chatLists.some((list) => list.id !== draft.id && list.name === name)) return taken();
    try {
      const picked = rowsRef.current.filter((row) => draft.keys.has(row.key));
      const threadIds = await lists.threadsOf(picked);
      let list: ChatList;
      if (draft.id) {
        const before = chatLists.find((row) => row.id === draft.id);
        if (before && before.name !== name) await listsApi.renameList(draft.id, name);
        list = await listsApi.members(draft.id, threadIds);
      } else {
        const created = await listsApi.createList(name);
        list = await listsApi.members(created.id, threadIds);
      }
      setChatLists((rows) =>
        rows.some((row) => row.id === list.id)
          ? rows.map((row) => (row.id === list.id ? list : row))
          : [...rows, list],
      );
      if (picked.some((row) => !row.threadId)) void data.refresh();
      lists.setFilter(`list:${list.id}`);
      sheets.close();
      if (draft.fromSelection) lists.end();
      toast(fill(draft.id ? t("sh_listSaved") : t("sh_listCreated"), { name }), {
        type: "success",
      });
    } catch (error) {
      if (error instanceof ApiError && error.code === "chat_list_name_taken") taken();
      else lists.failed(error);
    }
  }

  function pickPage(draft: Draft) {
    sheets.open({
      id: "list",
      title: fill(t("sh_addTo"), draft.name.trim()),
      bar: true,
      full: true,
      fixed: true,
      back: () => namePage(draft),
      body: <PickStep draft={draft} onSave={() => save(draft)} />,
    });
  }
  function namePage(draft: Draft) {
    sheets.open({
      id: "list",
      title: draft.id ? t("sh_editList") : t("sh_newList"),
      bar: true,
      full: true,
      fixed: true,
      body: (
        <NameStep
          draft={draft}
          onNext={() => pickPage(draft)}
          onLimit={() => toast(t("sh_nameMax"), { type: "warn" })}
        />
      ),
    });
  }
  const newList = (rows: readonly ChatRow[] = [], fromSelection = false) =>
    namePage({ name: "", keys: new Set(rows.map((row) => row.key)), fromSelection });
  const editList = (list: ChatList, step: "name" | "pick" = "name") => {
    const draft: Draft = {
      id: list.id,
      name: list.name,
      keys: new Set(listMemberRows(rowsRef.current, list).map((row) => row.key)),
      fromSelection: false,
    };
    if (step === "pick") pickPage(draft);
    else namePage(draft);
  };

  async function removeList(list: ChatList) {
    const index = chatLists.findIndex((row) => row.id === list.id);
    const wasActive = lists.filter === `list:${list.id}`;
    try {
      await listsApi.deleteList(list.id);
    } catch (error) {
      lists.failed(error);
      return;
    }
    setChatLists((rows) => rows.filter((row) => row.id !== list.id));
    if (wasActive) lists.setFilter("all");
    toast(fill(t("sh_listDeleted"), list.name), {
      action: {
        label: t("sh_undo"),
        run: async () => {
          try {
            const created = await listsApi.createList(list.name);
            await listsApi.members(created.id, list.thread_ids);
            const restored = await listsApi.moveList(created.id, Math.max(0, index));
            setChatLists((rows) => {
              const next = rows.filter((row) => row.id !== restored.id);
              next.splice(Math.max(0, index), 0, restored);
              return next;
            });
            if (wasActive) lists.setFilter(`list:${restored.id}`);
          } catch (error) {
            lists.failed(error);
          }
        },
      },
    });
  }

  const listMenu = (list: ChatList) => {
    const size = listSize(
      locale,
      listMemberRows(rowsRef.current, list).length,
      t("sh_listUnitEmpty"),
    );
    sheets.open({
      id: "list-menu",
      title: `${list.name} · ${size}`,
      body: (
        <GroupBox>
          <Row
            lead={<Icon name="edit" size={22} color={c.text} />}
            title={t("sh_editList")}
            onPress={() => editList(list)}
          />
          <Row
            lead={<Icon name="users" size={22} color={c.text} />}
            title={t("sh_theChats")}
            onPress={() => editList(list, "pick")}
          />
          <Row
            last
            lead={<Icon name="trash" size={22} color={c.red} />}
            title={t("sh_deleteList")}
            onPress={() => {
              sheets.close();
              void removeList(list);
            }}
          />
        </GroupBox>
      ),
    });
  };

  const addToList = (rows: readonly ChatRow[]) => {
    const add = async (list: ChatList) => {
      try {
        const ids = await lists.threadsOf(rows);
        const added = ids.filter((id) => !list.thread_ids.includes(id));
        const saved = await listsApi.members(list.id, [...list.thread_ids, ...added]);
        setChatLists((all) => all.map((row) => (row.id === saved.id ? saved : row)));
        if (rows.some((row) => !row.threadId)) void data.refresh();
        sheets.close();
        lists.end();
        toast(
          added.length
            ? fill(t("sh_addedToList"), chatsWord(locale, added.length), list.name)
            : fill(t("sh_allInList"), list.name),
          { type: "success" },
        );
      } catch (error) {
        lists.failed(error);
      }
    };
    const body: ReactNode = (
      <GroupBox>
        {chatLists.map((list) => (
          <Row
            key={list.id}
            lead={<Icon name="layers" size={22} color={c.muted} />}
            title={list.name}
            sub={listSize(
              locale,
              listMemberRows(rowsRef.current, list).length,
              t("sh_listUnitEmpty"),
            )}
            onPress={() => void add(list)}
          />
        ))}
        <Row
          last
          lead={<Icon name="plus" size={22} color={c.muted} />}
          title={t("sh_newList")}
          sub={fill(t("sh_willBeAdded"), chatsWord(locale, rows.length))}
          onPress={() => newList(rows, true)}
        />
      </GroupBox>
    );
    sheets.open({ id: "list", title: t("sh_addToList"), bar: true, body });
  };

  return { newList, editList, listMenu, addToList };
}
