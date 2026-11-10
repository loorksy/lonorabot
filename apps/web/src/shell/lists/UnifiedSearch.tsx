import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { SearchCategory, SearchResponse, SearchResult } from "@lonora/contracts";
import { type ChatRow, highlightRange, rowKey } from "@lonora/core";
import { Icon, type IconName } from "@lonora/ui-web";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { isRequestCancelled, request } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useShellData } from "../data";
import { useNavigation } from "../navigation";
import { SkPage, SkPill, SkRows } from "../Skeleton";
import { useToast } from "../Toast";
import { chatPath } from "./ChatList";
import { useLists } from "./state";
import { clockTime, RowAvatar, rowSubtitle } from "./ThreadRow";

/* UnifiedSearch: one engine (GET /api/search, owner-wide, never an agent's) behind the
   header field on phones and the list pane's field on desktop. An empty query browses
   what is recent; categories are tabs with counts; الكل shows a few of each, a tab pages
   by 32. Only the latest query lands. */
export type SearchTab = "all" | "chats" | "messages" | "tasks" | "files" | "other";
export const SEARCH_TABS: SearchTab[] = ["all", "chats", "messages", "tasks", "files", "other"];
type Section = { tab: Exclude<SearchTab, "all">; items: SearchResult[]; count: number };
type Loaded = { key: string; sections: Section[]; error?: unknown };
const PAGE = 32;
const sources: Record<Exclude<SearchTab, "all">, SearchCategory[]> = {
  chats: ["chats"],
  messages: ["messages"],
  tasks: ["tasks"],
  files: ["files"],
  other: ["knowledge", "skills"],
};

function fetchSearch(
  q: string,
  category: SearchCategory | null,
  limit: number,
  offset: number,
  signal: AbortSignal,
) {
  const params = new URLSearchParams({ q, limit: String(limit), offset: String(offset) });
  if (category) params.set("category", category);
  return request<SearchResponse>(`/search?${params}`, { signal });
}

async function firstPage(q: string, tab: SearchTab, signal: AbortSignal): Promise<Section[]> {
  if (tab === "all") {
    const response = await fetchSearch(q, null, q ? 3 : 4, 0, signal);
    return (Object.keys(sources) as Exclude<SearchTab, "all">[]).map((name) => ({
      tab: name,
      items: sources[name].flatMap((category) => response.results[category] ?? []),
      count: sources[name].reduce((sum, category) => sum + (response.counts[category] ?? 0), 0),
    }));
  }
  const responses = await Promise.all(
    sources[tab].map((category) => fetchSearch(q, category, PAGE, 0, signal)),
  );
  return [
    {
      tab,
      items: responses.flatMap((response, i) => response.results[sources[tab][i]] ?? []),
      count: responses.reduce(
        (sum, response, i) => sum + (response.counts[sources[tab][i]] ?? 0),
        0,
      ),
    },
  ];
}

function Highlight({ text, query }: { text: string; query: string }) {
  const range = query ? highlightRange(text, query) : null;
  if (!range) return <>{text}</>;
  return (
    <>
      {text.slice(0, range[0])}
      <mark>{text.slice(range[0], range[1])}</mark>
      {text.slice(range[1])}
    </>
  );
}

