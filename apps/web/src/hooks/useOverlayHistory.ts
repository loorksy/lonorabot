import { useEffect, useRef } from "react";

type Position = { index: number; order: number; id?: string; url: string; key?: string };
type Layer = {
  id: string;
  token: string;
  url: string;
  dismiss: () => void;
  focus: Element | null;
  generation: number;
  installed: boolean;
};
type Entry = { order: number; baseKey?: string; closed: boolean };
const marker = "lonoraOverlay";
const storageKey = "lonora:overlay-history";
const layers: Layer[] = [];
const entries = new Map<string, Entry>();
let listening = false;
let sequence = 0;
let position: Position | null = null;
let traversal: { direction: number; skipBase: boolean; closedVisible: boolean } | null = null;
let traversalTimer: ReturnType<typeof setTimeout> | undefined;

function saveEntries() {
  try {
    // Per-tab navigation metadata only: no message content, URLs or credentials.
    sessionStorage.setItem(storageKey, JSON.stringify([...entries].slice(-512)));
  } catch {
    // Private browsing may disable storage; in-memory navigation still works.
  }
}

function restoreEntries() {
  try {
    const saved: unknown = JSON.parse(sessionStorage.getItem(storageKey) ?? "null");
    if (!Array.isArray(saved)) return;
    for (const item of saved.slice(-512)) {
      if (!Array.isArray(item) || item.length !== 2 || typeof item[0] !== "string") continue;
      const value: unknown = item[1];
      if (
        !value ||
        typeof value !== "object" ||
        !("order" in value) ||
        typeof value.order !== "number" ||
        !Number.isFinite(value.order) ||
        !("closed" in value) ||
        typeof value.closed !== "boolean"
      )
        continue;
      entries.set(item[0], {
        order: value.order,
        // A layer belongs to the previous document. A restored panel registers
        // a fresh layer; its old history entry must not consume a Back tap.
        closed: true,
        ...("baseKey" in value && typeof value.baseKey === "string"
          ? { baseKey: value.baseKey }
          : {}),
      });
      sequence = Math.max(sequence, value.order);
    }
  } catch {
    // Invalid or unavailable storage must not block navigation.
  }
}

function currentPosition(): Position {
  const state = window.history.state;
  const id = typeof state?.[marker] === "string" ? state[marker] : undefined;
  return {
    index: typeof state?.idx === "number" ? state.idx : 0,
    order: id ? (entries.get(id)?.order ?? 0) : 0,
    id,
    url: window.location.href,
    key: typeof state?.key === "string" ? state.key : undefined,
  };
}

function install(layer: Layer) {
  if (layer.installed || !layers.includes(layer)) return;
  layer.installed = true;
  const previous = window.history.state;
  entries.set(layer.id, {
    order: ++sequence,
    baseKey: previous?.key,
    closed: false,
  });
  saveEntries();
  // Preserve BrowserRouter's key, index and user state for the unchanged route.
  window.history.pushState({ ...previous, [marker]: layer.id }, "");
  position = currentPosition();
}

function finishTraversal() {
  if (traversalTimer !== undefined) clearTimeout(traversalTimer);
  traversalTimer = undefined;
  traversal = null;
  for (const layer of layers) install(layer);
  position = currentPosition();
}

function remove(layer: Layer, dismiss: boolean) {
  const index = layers.indexOf(layer);
  if (index < 0) return;
  layers.splice(index, 1);
  const entry = entries.get(layer.id);
  if (entry) entry.closed = true;
  saveEntries();
  if (dismiss) layer.dismiss();
}

function restoreFocus(layer: Layer) {
  // A newly opened layer owns focus; closing its predecessor must not steal it.
  if (layers.length) return;
  if (layer.focus instanceof HTMLElement && layer.focus.isConnected) layer.focus.focus();
}

