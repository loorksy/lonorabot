import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import {
  archivedRowSummary,
  archivedRows,
  BUILTIN_FILTERS,
  type ChatRow,
  filterRows,
  type ListFilter,
  listIdOf,
} from "@lonora/core";
import { Icon } from "@lonora/ui-web";
import {
  type MouseEvent,
  type PointerEvent,
  useCallback,
  useLayoutEffect,
  useMemo,
  useRef,
  useSyncExternalStore,
} from "react";
import { useLocation } from "react-router-dom";
import {
  type OutgoingIntent,
  outgoingKey,
  outgoingMessages,
  outgoingVersion,
  subscribeOutgoing,
} from "../../lib/outgoing-messages";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import { hideFiltersInitially, syncFilters } from "../chrome";
import { useShellData } from "../data";
import { isDesktop } from "../motion";
import { useNavigation } from "../navigation";
import { SkPage, SkRows } from "../Skeleton";
import { useToast } from "../Toast";
import { listsApi } from "./api";
import { useListSheets } from "./ListSheets";
import { useLists } from "./state";
import { ThreadRow } from "./ThreadRow";

const placed = new Set<string>();

export const chatPath = (row: ChatRow) =>
  row.kind === "group"
    ? `/app/g/${row.id}`
    : `/app/${row.id}${row.threadId ? `?thread=${encodeURIComponent(row.threadId)}` : ""}`;

/** The newest message of each thread still in this device's outbox. */
function useOutgoing(rows: readonly ChatRow[]) {
  const { owner } = useClient();
  const version = useSyncExternalStore(subscribeOutgoing, outgoingVersion);
  return useMemo(() => {
    void version;
    const latest = new Map<string, OutgoingIntent>();
    for (const row of rows) {
      if (!row.threadId) continue;
      const pending = outgoingMessages(outgoingKey(owner.id, row.threadId));
      const last = pending.at(-1);
      if (last) latest.set(row.threadId, last);
    }
    return latest;
  }, [rows, owner.id, version]);
}

/* Long-press (430ms, touch) or right-click starts the selection; while selecting a tap
   toggles; the click that ends a long-press is swallowed. */
