import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { Icon } from "@lonora/ui-web";
import { ConversationInbox } from "../pages/shell/conversation-inbox";
import { useShellData } from "./data";
import { SkChats } from "./Skeleton";

/* The desktop list pane: head (title, new chat), the search pill, then the conversation rows. */
export function DesktopList({
  query,
  onQuery,
  selected,
  onOpen,
  onNewChat,
}: {
  query: string;
  onQuery: (query: string) => void;
  selected?: string;
  onOpen: (path: string) => void;
  onNewChat: () => void;
}) {
  const data = useShellData();
  const loading = data.agentsLoading || data.groupsLoading || data.inboxLoading;
  return (
    <aside className="desktop-list" aria-label={t`Chat list`}>
      <div className="desktop-list-head">
        <h2>
          <Trans>Chats</Trans>
        </h2>
        <button type="button" className="icon" aria-label={t`New chat`} onClick={onNewChat}>
          <Icon name="plus" />
        </button>
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
        {loading && !data.agents.length && !data.groups.length ? (
          <SkChats />
        ) : (
          <ConversationInbox
            agents={data.agents}
            groups={data.groups}
            entries={data.inbox}
            loading={loading}
            error={data.inboxError}
            busyIds={data.busyIds}
            onOpen={onOpen}
            onCreate={onNewChat}
            onRetry={data.refresh}
            query={query}
            searching={false}
            onQueryChange={onQuery}
            selected={selected}
          />
        )}
      </div>
    </aside>
  );
}
