import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { ChatList } from "@lonora/contracts";
import { type ChatRow, foldSearch, listMemberRows, rowKey } from "@lonora/core";
import { Icon } from "@lonora/ui-web";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { type Agent, ApiError, type Resource } from "../../lib/api";
import { useShellData } from "../data";
import { isDesktop } from "../motion";
import { useSheets } from "../sheets/SheetHost";
import { useToast } from "../Toast";
import { listsApi } from "./api";
import { EmojiPanel } from "./EmojiPanel";
import { PopItem, PopSep, usePopover } from "./Popover";
import { useLists } from "./state";
import { RowAvatar } from "./ThreadRow";
import { chatsWord, listSize } from "./words";

/* Custom lists (WhatsApp «القوائم»): «قائمة جديدة» is a full-height sheet in two pages, the
   name (😊 opens the emoji panel) then the agents and groups; a list chip's menu edits or
   deletes it (with undo); the selection adds chats to a list. Lists live on the server. */
type Draft = { id?: string; name: string; keys: Set<string>; fromSelection: boolean };

/* Sheet bodies render in the sheet layer, outside the list's providers: what they need
   comes in as props. */
function NameStep({
  draft,
  first,
  onNext,
  onLimit,
}: {
  draft: Draft;
  first: boolean;
  onNext: () => void;
  onLimit: () => void;
}) {
  const [name, setName] = useState(draft.name);
  const [emoji, setEmoji] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const timer = setTimeout(
      () => {
        const field = input.current;
        if (field && document.activeElement !== field) {
          field.focus({ preventScroll: true });
          field.setSelectionRange(field.value.length, field.value.length);
        }
      },
      first ? 340 : 40,
    );
    return () => clearTimeout(timer);
  }, [first]);
  useEffect(() => {
    const dialog = document.getElementById("dialog");
    dialog?.classList.toggle("emo-open", emoji);
    return () => dialog?.classList.remove("emo-open");
  }, [emoji]);
  const update = (value: string) => {
    draft.name = value;
    setName(value);
  };
  return (
    <form
      className="list-form"
      data-form="list-name"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        if (!name.trim()) return;
        setEmoji(false);
        onNext();
      }}
    >
      <div className="list-top">
        <label className="list-label" htmlFor="list-name">
          <Trans>List name</Trans>
        </label>
        <div className="list-name-row">
          <input
            id="list-name"
            ref={input}
            name="name"
            maxLength={30}
            autoComplete="off"
            enterKeyHint="next"
            placeholder={t`For example: Work, Friends`}
            value={name}
            onChange={(event) => update(event.target.value)}
            onPointerDown={() => {
              // A tap on the field brings the keyboard back.
              if (emoji) setEmoji(false);
            }}
          />
          <button
            type="button"
            className="icon list-emoji-b"
            aria-label={emoji ? t`Keyboard` : t`Add an emoji`}
            aria-expanded={emoji}
            onPointerDown={(event) => event.preventDefault()}
            onClick={() => {
              setEmoji((open) => !open);
              if (emoji) {
                const field = input.current;
                field?.blur();
                field?.focus({ preventScroll: true });
              }
            }}
          >
            <Icon name={emoji ? "keyboard" : "smile"} />
          </button>
        </div>
        <p className="list-hint">
          <Trans>Every list you create becomes a filter above the chat list.</Trans>
        </p>
      </div>
      <div className="list-foot">
        <button type="submit" className="btn primary full list-next" disabled={!name.trim()}>
          {draft.id ? <Trans>Next: the chats</Trans> : <Trans>Add agents or groups</Trans>}
        </button>
      </div>
      {emoji && (
        <EmojiPanel target={input} value={name} maxLength={30} onValue={update} onLimit={onLimit} />
      )}
    </form>
  );
}

