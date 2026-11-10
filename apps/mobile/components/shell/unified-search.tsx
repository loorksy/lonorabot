// UnifiedSearch: one engine (GET /api/search, owner-wide, never an agent's) behind the chats
// header's field. An empty query browses what is recent; categories are tabs with counts; الكل shows
// a few of each, a tab pages by 32. Only the latest query lands. Paging and mapping live in core.
import type { SearchResponse, SearchResult } from "@lonora/contracts";
import {
  type ChatRow,
  firstSearchPage,
  highlightRange,
  moreSearchItems,
  rowKey,
  SEARCH_TABS,
  type SearchFetch,
  type SearchSection,
  type SearchTab,
  searchPath,
} from "@lonora/core";
import { useRouter } from "expo-router";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { request, SessionRequestCancelled } from "../../lib/api";
import { fill } from "../../lib/i18n";
import { useLists } from "../../lib/lists-state";
import { useSession } from "../../lib/session";
import { useShellData } from "../../lib/shell-data";
import { radius, useTheme } from "../../lib/theme";
import { useOpenChat } from "./chat-list";
import { Icon, type IconName } from "./icon";
import { RowAvatar, RtlScroll, Sk, SkRows, useAgentRole } from "./kit";
import { clockTime } from "./thread-row";
import { useToast } from "./toast";

type Loaded = { key: string; sections: SearchSection[]; error?: string };

function Highlight({ text, query, color }: { text: string; query: string; color: string }) {
  const { c } = useTheme();
  const range = query ? highlightRange(text, query) : null;
  if (!range) return <Text style={{ color }}>{text}</Text>;
  return (
    <Text style={{ color }}>
      {text.slice(0, range[0])}
      <Text style={{ backgroundColor: `${c.accent}4d`, color: c.text }}>
        {text.slice(range[0], range[1])}
      </Text>
      {text.slice(range[1])}
    </Text>
  );
}