function useRowGestures() {
  const lists = useLists();
  const press = useRef<{
    row: HTMLElement;
    id: number;
    x: number;
    y: number;
    timer: number;
  } | null>(null);
  const lastPress = useRef(0);
  const swallowUntil = useRef(0);
  const select = useCallback(
    (key: string, touch: boolean) => {
      if (Date.now() - lastPress.current < 650) return;
      lastPress.current = Date.now();
      if (touch) swallowUntil.current = Date.now() + 450;
      if (lists.selected) lists.toggle(key);
      else lists.start(key);
    },
    [lists],
  );
  const cancel = () => {
    const p = press.current;
    if (!p) return;
    clearTimeout(p.timer);
    p.row.classList.remove("pressing");
    press.current = null;
  };
  return {
    onPointerDown: (event: PointerEvent<HTMLElement>) => {
      const row = (event.target as Element).closest<HTMLElement>(".thread[data-key]");
      if (!row || event.button > 0 || event.pointerType === "mouse") return;
      cancel();
      row.classList.add("pressing");
      const key = row.dataset.key ?? "";
      press.current = {
        row,
        id: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        timer: window.setTimeout(() => {
          cancel();
          select(key, true);
        }, 430),
      };
    },
    onPointerMove: (event: PointerEvent<HTMLElement>) => {
      const p = press.current;
      if (p && event.pointerId === p.id && Math.hypot(event.clientX - p.x, event.clientY - p.y) > 8)
        cancel();
    },
    onPointerUp: cancel,
    onPointerCancel: cancel,
    onContextMenu: (event: MouseEvent<HTMLElement>) => {
      const row = (event.target as Element).closest<HTMLElement>(".thread[data-key]");
      if (!row) return;
      event.preventDefault();
      const touch = Boolean(press.current);
      cancel();
      select(row.dataset.key ?? "", touch);
    },
    onClickCapture: (event: MouseEvent<HTMLElement>) => {
      const row = (event.target as Element).closest<HTMLElement>(".thread[data-key]");
      if (!row) return;
      if (Date.now() < swallowUntil.current) {
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      if (!lists.selected) return;
      event.preventDefault();
      event.stopPropagation();
      lists.toggle(row.dataset.key ?? "");
    },
  };
}

function Rows({ rows, selectedKey }: { rows: readonly ChatRow[]; selectedKey?: string }) {
  const data = useShellData();
  const lists = useLists();
  const nav = useNavigation();
  const outgoing = useOutgoing(rows);
  const open = useCallback((row: ChatRow) => nav.go(chatPath(row)), [nav]);
  return rows.map((row) => (
    <ThreadRow
      key={row.key}
      row={row}
      agents={data.agents}
      current={selectedKey === row.key}
      selecting={lists.selected !== null}
      picked={lists.selected?.has(row.key) ?? false}
      working={row.kind === "agent" && data.busyIds.has(row.id)}
      outgoing={row.threadId ? outgoing.get(row.threadId) : undefined}
      onOpen={open}
    />
  ));
}

const Empty = ({ children }: { children: React.ReactNode }) => (
  <div className="empty">
    <Icon name="folder" />
    <div>{children}</div>
  </div>
);

/* The filters: الكل · غير مقروءة · المفضلة · الوكلاء · المجموعات, the owner's lists, «+». */
function Filters() {
  const data = useShellData();
  const lists = useLists();
  const sheets = useListSheets();
  const press = useRef<{ x: number; y: number; timer: number } | null>(null);
  const eat = useRef<string | null>(null);
  const names: Record<(typeof BUILTIN_FILTERS)[number], string> = {
    all: t({ message: "All", context: "chat filter" }),
    unread: t({ message: "Unread", context: "chat filter" }),
    fav: t({ message: "Favourites", context: "chat filter" }),
    agents: t`Agents`,
    groups: t`Groups`,
  };
  const choose = (filter: ListFilter) => {
    lists.setFilter(filter);
    if (isDesktop()) document.getElementById("desktop-threads")?.scrollTo({ top: 0 });
  };
  const endPress = () => {
    if (press.current) clearTimeout(press.current.timer);
    press.current = null;
  };
  return (
    // biome-ignore lint/a11y/useSemanticElements: the reference's group of filter tabs; a fieldset would make them a form
    <div
      className="list-filters"
      role="group"
      aria-label={t`Filter chats`}
      data-rest={lists.filter === "all" ? "1" : "0"}
    >
      {BUILTIN_FILTERS.map((filter) => (
        <button
          type="button"
          key={filter}
          className={`chip${lists.filter === filter ? " active" : ""}`}
          aria-pressed={lists.filter === filter}
          onClick={() => choose(filter)}
        >
          {names[filter]}
        </button>
      ))}
      {data.chatLists.map((list) => {
        const filter: ListFilter = `list:${list.id}`;
        return (
          <button
            type="button"
            key={list.id}
            className={`chip list-chip${lists.filter === filter ? " active" : ""}`}
            data-list={list.id}
            aria-pressed={lists.filter === filter}
            onPointerDown={(event) => {
              const chip = event.currentTarget;
              endPress();
              // A right-click opens the menu through contextmenu; only a held press waits.
              if (event.button > 0) return;
              press.current = {
                x: event.clientX,
                y: event.clientY,
                timer: window.setTimeout(() => {
                  press.current = null;
                  eat.current = list.id;
                  sheets.listMenu(list, chip);
                }, 480),
              };
            }}
            onPointerMove={(event) => {
              const p = press.current;
              if (p && Math.hypot(event.clientX - p.x, event.clientY - p.y) > 8) endPress();
            }}
            onPointerUp={endPress}
            onPointerCancel={endPress}
            onContextMenu={(event) => {
              event.preventDefault();
              endPress();
              sheets.listMenu(list, event.currentTarget);
            }}
            onClick={() => {
              if (eat.current === list.id) {
                eat.current = null;
                return;
              }
              choose(filter);
            }}
          >
            {list.name}
          </button>
        );
      })}
      <button
        type="button"
        className="chip chip-add"
        aria-label={t`New list`}
        title={t`New list`}
        onClick={() => sheets.newList()}
      >
        <Icon name="plus" />
      </button>
    </div>
  );
}

/** The «المؤرشفة» row on top of الكل: the unread archived count in the accent, else the count. */
function ArchiveRow() {
  const lists = useLists();
  const nav = useNavigation();
  const { count, unread } = archivedRowSummary(lists.rows);
  if (!count) return null;
  return (
    <button
      type="button"
      className="row thread archive-row"
      onClick={() => nav.go("/app/archived")}
    >
      <span className="arch-ic">
        <Icon name="archive" />
      </span>
      <span className="body">
        <strong>
          <Trans>Archived</Trans>
        </strong>
      </span>
      <span className={`arch-n${unread ? " on" : ""}`}>{unread || count}</span>
    </button>
  );
}

/* #chat-rows: the phone's chat list and the desktop list pane share it. On phones the filters
   rest hidden above the first row and appear when the list is pulled down. */
export function ChatList({ selectedKey }: { selectedKey?: string }) {
  const data = useShellData();
  const lists = useLists();
  const sheets = useListSheets();
  const gestures = useRowGestures();
  const host = useRef<HTMLElement>(null);
  const visible = useMemo(
    () => filterRows(lists.rows, lists.filter, data.chatLists),
    [lists.rows, lists.filter, data.chatLists],
  );
  const listId = listIdOf(lists.filter);
  const activeList = listId ? data.chatLists.find((list) => list.id === listId) : undefined;
  // A history entry the list has not been placed in yet rests with its filters hidden;
  // returning to one keeps where it was (the scroll memory restores it).
  const entry = useLocation().key;
  useLayoutEffect(() => {
    const main = host.current?.closest("main");
    if (!main || isDesktop()) return;
    if (!placed.has(entry)) {
      placed.add(entry);
      hideFiltersInitially(main);
    }
    syncFilters(main);
  }, [entry]);
  useLayoutEffect(() => {
    // A filter other than الكل keeps the filters in view.
    void lists.filter;
    const main = host.current?.closest("main");
    if (main && !isDesktop()) syncFilters(main);
  }, [lists.filter]);
  const empty =
    lists.filter === "unread" ? (
      <Trans>No unread messages.</Trans>
    ) : lists.filter === "fav" ? (
      <Trans>Add chats to your favourites: press and hold a chat, then ⋮.</Trans>
    ) : (
      <Trans>No chats.</Trans>
    );
  return (
    <section
      id="chat-rows"
      ref={host}
      data-testid="conversation-inbox"
      aria-label={t`Conversations`}
      {...gestures}
    >
      <Filters />
      {data.inboxError != null && (
        <div className="note" role="alert">
          {userError(data.inboxError)}{" "}
          <button type="button" className="btn small outline" onClick={data.refresh}>
            <Trans>Retry</Trans>
          </button>
        </div>
      )}
      {lists.filter === "all" && <ArchiveRow />}
      {visible.length ? (
        <div className="thread-list">
          <Rows rows={visible} selectedKey={selectedKey} />
        </div>
      ) : activeList ? (
        <div className="empty list-empty">
          <Icon name="layers" />
          <div>
            <Trans>No chats in «{activeList.name}» yet.</Trans>
          </div>
          <button
            type="button"
            className="btn outline small"
            onClick={() => sheets.editList(activeList, "pick")}
          >
            <Icon name="plus" />
            <span>
              <Trans>Add chats</Trans>
            </span>
          </button>
        </div>
      ) : (
        <Empty>{empty}</Empty>
      )}
    </section>
  );
}

/* «المؤرشفة»: the archived rows (selection offers إلغاء الأرشفة), the note and the setting. */
export function ArchivedPage() {
  const data = useShellData();
  const lists = useLists();
  const toast = useToast();
  const gestures = useRowGestures();
  const rows = useMemo(() => archivedRows(lists.rows), [lists.rows]);
  const keep = data.threadSettings?.keep_archived ?? true;
  if ((data.agentsLoading || data.inboxLoading) && !data.inbox.length)
    return (
      <SkPage>
        <SkRows count={5} />
      </SkPage>
    );
  const settings = (
    <div className="group arch-settings">
      <div className="row">
        <span className="row-icon">
          <Icon name="archive" />
        </span>
        <span className="body">
          <strong>
            <Trans>Keep chats archived</Trans>
          </strong>
          <small>
            {keep ? (
              <Trans>A chat does not return to the list when a new message arrives.</Trans>
            ) : (
              <Trans>A chat returns to the list when a new message arrives.</Trans>
            )}
          </small>
        </span>
        <button
          type="button"
          className="switch"
          role="switch"
          aria-checked={keep}
          aria-label={t`Keep chats archived`}
          disabled={!data.threadSettings}
          onClick={async () => {
            try {
              const next = await listsApi.settings({ keep_archived: !keep });
              data.setThreadSettings(next);
              toast(
                next.keep_archived
                  ? t`Chats will stay archived`
                  : t`A chat will return when a new message arrives`,
              );
            } catch (error) {
              lists.failed(error);
            }
          }}
        />
      </div>
    </div>
  );
  if (!rows.length)
    return (
      <>
        <Empty>
          <Trans>
            No archived chats. Press and hold a chat in the list, then choose «Archive».
          </Trans>
        </Empty>
        {settings}
      </>
    );
  return (
    <>
      <div className="thread-list" {...gestures}>
        <Rows rows={rows} />
      </div>
      <p className="note arch-note">
        <Icon name="info" />
        <span>
          <Trans>Press and hold a chat to unarchive, mute or delete it.</Trans>
        </span>
      </p>
      {settings}
    </>
  );
}
