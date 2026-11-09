import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import {
  type ChatRow,
  groupDraftName,
  isArchived,
  isPinned,
  PIN_LIMIT,
  pinsAfter,
  selectionSummary,
} from "@lonora/core";
import { Icon, type IconName } from "@lonora/ui-web";
import type { MouseEvent } from "react";
import { useShellData } from "../data";
import { isDesktop } from "../motion";
import { useNavigation } from "../navigation";
import { useSheets } from "../sheets/SheetHost";
import { useToast } from "../Toast";
import { useListSheets } from "./ListSheets";
import { PopItem, PopSep, usePopover } from "./Popover";
import { useLists } from "./state";
import { chatsWord } from "./words";

/** The rows a «select all» adds: the ones on screen in the list being selected. */
const visibleKeys = () =>
  [
    ...document.querySelectorAll<HTMLElement>(
      isDesktop() ? ".desktop-list .thread[data-key]" : "#view-scroll .thread[data-key]",
    ),
  ].map((row) => row.dataset.key ?? "");

type Act = "pin" | "mute" | "archive" | "delete" | "clear" | "read" | "fav" | "list" | "group";

/* The selection's actions (reference selAction), each on the server and each ending the
   selection. «حذف» and «مسح الرسائل» hide the history for the owner (owner decision Q1):
   agents and groups are never deleted; the conversation stays in the list. */