function Hit({
  item,
  query,
  rows,
}: {
  item: SearchResult;
  query: string;
  rows: readonly ChatRow[];
}) {
  const { c } = useTheme();
  const { t, rtl } = useSession();
  const data = useShellData();
  const router = useRouter();
  const toast = useToast();
  const openChat = useOpenChat();
  const role = useAgentRole();
  const agentName = (id?: string | null) =>
    data.agents.find((agent) => agent.id === id)?.name ?? "";
  const gone = () => toast(t("sh_resultGone"));
  const disc = (name: IconName) => (
    <View
      style={{
        width: 44,
        height: 44,
        borderRadius: 22,
        backgroundColor: c.fill,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Icon name={name} size={20} color={c.muted} />
    </View>
  );
  let lead: ReactNode;
  let title: ReactNode;
  let sub: ReactNode;
  let meta: string | null = null;
  let open: () => void;
  switch (item.category) {
    case "chats": {
      const row = rows.find(
        (candidate) => candidate.key === rowKey(item.kind === "group" ? "group" : "agent", item.id),
      );
      const at = row?.entry?.last_message?.created_at;
      lead = row ? (
        <RowAvatar row={row} agents={data.agents} size={44} />
      ) : (
        disc(item.kind === "group" ? "users" : "bot")
      );
      title = <Highlight text={item.title} query={query} color={c.text} />;
      sub = (
        <Highlight
          text={item.snippet || (row ? (row.agent ? role(row.agent) : row.subtitle) : "")}
          query={query}
          color={c.muted}
        />
      );
      meta = at ? clockTime(at) : null;
      open = () => {
        if (!row) return gone();
        void openChat(row);
      };
      break;
    }
    case "messages": {
      // The thread's agent routes the hit, not the speaker: a peer's outcome sits in the asking agent's thread.
      const owner = item.thread_agent_id;
      const row =
        rows.find((candidate) => candidate.threadId === item.thread_id) ??
        (!item.group_id && owner
          ? rows.find((candidate) => candidate.key === rowKey("agent", owner))
          : undefined);
      const speaker =
        item.role === "user" ? t("sh_you") : agentName(item.agent_id) || row?.name || "";
      lead = disc("chat");
      title = <Text style={{ color: c.text }}>{`${row?.name ?? ""} · ${speaker}`}</Text>;
      sub = <Highlight text={item.snippet} query={query} color={c.muted} />;
      meta = item.created_at ? clockTime(item.created_at) : null;
      open = () => {
        if (!row || item.seq == null || !item.thread_id) return gone();
        // The hit's own conversation, not the row's main one; the conversation screen scrolls to `around`.
        if (row.kind === "group")
          router.push({
            pathname: "/group-thread",
            params: { groupId: row.id, around: String(item.seq) },
          });
        else
          router.push({
            pathname: "/thread",
            params: { id: item.thread_id ?? "", around: String(item.seq) },
          });
      };
      break;
    }
    case "tasks":
      lead = disc("task");
      title = <Highlight text={item.title} query={query} color={c.text} />;
      sub = <Highlight text={item.snippet} query={query} color={c.muted} />;
      meta = agentName(item.agent_id);
      open = () => router.push("/tasks");
      break;
    case "files":
      lead = disc("file");
      title = <Highlight text={item.title} query={query} color={c.text} />;
      sub =
        item.snippet && item.snippet !== item.title ? (
          <Highlight text={item.snippet} query={query} color={c.muted} />
        ) : (
          <Text style={{ color: c.muted }}>{t("sh_savedFile")}</Text>
        );
      meta = agentName(item.agent_id);
      open = () => router.push({ pathname: "/artifact", params: { artifactId: item.id } });
      break;
    default: {
      const skill = item.category === "skills";
      lead = disc(skill ? "cpu" : "folder");
      title = (
        <Text style={{ color: c.text }}>
          <Highlight text={item.title} query={query} color={c.text} />
          <Text
            style={{ color: c.muted, fontWeight: "400" }}
          >{` · ${skill ? t("sh_skill") : t("sh_knowledge")}`}</Text>
        </Text>
      );
      sub = <Highlight text={item.snippet} query={query} color={c.muted} />;
      const owner = agentName(item.agent_id);
      meta = owner && owner !== item.title ? owner : null;
      open = () =>
        skill
          ? router.push("/integrations")
          : item.agent_id
            ? router.push({ pathname: "/bot-settings", params: { botId: item.agent_id } })
            : gone();
    }
  }
  return (
    <Pressable
      accessibilityRole="button"
      testID={`search-hit-${item.category}`}
      onPress={open}
      style={({ pressed }) => ({
        flexDirection: rtl ? "row-reverse" : "row",
        alignItems: "center",
        gap: 12,
        minHeight: 64,
        paddingHorizontal: 16,
        paddingVertical: 10,
        backgroundColor: pressed ? c.hover : "transparent",
      })}
    >
      {lead}
      <View style={{ flex: 1, minWidth: 0, gap: 2 }}>
        <Text
          numberOfLines={2}
          style={{ fontSize: 14, fontWeight: "600", textAlign: rtl ? "right" : "left" }}
        >
          {title}
        </Text>
        <Text
          numberOfLines={2}
          style={{ fontSize: 12, lineHeight: 19, textAlign: rtl ? "right" : "left" }}
        >
          {sub}
        </Text>
      </View>
      {meta ? (
        <Text numberOfLines={1} style={{ maxWidth: "25%", color: c.muted, fontSize: 12 }}>
          {meta}
        </Text>
      ) : null}
    </Pressable>
  );
}

const fetchPage =
  (signal?: AbortSignal): SearchFetch =>
  (text, category, limit, offset) =>
    request<SearchResponse>(searchPath(text, category, limit, offset), { signal });

export function SearchSkeleton() {
  return (
    <View style={{ paddingTop: 8 }}>
      <View style={{ flexDirection: "row", gap: 8, paddingHorizontal: 14, paddingVertical: 10 }}>
        <Sk width={60} height={32} round={16} />
        <Sk width={72} height={32} round={16} />
        <Sk width={64} height={32} round={16} />
      </View>
      <SkRows count={3} size={44} />
      <SkRows count={2} size={44} />
    </View>
  );
}

export function UnifiedSearch({
  query,
  tab,
  onTab,
}: {
  query: string;
  tab: SearchTab;
  onTab: (tab: SearchTab) => void;
}) {
  const { c } = useTheme();
  const { t, rtl, errorText } = useSession();
  const lists = useLists();
  const q = query.trim();
  const key = `${tab}|${q}`;
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [more, setMore] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const report = useRef(errorText);
  report.current = errorText;
  useEffect(() => {
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    const timer = setTimeout(
      () => {
        firstSearchPage(q, tab, fetchPage(abort.signal))
          .then((sections) => {
            if (!abort.signal.aborted) setLoaded({ key, sections });
          })
          .catch((error) => {
            if (!abort.signal.aborted && !(error instanceof SessionRequestCancelled))
              setLoaded({ key, sections: [], error: report.current(error) });
          });
      },
      q ? 160 : 0,
    );
    return () => {
      clearTimeout(timer);
      abort.abort();
    };
  }, [key, q, tab]);
  const names: Record<SearchTab, string> = {
    all: t("sh_sAll"),
    chats: t("sh_sChats"),
    messages: t("sh_sMessages"),
    tasks: t("sh_sTasks"),
    files: t("sh_sFiles"),
    other: t("sh_sOther"),
  };
  const tabs = (
    <RtlScroll
      accessibilityRole="tablist"
      accessibilityLabel={t("sh_filterSearch")}
      style={{ flexGrow: 0 }}
      contentContainerStyle={{
        gap: 8,
        paddingHorizontal: 14,
        paddingVertical: 10,
      }}
    >
      {SEARCH_TABS.map((name) => (
        <Pressable
          key={name}
          accessibilityRole="tab"
          accessibilityState={{ selected: tab === name }}
          accessibilityLabel={names[name]}
          onPress={() => onTab(name)}
          style={{
            minHeight: 34,
            paddingHorizontal: 14,
            justifyContent: "center",
            borderRadius: radius.pill,
            borderWidth: 1,
            borderColor: tab === name ? "transparent" : c.line,
            backgroundColor: tab === name ? c.primary : c.surface,
          }}
        >
          <Text
            style={{
              color: tab === name ? c["on-primary"] : c.text,
              fontSize: 14,
              fontWeight: tab === name ? "600" : "400",
            }}
          >
            {names[name]}
          </Text>
        </Pressable>
      ))}
    </RtlScroll>
  );
  if (!loaded || loaded.key !== key) return <SearchSkeleton />;
  if (loaded.error)
    return (
      <View>
        {tabs}
        <View accessibilityRole="alert" style={{ padding: 48, alignItems: "center", gap: 12 }}>
          <Icon name="alert" size={32} color={c.muted} />
          <Text style={{ color: c.muted, textAlign: "center" }}>{loaded.error}</Text>
        </View>
      </View>
    );
  const hasHistory = lists.rows.some((row) => row.entry?.last_message);
  const titles: Record<SearchSection["tab"], string> = q
    ? {
        chats: t("sh_mAgentsGroups"),
        messages: t("sh_mMatching"),
        tasks: t("sh_sTasks"),
        files: t("sh_sFiles"),
        other: t("sh_sOther"),
      }
    : {
        chats: hasHistory ? t("sh_mRecentChats") : t("sh_mAgentsGroups"),
        messages: t("sh_mRecentMessages"),
        tasks: t("sh_sTasks"),
        files: t("sh_sFiles"),
        other: t("sh_sOther"),
      };
  const loadMore = async (section: SearchSection) => {
    setMore(true);
    try {
      const next = await moreSearchItems(q, section, fetchPage());
      setLoaded((current) =>
        current && current.key === key
          ? {
              ...current,
              sections: current.sections.map((row) => (row.tab === section.tab ? next : row)),
            }
          : current,
      );
    } catch {
      /* the button stays for another try */
    } finally {
      setMore(false);
    }
  };
  const body = loaded.sections
    .filter((section) => section.items.length)
    .map((section) => {
      const limit =
        tab === "all" ? (q ? 3 : section.tab === "chats" ? 4 : 2) : section.items.length;
      const shown = section.items.slice(0, limit);
      const rest = tab === "all" ? section.count > limit : section.count > section.items.length;
      return (
        <View
          key={section.tab}
          testID={`search-section-${section.tab}`}
          style={{ marginBottom: 12 }}
        >
          <View
            style={{
              flexDirection: rtl ? "row-reverse" : "row",
              justifyContent: "space-between",
              paddingHorizontal: 16,
              paddingTop: 14,
              paddingBottom: 6,
            }}
          >
            <Text
              accessibilityRole="header"
              style={{ color: c.muted, fontSize: 12, fontWeight: "600" }}
            >
              {titles[section.tab]}
            </Text>
            {q || tab !== "all" ? (
              <Text style={{ color: c.muted, fontSize: 12 }}>{section.count}</Text>
            ) : null}
          </View>
          {shown.map((item) => (
            <Hit key={`${item.category}:${item.id}`} item={item} query={q} rows={lists.rows} />
          ))}
          {rest ? (
            <Pressable
              accessibilityRole="button"
              disabled={more}
              onPress={() => (tab === "all" ? onTab(section.tab) : void loadMore(section))}
              style={{ minHeight: 40, alignItems: "center", justifyContent: "center" }}
            >
              <Text style={{ color: c.text, fontSize: 14, fontWeight: "600" }}>
                {tab === "all"
                  ? q
                    ? fill(t("sh_showAllN"), section.count)
                    : t("sh_showAll")
                  : t("sh_showMore")}
              </Text>
            </Pressable>
          ) : null}
        </View>
      );
    });
  const browseEmpty: Record<SearchTab, string> = {
    all: t("sh_browseEmpty"),
    chats: t("sh_noChatsAvail"),
    messages: t("sh_noMessagesSaved"),
    tasks: t("sh_noTasksSaved"),
    files: t("sh_noFilesAvail"),
    other: t("sh_noKnowledgeSaved"),
  };
  const emptyBlock = (heading: string, text: string) => (
    <View style={{ padding: 48, alignItems: "center", gap: 8 }}>
      <Icon name="search" size={32} color={c.muted} />
      <Text accessibilityRole="header" style={{ color: c.text, fontSize: 16, fontWeight: "600" }}>
        {heading}
      </Text>
      <Text style={{ color: c.muted, fontSize: 12, lineHeight: 22, textAlign: "center" }}>
        {text}
      </Text>
    </View>
  );
  return (
    <ScrollView
      testID="unified-search"
      keyboardShouldPersistTaps="handled"
      contentContainerStyle={{ paddingBottom: 120 }}
    >
      {tabs}
      <View accessibilityLabel={q ? t("sh_searchResults") : t("sh_browseContent")}>
        {body.length
          ? body
          : q && tab === "all"
            ? emptyBlock(t("sh_noResultsTitle"), fill(t("sh_noResultsFor"), { q }))
            : q
              ? emptyBlock(t("sh_noResultsCat"), t("sh_chooseAll"))
              : emptyBlock(t("sh_emptySection"), browseEmpty[tab])}
      </View>
      {!q && tab === "all" ? (
        <View
          style={{
            flexDirection: rtl ? "row-reverse" : "row",
            alignItems: "center",
            gap: 8,
            padding: 16,
          }}
        >
          <Icon name="search" size={18} color={c.faint} />
          <Text style={{ flex: 1, color: c.faint, fontSize: 12 }}>{t("sh_typeToSearch")}</Text>
        </View>
      ) : null}
    </ScrollView>
  );
}
