/**
 * The unified search's paging, shared by Web and Mobile: one engine (GET /api/search),
 * the tabs map onto its categories; «الكل» shows a few of each, a tab pages by 32.
 */
import type { SearchCategory, SearchResponse, SearchResult } from "@lonora/contracts";

export type SearchTab = "all" | "chats" | "messages" | "tasks" | "files" | "other";
export const SEARCH_TABS: SearchTab[] = ["all", "chats", "messages", "tasks", "files", "other"];
export type SearchSection = {
  tab: Exclude<SearchTab, "all">;
  items: SearchResult[];
  count: number;
};
export const SEARCH_PAGE = 32;
export const SEARCH_SOURCES: Record<Exclude<SearchTab, "all">, SearchCategory[]> = {
  chats: ["chats"],
  messages: ["messages"],
  tasks: ["tasks"],
  files: ["files"],
  other: ["knowledge", "skills"],
};
export type SearchFetch = (
  q: string,
  category: SearchCategory | null,
  limit: number,
  offset: number,
) => Promise<SearchResponse>;

export const searchPath = (
  q: string,
  category: SearchCategory | null,
  limit: number,
  offset: number,
) => {
  const params = new URLSearchParams({ q, limit: String(limit), offset: String(offset) });
  if (category) params.set("category", category);
  return `/search?${params}`;
};

/** The first screen of a tab for a query ("" browses what is recent). */
export async function firstSearchPage(
  q: string,
  tab: SearchTab,
  fetchPage: SearchFetch,
): Promise<SearchSection[]> {
  if (tab === "all") {
    const response = await fetchPage(q, null, q ? 3 : 4, 0);
    return (Object.keys(SEARCH_SOURCES) as Exclude<SearchTab, "all">[]).map((name) => ({
      tab: name,
      items: SEARCH_SOURCES[name].flatMap((category) => response.results[category] ?? []),
      count: SEARCH_SOURCES[name].reduce(
        (sum, category) => sum + (response.counts[category] ?? 0),
        0,
      ),
    }));
  }
  const responses = await Promise.all(
    SEARCH_SOURCES[tab].map((category) => fetchPage(q, category, SEARCH_PAGE, 0)),
  );
  return [
    {
      tab,
      items: responses.flatMap((response, i) => response.results[SEARCH_SOURCES[tab][i]] ?? []),
      count: responses.reduce(
        (sum, response, i) => sum + (response.counts[SEARCH_SOURCES[tab][i]] ?? 0),
        0,
      ),
    },
  ];
}

/** The next 32 of one section, appended after what it already shows. */
export async function moreSearchItems(
  q: string,
  section: SearchSection,
  fetchPage: SearchFetch,
): Promise<SearchSection> {
  const sources = SEARCH_SOURCES[section.tab];
  const pages = await Promise.all(
    sources.map((category) =>
      fetchPage(
        q,
        category,
        SEARCH_PAGE,
        section.items.filter((item) => item.category === category).length,
      ),
    ),
  );
  return {
    ...section,
    items: [...section.items, ...pages.flatMap((page, i) => page.results[sources[i]] ?? [])],
  };
}