export function useSelectionActions() {
  const lists = useLists();
  const data = useShellData();
  const toast = useToast();
  const sheets = useSheets();
  const nav = useNavigation();
  const listSheets = useListSheets();
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
    const what =
      act === "clear"
        ? t`The messages of ${chatsWord(rows.length)} are hidden for you; the chats stay in the list.`
        : !agents
          ? groups === 1
            ? t`The selected group's chat history is hidden for you. The group stays with its members.`
            : t`The selected groups' chat history is hidden for you. The groups stay with their members.`
          : groups
            ? t`The chat history of ${chatsWord(rows.length)} is hidden for you. The agents and groups stay.`
            : t`The chat history of ${chatsWord(rows.length)} is hidden for you. The agents stay in the agents list.`;
    const title = act === "clear" ? t`Clear the messages?` : t`Delete the chats?`;
    sheets.open({
      id: "sel-confirm",
      title,
      label: title,
      body: (
        <>
          <p>{what}</p>
          <div className="actions">
            <button type="button" className="btn outline" onClick={() => sheets.close()}>
              <Trans>Cancel</Trans>
            </button>
            <button
              type="button"
              className="btn danger"
              onClick={() => {
                sheets.close(true);
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
                  act === "delete" ? t`${chatsWord(rows.length)} deleted` : t`Messages cleared`,
                );
              }}
            >
              {act === "clear" ? <Trans>Clear</Trans> : <Trans>Delete</Trans>}
            </button>
          </div>
        </>
      ),
    });
  };
  const act = (what: Act | "all") => {
    if (!n) return;
    const summary = selectionSummary(picked, visibleKeys());
    switch (what) {
      case "all":
        lists.selectAll(visibleKeys());
        return;
      case "pin":
        if (summary.allPinned)
          return run(
            () => lists.prefs(picked, { pinned: false }),
            n > 1 ? t`Chats unpinned` : t`Chat unpinned`,
          );
        if (pinsAfter(lists.rows, picked) > PIN_LIMIT) return toast(t`You can pin 3 chats only`);
        // New pins go on top in the order they were picked.
        return run(
          () => lists.prefs(picked.filter((row) => !isPinned(row)).reverse(), { pinned: true }),
          n > 1 ? t`Chats pinned to the top` : t`Chat pinned to the top`,
        );
      case "mute":
        return run(
          () => lists.prefs(picked, { muted: !summary.allMuted }),
          summary.allMuted ? t`Notifications restored` : t`Notifications muted`,
        );
      case "archive": {
        if (picked.every(isArchived))
          return run(
            () => lists.prefs(picked, { archived: false }),
            n > 1 ? t`Chats returned to the list` : t`Chat returned to the list`,
          );
        const rows = [...picked];
        return run(async () => {
          await lists.prefs(rows, { archived: true });
          toast(t`${chatsWord(rows.length)} archived`, {
            type: "success",
            action: {
              label: t`Undo`,
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
          summary.allFavourite ? t`Removed from favourites` : t`Added to favourites`,
        );
      case "list":
        if (data.chatLists.length) listSheets.addToList(picked);
        else listSheets.newList(picked, true);
        return;
      case "group": {
        const members = summary.agentRows;
        const name = groupDraftName(members.map((row) => row.name));
        lists.end();
        nav.go("/app/new-group", {
          state: { members: members.map((row) => row.id), name },
        });
        return;
      }
      case "clear":
      case "delete":
        return confirm(what, [...picked]);
    }
  };
  return { act, picked, summary: selectionSummary(picked, []) };
}

function ToolButton({
  icon,
  label,
  onClick,
}: {
  icon: IconName;
  label: string;
  onClick: (event: MouseEvent<HTMLButtonElement>) => void;
}) {
  return (
    <button type="button" className="icon" aria-label={label} title={label} onClick={onClick}>
      <Icon name={icon} />
    </button>
  );
}

/* The header while selecting: ✕ · count | pin · mute · archive · delete · ⋮ (a toolbar). */
export function SelBar() {
  const lists = useLists();
  const popover = usePopover();
  const { act, picked, summary } = useSelectionActions();
  const n = picked.length;
  const archived = n > 0 && picked.every(isArchived);
  const menu = (anchor: HTMLElement) => {
    const full = selectionSummary(picked, visibleKeys());
    popover.open(
      anchor,
      <>
        {!full.allVisiblePicked && (
          <PopItem icon="checks" label={<Trans>Select all</Trans>} onSelect={() => act("all")} />
        )}
        <PopItem
          icon={full.anyUnread ? "checks" : "chat"}
          label={
            full.anyUnread
              ? t({ message: "Mark as read", context: "chats" })
              : t({ message: "Mark as unread", context: "chats" })
          }
          onSelect={() => act("read")}
        />
        <PopItem
          icon="heart"
          label={
            full.allFavourite ? (
              <Trans>Remove from favourites</Trans>
            ) : (
              <Trans>Add to favourites</Trans>
            )
          }
          onSelect={() => act("fav")}
        />
        <PopItem icon="layers" label={<Trans>Add to a list</Trans>} onSelect={() => act("list")} />
        {full.agentRows.length >= 2 && (
          <PopItem
            icon="users"
            label={<Trans>Group from the selected</Trans>}
            onSelect={() => act("group")}
          />
        )}
        <PopSep />
        <PopItem
          icon="trash"
          danger
          label={<Trans>Clear the messages</Trans>}
          onSelect={() => act("clear")}
        />
      </>,
      t`More`,
    );
  };
  return (
    <header className="sel-bar" role="toolbar" aria-label={t`Selected chats`}>
      <ToolButton icon="close" label={t`Cancel the selection`} onClick={lists.end} />
      <strong className="sel-count" aria-live="polite">
        {n}
        <span className="sr-only"> {t`selected`}</span>
      </strong>
      <span className="grow" />
      {!archived && (
        <ToolButton
          icon={summary.allPinned ? "pinOff" : "pin"}
          label={summary.allPinned ? t`Unpin` : t`Pin`}
          onClick={() => act("pin")}
        />
      )}
      <ToolButton
        icon={summary.allMuted ? "bell" : "bellOff"}
        label={summary.allMuted ? t`Unmute` : t`Mute notifications`}
        onClick={() => act("mute")}
      />
      <ToolButton
        icon={archived ? "unarchive" : "archive"}
        label={archived ? t`Unarchive` : t`Archive`}
        onClick={() => act("archive")}
      />
      <ToolButton icon="trash" label={t`Delete`} onClick={() => act("delete")} />
      <ToolButton icon="more" label={t`More`} onClick={(event) => menu(event.currentTarget)} />
    </header>
  );
}