function PickStep({
  draft,
  rows,
  agents,
  groups,
  onSave,
}: {
  draft: Draft;
  rows: readonly ChatRow[];
  agents: Agent[];
  groups: Resource[];
  onSave: () => Promise<void>;
}) {
  const [keys, setKeys] = useState(() => new Set(draft.keys));
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const choices = useMemo(
    () =>
      [
        ...agents.map((agent) => rowKey("agent", agent.id)),
        ...groups.map((group) => rowKey("group", group.id)),
      ]
        .map((key) => rows.find((row) => row.key === key))
        .filter((row): row is ChatRow => Boolean(row)),
    [agents, groups, rows],
  );
  const q = foldSearch(query);
  const shown = choices.filter(
    (row) =>
      !q ||
      foldSearch(`${row.name} ${row.subtitle || (row.kind === "group" ? t`Group` : "")}`).includes(
        q,
      ),
  );
  const count = keys.size;
  return (
    <div className="list-pick">
      <label className="lp-search">
        <Icon name="search" />
        <input
          id="list-q"
          type="search"
          placeholder={t`Search`}
          autoComplete="off"
          aria-label={t`Search agents and groups`}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </label>
      {/* biome-ignore lint/a11y/useSemanticElements: the reference's group of check rows */}
      <div className="group list-rows" role="group" aria-label={t`Agents and groups`}>
        {shown.map((row) => (
          // biome-ignore lint/a11y/useSemanticElements: a whole row toggles, as in the reference
          <button
            type="button"
            key={row.key}
            className="row list-row"
            role="checkbox"
            aria-checked={keys.has(row.key)}
            onClick={() => {
              const next = new Set(keys);
              if (next.has(row.key)) next.delete(row.key);
              else next.add(row.key);
              draft.keys = next;
              setKeys(next);
              navigator.vibrate?.(6);
            }}
          >
            <RowAvatar row={row} agents={agents} />
            <span className="body">
              <strong dir="auto">{row.name}</strong>
              <small dir="auto">{row.subtitle || (row.kind === "group" ? t`Group` : "")}</small>
            </span>
            <span className="list-box" aria-hidden="true">
              <Icon name="check" />
            </span>
          </button>
        ))}
        {!shown.length && (
          <p className="list-none">
            <Trans>No results.</Trans>
          </p>
        )}
      </div>
      <div className="list-foot">
        <button
          type="button"
          className="btn primary full list-save"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await onSave();
            } finally {
              setBusy(false);
            }
          }}
        >
          {draft.id
            ? count
              ? t`Save the list · ${count}`
              : t`Save the list`
            : count
              ? t`Create the list · ${count}`
              : t`Create the list`}
        </button>
      </div>
    </div>
  );
}

