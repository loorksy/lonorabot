// المحادثات: the chats header (title, search pill, «+»), the filters that rest hidden above the first
// row, every agent and group as a row, and the unified search over it all.
import type { SearchTab } from "@lonora/core";
import { filterRows } from "@lonora/core";
import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useMemo, useState } from "react";
import { BackHandler, View } from "react-native";
import { ChatList } from "../../components/shell/chat-list";
import { ChatsHeader, TopBar } from "../../components/shell/chrome";
import { useNewChatSheet } from "../../components/shell/new-chat-sheet";
import { SelBar } from "../../components/shell/selection";
import { UnifiedSearch } from "../../components/shell/unified-search";
import { useLists } from "../../lib/lists-state";
import { useShellData } from "../../lib/shell-data";
import { useTheme } from "../../lib/theme";

export default function Chats() {
  const { c } = useTheme();
  const router = useRouter();
  const data = useShellData();
  const lists = useLists();
  const newChat = useNewChatSheet();
  const [search, setSearch] = useState({ expanded: false, query: "", tab: "all" as SearchTab });
  const clearSearch = useCallback(() => setSearch({ expanded: false, query: "", tab: "all" }), []);
  useFocusEffect(
    useCallback(() => {
      if (!search.expanded) return;
      const sub = BackHandler.addEventListener("hardwareBackPress", () => {
        clearSearch();
        return true;
      });
      return () => sub.remove();
    }, [search.expanded, clearSearch]),
  );
  const visibleKeys = useMemo(
    () => filterRows(lists.rows, lists.filter, data.chatLists).map((row) => row.key),
    [lists.rows, lists.filter, data.chatLists],
  );
  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <TopBar solid={Boolean(lists.selected)}>
        {lists.selected ? (
          <SelBar visibleKeys={visibleKeys} />
        ) : (
          <ChatsHeader
            expanded={search.expanded}
            query={search.query}
            onQuery={(query) => setSearch((current) => ({ ...current, expanded: true, query }))}
            onExpand={() => setSearch((current) => ({ ...current, expanded: true }))}
            onClear={clearSearch}
            onNewChat={newChat}
          />
        )}
      </TopBar>
      {search.expanded && !lists.selected ? (
        <UnifiedSearch
          query={search.query}
          tab={search.tab}
          onTab={(tab) => setSearch((current) => ({ ...current, tab }))}
        />
      ) : (
        <ChatList onArchived={() => router.push("/archived")} />
      )}
    </View>
  );
}
