// The chats list: filters that rest hidden above the first row and appear when the list is pulled
// down, the «المؤرشفة» row, and every agent and group as one row. The archived page shares its rows.
import type { Thread } from "@lonora/contracts";
import {
  archivedRowSummary,
  archivedRows,
  BUILTIN_FILTERS,
  type ChatRow,
  filterRows,
  type ListFilter,
  listIdOf,
} from "@lonora/core";
import { useRouter } from "expo-router";
import {
  type ReactElement,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  FlatList,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  Pressable,
  RefreshControl,
  ScrollView,
  Text,
  View,
} from "react-native";
import { api } from "../../lib/api";
import { fill } from "../../lib/i18n";
import { listsApi } from "../../lib/lists-api";
import { useLists } from "../../lib/lists-state";
import { useSession } from "../../lib/session";
import { useShellData } from "../../lib/shell-data";
import { useTheme } from "../../lib/theme";
import { Icon } from "./icon";
import { Empty, GroupBox, Row, SkRows, Switch } from "./kit";
import { useListSheets } from "./list-sheets";
import { ThreadRow } from "./thread-row";
import { useToast } from "./toast";

const FILTER_H = 41;

/** Opens a row's conversation: an agent with none gets it now; a group opens its own screen. */
export function useOpenChat() {
  const router = useRouter();
  const { errorText } = useSession();
  const toast = useToast();
  return useCallback(
    async (row: ChatRow, extra: Record<string, string> = {}) => {
      try {
        if (row.kind === "group") {
          router.push({ pathname: "/group-thread", params: { groupId: row.id, ...extra } });
          return;
        }
        const threadId =
          row.threadId ??
          (await api.post<Thread>(`/agents/${encodeURIComponent(row.id)}/conversation`, {})).id;
        router.push({ pathname: "/thread", params: { id: threadId, ...extra } });
      } catch (reason) {
        toast(errorText(reason), { type: "error" });
      }
    },
    [router, errorText, toast],
  );
}

function Filters() {
  const { c } = useTheme();
  const { t, rtl } = useSession();
  const data = useShellData();
  const lists = useLists();
  const sheets = useListSheets();
  const names: Record<(typeof BUILTIN_FILTERS)[number], string> = {
    all: t("sh_fAll"),
    unread: t("sh_fUnread"),
    fav: t("sh_fFav"),
    agents: t("sh_fAgents"),
    groups: t("sh_fGroups"),
  };
  const chip = (key: string, label: string, filter: ListFilter, onLong?: () => void) => {
    const active = lists.filter === filter;
    return (
      <Pressable
        key={key}
        accessibilityRole="button"
        accessibilityState={{ selected: active }}
        aria-pressed={active}
        accessibilityLabel={label}
        onPress={() => lists.setFilter(filter)}
        onLongPress={onLong}
        delayLongPress={480}
        style={{ minHeight: 40, paddingHorizontal: 12, justifyContent: "center" }}
      >
        <Text
          style={{
            color: active ? c.text : c.muted,
            fontSize: 14,
            fontWeight: active ? "700" : "600",
          }}
        >
          {label}
        </Text>
        {active ? (
          <View
            style={{
              position: "absolute",
              left: 8,
              right: 8,
              bottom: -1,
              height: 2.5,
              borderTopLeftRadius: 2,
              borderTopRightRadius: 2,
              backgroundColor: c.accent,
            }}
          />
        ) : null}
      </Pressable>
    );
  };
  return (
    <View
      accessibilityRole="toolbar"
      accessibilityLabel={t("sh_filterChats")}
      style={{ height: FILTER_H, borderBottomWidth: 1, borderBottomColor: c.line }}
    >
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ flexDirection: rtl ? "row-reverse" : "row", paddingHorizontal: 4 }}
      >
        {BUILTIN_FILTERS.map((filter) => chip(filter, names[filter], filter))}
        {data.chatLists.map((list) =>
          chip(`list:${list.id}`, list.name, `list:${list.id}`, () => sheets.listMenu(list)),
        )}
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("sh_newList")}
          onPress={() => sheets.newList()}
          style={{ width: 40, minHeight: 40, alignItems: "center", justifyContent: "center" }}
        >
          <Icon name="plus" size={18} color={c.muted} />
        </Pressable>
      </ScrollView>
    </View>
  );
}