export function useListSheets() {
  const sheets = useSheets();
  const popover = usePopover();
  const data = useShellData();
  const lists = useLists();
  const toast = useToast();
  const { setChatLists, chatLists } = data;

  async function save(draft: Draft) {
    const name = draft.name.trim().slice(0, 30);
    if (!name) return;
    const taken = () => toast(t`A list named «${name}» already exists`, { type: "warn" });
    if (chatLists.some((list) => list.id !== draft.id && list.name === name)) return taken();
    try {
      const picked = lists.rows.filter((row) => draft.keys.has(row.key));
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
      if (picked.some((row) => !row.threadId)) data.refresh();
      lists.setFilter(`list:${list.id}`);
      sheets.close();
      if (draft.fromSelection) lists.end();
      const scroller = isDesktop()
        ? document.getElementById("desktop-threads")
        : document.getElementById("view-scroll");
      scroller?.scrollTo({ top: 0 });
      setTimeout(
        () =>
          document
            .querySelector(`.list-filters .chip[data-list="${CSS.escape(list.id)}"]`)
            ?.scrollIntoView({ inline: "nearest", block: "nearest", behavior: "smooth" }),
        80,
      );
      toast(draft.id ? t`«${name}» saved` : t`List «${name}» created`, { type: "success" });
    } catch (error) {
      if (error instanceof ApiError && error.code === "chat_list_name_taken") taken();
      else lists.failed(error);
    }
  }

  function pickPage(draft: Draft, dir?: "fwd" | "back") {
    const title = t`Add to «${draft.name.trim()}»`;
    sheets.open(
      {
        id: "list",
        title,
        label: title,
        bar: true,
        full: true,
        dir,
        back: () => namePage(draft, "back"),
        body: (
          <PickStep
            draft={draft}
            rows={lists.rows}
            agents={data.agents}
            groups={data.groups}
            onSave={() => save(draft)}
          />
        ),
      },
      { morph: Boolean(dir) },
    );
  }
  function namePage(draft: Draft, dir?: "fwd" | "back") {
    const title = draft.id ? t`Edit the list` : t`New list`;
    sheets.open(
      {
        id: "list",
        title,
        label: title,
        bar: true,
        full: true,
        dir,
        body: (
          <NameStep
            draft={draft}
            first={!dir}
            onNext={() => pickPage(draft, "fwd")}
            onLimit={() => toast(t`You reached the name's maximum length`, { type: "warn" })}
          />
        ),
      },
      { morph: Boolean(dir) },
    );
  }

  function newList(rows: readonly ChatRow[] = [], fromSelection = false, dir?: "fwd") {
    namePage({ name: "", keys: new Set(rows.map((row) => row.key)), fromSelection }, dir);
  }
  function editList(list: ChatList, step: "name" | "pick" = "name") {
    const draft: Draft = {
      id: list.id,
      name: list.name,
      keys: new Set(listMemberRows(lists.rows, list).map((row) => row.key)),
      fromSelection: false,
    };
    if (step === "pick") pickPage(draft);
    else namePage(draft);
  }

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
    toast(t`«${list.name}» deleted`, {
      action: {
        label: t`Undo`,
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

  function listMenu(list: ChatList, anchor: HTMLElement) {
    navigator.vibrate?.(10);
    const size = listSize(listMemberRows(lists.rows, list).length);
    popover.open(
      anchor,
      <>
        <div className="pop-title">
          {list.name} · {size}
        </div>
        <PopItem icon="edit" label={<Trans>Edit the list</Trans>} onSelect={() => editList(list)} />
        <PopItem
          icon="users"
          label={<Trans>The chats</Trans>}
          onSelect={() => editList(list, "pick")}
        />
        <PopSep />
        <PopItem
          icon="trash"
          danger
          label={<Trans>Delete the list</Trans>}
          onSelect={() => void removeList(list)}
        />
      </>,
      list.name,
    );
  }

  function addToList(rows: readonly ChatRow[]) {
    const title = t`Add to a list`;
    const add = async (list: ChatList) => {
      try {
        const ids = await lists.threadsOf(rows);
        const added = ids.filter((id) => !list.thread_ids.includes(id));
        const saved = await listsApi.members(list.id, [...list.thread_ids, ...added]);
        setChatLists((all) => all.map((row) => (row.id === saved.id ? saved : row)));
        if (rows.some((row) => !row.threadId)) data.refresh();
        sheets.close();
        lists.end();
        toast(
          added.length
            ? t`${chatsWord(added.length)} added to «${list.name}»`
            : t`All already in «${list.name}»`,
          { type: "success" },
        );
      } catch (error) {
        lists.failed(error);
      }
    };
    const body: ReactNode = (
      <div className="group">
        {chatLists.map((list) => (
          <button type="button" className="row" key={list.id} onClick={() => void add(list)}>
            <span className="row-icon">
              <Icon name="layers" />
            </span>
            <span className="body">
              <strong dir="auto">{list.name}</strong>
              <small>{listSize(listMemberRows(lists.rows, list).length)}</small>
            </span>
          </button>
        ))}
        <button type="button" className="row" onClick={() => newList(rows, true, "fwd")}>
          <span className="row-icon">
            <Icon name="plus" />
          </span>
          <span className="body">
            <strong>
              <Trans>New list</Trans>
            </strong>
            <small>{t`${chatsWord(rows.length)} will be added to it`}</small>
          </span>
        </button>
      </div>
    );
    sheets.open({ id: "list", title, label: title, bar: true, body });
  }

  return { newList, editList, listMenu, addToList };
}