function listen() {
  if (listening) return;
  listening = true;
  restoreEntries();
  position = currentPosition();
  // Router pushes synchronously, before React commits its location update. Track
  // that transition here so an immediate Back cannot use the previous layer's
  // position. Delegate unchanged arguments and state to the browser methods.
  const pushState = window.history.pushState.bind(window.history);
  const replaceState = window.history.replaceState.bind(window.history);
  window.history.pushState = (...args) => {
    pushState(...args);
    position = currentPosition();
  };
  window.history.replaceState = (...args) => {
    replaceState(...args);
    position = currentPosition();
  };
  window.addEventListener("popstate", () => {
    const next = currentPosition();
    const previous = position;
    if (!traversal) {
      const difference =
        next.index - (previous?.index ?? next.index) ||
        next.order - (previous?.order ?? next.order);
      traversal = {
        direction: difference > 0 ? 1 : -1,
        skipBase: Boolean(
          previous?.id && entries.get(previous.id)?.closed && previous.url === next.url,
        ),
        closedVisible: false,
      };
    }
    position = next;
    const installed = layers.filter((layer) => layer.installed);
    while (installed.length && installed.at(-1)?.id !== next.id) {
      const layer = installed.pop();
      if (!layer) break;
      traversal.closedVisible = true;
      remove(layer, true);
      restoreFocus(layer);
    }
    // UI closes leave an inactive entry. Back must close the next visible layer,
    // rather than consuming that inactive entry with no visible change.
    const top = installed.at(-1);
    if (traversal.direction < 0 && traversal.skipBase && top && top.id === next.id) {
      traversal.closedVisible = true;
      remove(top, true);
      restoreFocus(top);
    }
    const entry = next.id ? entries.get(next.id) : undefined;
    const closedEntry = Boolean(entry?.closed);
    const inactiveBase =
      traversal.direction < 0 &&
      traversal.skipBase &&
      !traversal.closedVisible &&
      !next.id &&
      previous?.id &&
      entries.get(previous.id)?.baseKey === next.key &&
      previous.url === next.url;
    if (closedEntry || inactiveBase) {
      // Only user-initiated traversal consumes old entries. UI cleanup never
      // issues an asynchronous Back that could race a new dialog or navigation.
      window.history.go(traversal.direction);
      if (traversalTimer !== undefined) clearTimeout(traversalTimer);
      // At the end of Forward history there may be no further popstate.
      traversalTimer = setTimeout(finishTraversal, 80);
      return;
    }
    finishTraversal();
  });
  window.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || event.defaultPrevented || !layers.length) return;
    event.preventDefault();
    layers.at(-1)?.dismiss();
  });
}

/** Back closes the top layer; UI close and immediate navigation never race Back. */
export function useOverlayHistory(open: boolean, onClose: () => void) {
  const close = useRef(onClose);
  close.current = onClose;
  const token = useRef<string | null>(null);
  if (token.current === null) token.current = crypto.randomUUID();
  useEffect(listen, []);
  useEffect(() => {
    if (!open) return;
    listen();
    let layer = layers.find((candidate) => candidate.token === token.current);
    if (!layer) {
      layer = {
        id: crypto.randomUUID(),
        token: token.current ?? "",
        url: window.location.href,
        dismiss: () => close.current(),
        focus: document.activeElement,
        generation: 0,
        installed: false,
      };
      layers.push(layer);
      if (!traversal) install(layer);
    }
    const current = layer;
    current.generation += 1;
    return () => {
      const generation = ++current.generation;
      // StrictMode setup/cleanup/setup reuses the same layer and cancels release.
      queueMicrotask(() => {
        if (current.generation !== generation) return;
        remove(current, false);
        restoreFocus(current);
      });
    };
  }, [open]);
}

/** Navigation closes transient layers; their history entries are skipped on Back. */
export function dismissOverlays() {
  for (const layer of [...layers].reverse()) {
    remove(layer, true);
    restoreFocus(layer);
  }
}