function ArchiveRow({ onOpen }: { onOpen: () => void }) {
  const { c } = useTheme();
  const { t, rtl } = useSession();
  const lists = useLists();
  const { count, unread } = archivedRowSummary(lists.rows);
  if (!count) return null;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={t("sh_archived")}
      testID="archive-row"
      onPress={onOpen}
      style={({ pressed }) => ({
        flexDirection: rtl ? "row-reverse" : "row",
        alignItems: "center",
        gap: 12,
        minHeight: 54,
        paddingHorizontal: 16,
        backgroundColor: pressed ? c.hover : "transparent",
      })}
    >
      <View style={{ width: 50, alignItems: "center" }}>
        <Icon name="archive" size={22} color={c.muted} />
      </View>
      <Text
        style={{
          flex: 1,
          color: c.text,
          fontSize: 16,
          fontWeight: "600",
          textAlign: rtl ? "right" : "left",
        }}
      >
        {t("sh_archived")}
      </Text>
      <Text
        style={{
          color: unread ? c["accent-ink"] : c.muted,
          fontSize: 12,
          fontWeight: "600",
          paddingHorizontal: 8,
        }}
      >
        {unread || count}
      </Text>
    </Pressable>
  );
}

/** Rows with their gestures; `header` and `footer` ride inside the scroller. */
function RowsList({
  rows,
  header,
  footer,
  empty,
  restHidden,
  scrollRef,
}: {
  rows: readonly ChatRow[];
  header?: ReactNode;
  footer?: ReactNode;
  empty: ReactNode;
  restHidden?: boolean;
  scrollRef?: React.RefObject<FlatList<ChatRow> | null>;
}) {
  const { c } = useTheme();
  const data = useShellData();
  const lists = useLists();
  const open = useOpenChat();
  const [refreshing, setRefreshing] = useState(false);
  const [viewport, setViewport] = useState(0);
  const onSelect = useCallback(
    (row: ChatRow) => {
      if (lists.selected) lists.toggle(row.key);
      else lists.start(row.key);
    },
    [lists],
  );
  const placed = useRef(false);
  const list = useRef<FlatList<ChatRow>>(null);
  const ref = scrollRef ?? list;
  // The filters rest hidden above the first row until the list is pulled down.
  useEffect(() => {
    if (!restHidden || placed.current || !viewport || !data.loaded) return;
    placed.current = true;
    ref.current?.scrollToOffset({ offset: FILTER_H, animated: false });
  }, [restHidden, viewport, data.loaded, ref]);
  const snap = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    if (!restHidden) return;
    const y = event.nativeEvent.contentOffset.y;
    if (y > 0 && y < FILTER_H)
      ref.current?.scrollToOffset({ offset: y > FILTER_H / 2 ? FILTER_H : 0, animated: true });
  };
  return (
    <FlatList
      ref={ref}
      data={rows as ChatRow[]}
      extraData={lists.selected}
      keyExtractor={(row) => row.key}
      onLayout={(event) => setViewport(event.nativeEvent.layout.height)}
      contentContainerStyle={{
        flexGrow: 1,
        paddingBottom: 120,
        minHeight: restHidden ? viewport + FILTER_H : undefined,
      }}
      onScrollEndDrag={snap}
      onMomentumScrollEnd={snap}
      keyboardShouldPersistTaps="handled"
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          tintColor={c.text}
          onRefresh={() => {
            setRefreshing(true);
            void data.refresh().finally(() => setRefreshing(false));
          }}
        />
      }
      ListHeaderComponent={header as ReactElement | undefined}
      ListFooterComponent={footer as ReactElement | undefined}
      ListEmptyComponent={empty as ReactElement}
      renderItem={({ item }) => (
        <ThreadRow
          row={item}
          agents={data.agents}
          selecting={lists.selected !== null}
          picked={lists.selected?.has(item.key) ?? false}
          working={item.kind === "agent" && data.busyIds.has(item.id)}
          outgoing={item.threadId ? lists.outgoing.get(item.threadId) : undefined}
          onOpen={open}
          onSelect={onSelect}
        />
      )}
    />
  );
}