export function SearchSkeleton() {
  return (
    <SkPage>
      <div className="sk-chips">
        <SkPill width={60} height={32} />
        <SkPill width={72} height={32} />
        <SkPill width={64} height={32} />
      </div>
      <SkRows count={3} size={44} />
      <SkRows count={2} size={44} />
    </SkPage>
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
  const data = useShellData();
  const nav = useNavigation();
  const toast = useToast();
  const agentName = (id?: string | null) =>
    data.agents.find((agent) => agent.id === id)?.name ?? "";
  const gone = () => toast(t`The result is no longer available.`);
  let lead: ReactNode;
  let title: ReactNode;
  let sub: ReactNode;
  let meta: ReactNode = null;
  let open: () => void;
  const icon = (name: IconName) => (
    <span className="search-hit-icon">
      <Icon name={name} />
    </span>
  );
  switch (item.category) {
    case "chats": {
      const row = rows.find(
        (candidate) => candidate.key === rowKey(item.kind === "group" ? "group" : "agent", item.id),
      );
      const at = row?.entry?.last_message?.created_at;
      lead = row ? (
        <RowAvatar row={row} agents={data.agents} />
      ) : (
        icon(item.kind === "group" ? "users" : "bot")
      );
      title = <Highlight text={item.title} query={query} />;
      sub = <Highlight text={item.snippet || (row ? rowSubtitle(row) : "")} query={query} />;
      meta = at ? (
        <time className="search-hit-meta" dir="ltr" dateTime={at}>
          {clockTime(at)}
        </time>
      ) : null;
      open = () => (row ? nav.go(chatPath(row)) : gone());
      break;
    }
    case "messages": {
      // A hit in one of an agent's other conversations (a subagent run, a ticket, a new
      // thread) belongs to that agent's row; a group shows only its own thread. The thread's
      // agent routes it, not the speaker: a peer's outcome sits in the asking agent's thread.
      const owner = item.thread_agent_id;
      const row =
        rows.find((candidate) => candidate.threadId === item.thread_id) ??
        (!item.group_id && owner
          ? rows.find((candidate) => candidate.key === rowKey("agent", owner))
          : undefined);
      const speaker = item.role === "user" ? t`You` : agentName(item.agent_id) || row?.name || "";
      lead = icon("chat");
      title = (
        <>
          <bdi>{row?.name ?? ""}</bdi> · <bdi>{speaker}</bdi>
        </>
      );
      sub = <Highlight text={item.snippet} query={query} />;
      meta = item.created_at ? (
        <time className="search-hit-meta" dir="ltr" dateTime={item.created_at}>
          {clockTime(item.created_at)}
        </time>
      ) : null;
      open = () => {
        if (!row || item.seq == null || !item.thread_id) return gone();
        // The hit's own conversation, not the row's main one.
        const path =
          row.kind === "agent"
            ? `/app/${row.id}?thread=${encodeURIComponent(item.thread_id)}`
            : chatPath(row);
        nav.go(`${path}${path.includes("?") ? "&" : "?"}around=${item.seq}`);
      };
      break;
    }
    case "tasks":
      lead = icon("task");
      title = <Highlight text={item.title} query={query} />;
      sub = <Highlight text={item.snippet} query={query} />;
      meta = <span className="search-hit-meta">{agentName(item.agent_id)}</span>;
      open = () => nav.go("/app/tasks");
      break;
    case "files":
      lead = icon("file");
      title = <Highlight text={item.title} query={query} />;
      sub =
        item.snippet && item.snippet !== item.title ? (
          <Highlight text={item.snippet} query={query} />
        ) : (
          t`Saved file`
        );
      meta = <span className="search-hit-meta">{agentName(item.agent_id)}</span>;
      open = () => nav.go(`/app/artifacts/${encodeURIComponent(item.id)}`);
      break;
    default: {
      const skill = item.category === "skills";
      lead = icon(skill ? "cpu" : "folder");
      title = (
        <>
          <Highlight text={item.title} query={query} />{" "}
          <small className="muted">
            · {skill ? t`Skill` : t({ message: "Knowledge", context: "search hit" })}
          </small>
        </>
      );
      sub = <Highlight text={item.snippet} query={query} />;
      const owner = agentName(item.agent_id);
      meta =
        owner && owner !== item.title ? <span className="search-hit-meta">{owner}</span> : null;
      open = () =>
        skill
          ? nav.go(`/app/skills/${encodeURIComponent(item.id)}`)
          : nav.go(`/app/knowledge?agent=${encodeURIComponent(item.agent_id ?? "")}`);
    }
  }
  return (
    <button type="button" className="search-hit-row" data-search-hit={item.category} onClick={open}>
      {lead}
      <span className="search-hit-body">
        <span className="search-hit-title">{title}</span>
        <span className="search-hit-sub">
          <bdi>{sub}</bdi>
        </span>
      </span>
      {meta}
    </button>
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
  const lists = useLists();
  const q = query.trim();
  const key = `${tab}|${q}`;
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [more, setMore] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    const timer = setTimeout(
      () => {
        firstPage(q, tab, abort.signal)
          .then((sections) => {
            if (!abort.signal.aborted) setLoaded({ key, sections });
          })
          .catch((error) => {
            if (!abort.signal.aborted && !isRequestCancelled(error))
              setLoaded({ key, sections: [], error });
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
    all: t({ message: "All", context: "search tab" }),
    chats: t`Chats`,
    messages: t`Messages`,
    tasks: t`Tasks`,
    files: t`Files`,
    other: t`Knowledge and skills`,
  };
  const tabs = (
    <div className="search-tabs" role="tablist" aria-label={t`Filter the search results`}>
      {SEARCH_TABS.map((name) => (
        <button
          type="button"
          role="tab"
          key={name}
          aria-selected={tab === name}
          onClick={() => onTab(name)}
        >
          {names[name]}
        </button>
      ))}
    </div>
  );
  if (!loaded || loaded.key !== key) return <SearchSkeleton />;
  if (loaded.error != null)
    return (
      <div className="search-surface">
        {tabs}
        <div className="search-empty" role="alert">
          <Icon name="alert" />
          <p>{userError(loaded.error)}</p>
        </div>
      </div>
    );
  const hasHistory = lists.rows.some((row) => row.entry?.last_message);
  const titles: Record<Exclude<SearchTab, "all">, string> = q
    ? {
        chats: t`Agents and groups`,
        messages: t`Matching messages`,
        tasks: t`Tasks`,
        files: t`Files`,
        other: t`Knowledge and skills`,
      }
    : {
        chats: hasHistory ? t`Recent chats` : t`Agents and groups`,
        messages: t`Recent messages`,
        tasks: t`Tasks`,
        files: t`Files`,
        other: t`Knowledge and skills`,
      };
  const loadMore = async (section: Section) => {
    setMore(true);
    try {
      const abort = new AbortController();
      const done = new Map(
        sources[section.tab].map((category) => [
          category,
          section.items.filter((item) => item.category === category).length,
        ]),
      );
      const pages = await Promise.all(
        sources[section.tab].map((category) =>
          fetchSearch(q, category, PAGE, done.get(category) ?? 0, abort.signal),
        ),
      );
      const fresh = pages.flatMap((page, i) => page.results[sources[section.tab][i]] ?? []);
      setLoaded((current) =>
        current && current.key === key
          ? {
              ...current,
              sections: current.sections.map((row) =>
                row.tab === section.tab ? { ...row, items: [...row.items, ...fresh] } : row,
              ),
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
        <section className="search-section" key={section.tab} data-search-section={section.tab}>
          <div className="search-section-head">
            <h2>{titles[section.tab]}</h2>
            {(q || tab !== "all") && <span className="search-count">{section.count}</span>}
          </div>
          {shown.map((item) => (
            <Hit key={`${item.category}:${item.id}`} item={item} query={q} rows={lists.rows} />
          ))}
          {rest && (
            <button
              type="button"
              className="search-more"
              disabled={more}
              onClick={() => (tab === "all" ? onTab(section.tab) : void loadMore(section))}
            >
              {tab === "all"
                ? q
                  ? t`Show all results (${section.count})`
                  : t`Show all`
                : t`Show more`}
            </button>
          )}
        </section>
      );
    });
  const any = body.length > 0;
  const browseEmpty: Record<SearchTab, string> = {
    all: t`Start a chat or add a task for it to appear here.`,
    chats: t`No chats are available yet.`,
    messages: t`No saved messages yet. They appear here once a chat starts.`,
    tasks: t`No saved tasks yet.`,
    files: t`No files are available yet.`,
    other: t`No saved knowledge or skills yet.`,
  };
  return (
    <div className="search-surface">
      {tabs}
      <section id="search-results" aria-label={q ? t`Search results` : t`Browse Lonora's content`}>
        {any ? (
          body
        ) : q && tab === "all" ? (
          <div className="search-empty">
            <Icon name="search" />
            <h2>
              <Trans>No results</Trans>
            </h2>
            <p>
              <Trans>We found no results for «{q}». Try a shorter word or a different term.</Trans>
            </p>
          </div>
        ) : q ? (
          <div className="search-empty">
            <Icon name="search" />
            <h2>
              <Trans>No results in this category</Trans>
            </h2>
            <p>
              <Trans>You can choose «All» to search the other sections.</Trans>
            </p>
          </div>
        ) : (
          <div className="search-empty">
            <Icon name="search" />
            <h2>
              <Trans>There is no content in this section yet</Trans>
            </h2>
            <p>{browseEmpty[tab]}</p>
          </div>
        )}
      </section>
      {!q && tab === "all" && (
        <div className="search-tip">
          <Icon name="search" />
          <span>
            <Trans>Type a word to search chats, messages, tasks and files.</Trans>
          </span>
        </div>
      )}
    </div>
  );
}
