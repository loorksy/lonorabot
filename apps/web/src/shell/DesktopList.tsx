import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { archivedRowSummary, filterRows } from "@lonora/core";
import { Icon } from "@lonora/ui-web";
import { useShellData } from "./data";
import { listsApi } from "./lists/api";
import { ChatList } from "./lists/ChatList";
import { PopItem, PopSep, usePopover } from "./lists/Popover";
import { SelBar } from "./lists/Selection";
import { useLists } from "./lists/state";
import { type SearchTab, UnifiedSearch } from "./lists/UnifiedSearch";
import { useNavigation } from "./navigation";
import { SkChats } from "./Skeleton";

/* The desktop list pane: head (title, + new chat, ⋮ list menu; the selection toolbar while
   selecting), the search pill, then the rows, or the search results while a query is typed. */
export function DesktopList({
  query,
  onQuery,
  tab,
  onTab,
  selected,
  onNewChat,
}: {
  query: string;
  onQuery: (query: string) => void;
  tab: SearchTab;
  onTab: (tab: SearchTab) => void;
  selected?: string;
  onNewChat: () => void;
}) {
  const data = useShellData();
  const lists = useLists();
  const popover = usePopover();
  const nav = useNavigation();
  const loading = data.agentsLoading || data.groupsLoading || data.inboxLoading;
  const menu = (anchor: HTMLElement) =>
    popover.open(
      anchor,
      <>
        <PopItem
          icon="userPlus"
          label={<Trans>New agent</Trans>}
          onSelect={() => nav.go("/app/new-agent")}
        />
        <PopItem
          icon="users"
          label={<Trans>New group</Trans>}
          onSelect={() => nav.go("/app/new-group")}
        />
        <PopItem
          icon="bot"
          label={<Trans>Manage agents</Trans>}
          onSelect={() => nav.go("/app/agents")}
        />
        <PopSep />
        <PopItem
          icon="check"
          label={<Trans>Select chats</Trans>}
          onSelect={() => {
            const first = filterRows(lists.rows, lists.filter, data.chatLists)[0];
            if (first) lists.start(first.key);
          }}
        />
        {archivedRowSummary(lists.rows).count > 0 && (
          <PopItem
            icon="archive"
            label={<Trans>Archived</Trans>}
            onSelect={() => nav.go("/app/archived")}
          />
        )}
        <PopItem
          icon="checks"
          label={<Trans>Mark all as read</Trans>}
          onSelect={() => void listsApi.readAll().then(data.patchInbox).catch(lists.failed)}
        />
      </>,
      t`List options`,
    );
  return (
    <aside className="desktop-list" aria-label={t`Chat list`}>
      <div className="desktop-list-head">
        {lists.selected ? (
          <SelBar />
        ) : (
          <>
            <h2>
              <Trans>Chats</Trans>
            </h2>
            <button type="button" className="icon" aria-label={t`New chat`} onClick={onNewChat}>
              <Icon name="plus" />
            </button>
            <button
              type="button"
              className="icon"
              aria-label={t`List options`}
              aria-haspopup="menu"
              aria-expanded="false"
              onClick={(event) => menu(event.currentTarget)}
            >
              <Icon name="more" />
            </button>
          </>
        )}
      </div>
      <label className={`list-search${query.trim() ? " has-query" : ""}`}>
        <Icon name="search" />
        <input
          id="desktop-search"
          type="search"
          value={query}
          placeholder={t`Search chats, messages and tasks`}
          aria-label={t`Search in Lonora`}
          autoComplete="off"
          spellCheck={false}
          onChange={(event) => onQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              onQuery("");
            }
          }}
        />
        <button
          type="button"
          className="search-clear"
          aria-label={t`Clear search`}
          onClick={() => onQuery("")}
        >
          <Icon name="close" />
        </button>
      </label>
      <div className="desktop-threads" id="desktop-threads">
        {query.trim() ? (
          <UnifiedSearch query={query} tab={tab} onTab={onTab} />
        ) : loading && !data.agents.length && !data.groups.length ? (
          <SkChats />
        ) : (
          <ChatList selectedKey={selected} />
        )}
      </div>
    </aside>
  );
}