export function ChatList({
  onArchived,
  scrollRef,
}: {
  onArchived: () => void;
  scrollRef?: React.RefObject<FlatList<ChatRow> | null>;
}) {
  const { c } = useTheme();
  const { t, rtl } = useSession();
  const data = useShellData();
  const lists = useLists();
  const sheets = useListSheets();
  const visible = useMemo(
    () => filterRows(lists.rows, lists.filter, data.chatLists),
    [lists.rows, lists.filter, data.chatLists],
  );
  const listId = listIdOf(lists.filter);
  const activeList = listId ? data.chatLists.find((list) => list.id === listId) : undefined;
  const loading = !data.loaded;
  const empty = loading ? (
    <SkRows count={7} />
  ) : data.error && !data.inbox.length ? (
    <View
      accessibilityRole="alert"
      style={{ padding: 20, gap: 10, alignItems: rtl ? "flex-end" : "flex-start" }}
    >
      <Text style={{ color: c.muted, fontSize: 14 }}>{data.error}</Text>
    </View>
  ) : activeList ? (
    <View style={{ alignItems: "center", paddingVertical: 48, gap: 12 }}>
      <Icon name="layers" size={32} color={c.muted} />
      <Text style={{ color: c.muted, fontSize: 16 }}>
        {fill(t("sh_noChatsInList"), activeList.name)}
      </Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={t("sh_addChats")}
        onPress={() => sheets.editList(activeList, "pick")}
        style={{
          flexDirection: "row",
          gap: 6,
          alignItems: "center",
          minHeight: 36,
          paddingHorizontal: 14,
          borderRadius: 999,
          borderWidth: 1,
          borderColor: c["line-strong"],
        }}
      >
        <Icon name="plus" size={16} color={c.text} />
        <Text style={{ color: c.text, fontSize: 14, fontWeight: "600" }}>{t("sh_addChats")}</Text>
      </Pressable>
    </View>
  ) : (
    <Empty>
      {lists.filter === "unread"
        ? t("sh_noUnread")
        : lists.filter === "fav"
          ? t("sh_noFav")
          : t("sh_noChats")}
    </Empty>
  );
  return (
    <View
      testID="conversation-inbox"
      accessibilityLabel={t("sh_conversations")}
      style={{ flex: 1 }}
    >
      <RowsList
        rows={visible}
        scrollRef={scrollRef}
        restHidden={lists.filter === "all"}
        header={
          <>
            <Filters />
            {data.error && data.inbox.length ? (
              <Text
                accessibilityRole="alert"
                style={{
                  color: c.red,
                  fontSize: 12,
                  padding: 12,
                  textAlign: rtl ? "right" : "left",
                }}
              >
                {data.error}
              </Text>
            ) : null}
            {lists.filter === "all" ? <ArchiveRow onOpen={onArchived} /> : null}
          </>
        }
        empty={empty}
      />
    </View>
  );
}

/* «المؤرشفة»: the archived rows (selection offers إلغاء الأرشفة), the note and the setting. */
export function ArchivedContent() {
  const { c } = useTheme();
  const { t, rtl } = useSession();
  const data = useShellData();
  const lists = useLists();
  const toast = useToast();
  const rows = useMemo(() => archivedRows(lists.rows), [lists.rows]);
  const keep = data.threadSettings?.keep_archived ?? true;
  const settings = (
    <GroupBox style={{ marginHorizontal: 16 }}>
      <Row
        last
        lead={<Icon name="archive" size={22} color={c.muted} />}
        title={t("sh_keepArchived")}
        sub={keep ? t("sh_keepArchivedOn") : t("sh_keepArchivedOff")}
        trailing={
          <Switch
            label={t("sh_keepArchived")}
            value={keep}
            disabled={!data.threadSettings}
            onChange={async (next) => {
              try {
                const saved = await listsApi.settings({ keep_archived: next });
                data.setThreadSettings(saved);
                toast(saved.keep_archived ? t("sh_staysArchived") : t("sh_returnsOnMessage"));
              } catch (error) {
                lists.failed(error);
              }
            }}
          />
        }
      />
    </GroupBox>
  );
  if (!data.loaded) return <SkRows count={5} />;
  return (
    <RowsList
      rows={rows}
      empty={<Empty icon="archive">{t("sh_noArchived")}</Empty>}
      footer={
        <View>
          {rows.length ? (
            <View style={{ flexDirection: rtl ? "row-reverse" : "row", gap: 8, margin: 18 }}>
              <Icon name="info" size={18} color={c.faint} />
              <Text
                style={{ flex: 1, color: c.faint, fontSize: 14, textAlign: rtl ? "right" : "left" }}
              >
                {t("sh_archivedNote")}
              </Text>
            </View>
          ) : null}
          {settings}
        </View>
      }
    />
  );
}
