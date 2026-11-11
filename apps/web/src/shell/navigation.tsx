import { Trans } from "@lingui/react/macro";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { usePopover } from "./lists/Popover";
import { parseRoute, type ShellRoute } from "./routes";
import { useSheets } from "./sheets/SheetHost";

/* Navigation model of the reference: every go() is a history entry; scroll is remembered per
   entry; Back closes the popover menu first, then the sheet, then asks about unsaved edits, then pops. Dirty forms are
   any main-page form marked data-form (never the composer); they clear on submit or discard. */
let dirty = false;
let allowLeave = false;
let pendingNav: (() => void) | null = null;
let askToLeave: ((title: "unsaved" | "leave", run: () => void) => void) | null = null;
let current = { href: window.location.href, state: window.history.state as unknown };
const scrollMemory = new Map<string, number>();

export function markDirty() {
  dirty = true;
}
export function clearDirty() {
  dirty = false;
}
export const isDirty = () => dirty;
/* The shell's guarded navigation for UI that renders outside NavigationProvider (the sheet
   layer sits above it): same unsaved-edits guard, closes the open sheet first. */
let shellGo: ((path: string) => void) | null = null;
export const goFromSheet = (path: string) => shellGo?.(path);

document.addEventListener("input", (event) => {
  const target = event.target;
  if (!(target instanceof Element)) return;
  const form = target.closest<HTMLFormElement>("main form[data-form]");
  if (form && form.dataset.form !== "message") dirty = true;
});
document.addEventListener("submit", (event) => {
  const form = event.target;
  if (form instanceof HTMLFormElement && form.matches("main form[data-form]")) dirty = false;
});
window.addEventListener("beforeunload", (event) => {
  if (dirty) event.preventDefault();
});
// Registered at module load, before the router's own listener: a Back while a form is dirty
// re-pushes the entry we are on and asks first; the router never sees that pop. An open popover
// or sheet closes first through its own history layer.
window.addEventListener("popstate", (event) => {
  if (
    !dirty ||
    allowLeave ||
    document.getElementById("dialog")?.matches("[open]") ||
    document.querySelector(".pop[role=menu]")
  )
    return;
  window.history.pushState(current.state, "", current.href);
  event.stopImmediatePropagation();
  askToLeave?.("leave", () => {
    allowLeave = true;
    dirty = false;
    window.history.back();
    setTimeout(() => {
      allowLeave = false;
    }, 0);
  });
});

type Navigation = {
  route: ShellRoute;
  key: string;
  go: (path: string, options?: { replace?: boolean; state?: unknown }) => void;
  back: () => void;
};
const Context = createContext<Navigation | null>(null);

export function NavigationProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const sheets = useSheets();
  const popover = usePopover();
  const route = useMemo(() => parseRoute(location.pathname), [location.pathname]);
  useEffect(() => {
    void location;
    current = { href: window.location.href, state: window.history.state };
  }, [location]);
  useEffect(() => {
    askToLeave = (title, run) => {
      pendingNav = run;
      sheets.open({
        id: "leave",
        title:
          title === "unsaved" ? <Trans>Unsaved changes</Trans> : <Trans>Leave the edits?</Trans>,
        body: (
          <>
            <p>
              {title === "unsaved" ? (
                <Trans>You can keep editing or discard the changes.</Trans>
              ) : (
                <Trans>You will lose the unsaved edits.</Trans>
              )}
            </p>
            <div className="actions">
              <button
                type="button"
                className="btn outline"
                onClick={() => {
                  pendingNav = null;
                  sheets.close();
                }}
              >
                <Trans>Keep editing</Trans>
              </button>
              <button
                type="button"
                className="btn danger"
                onClick={() => {
                  const run = pendingNav;
                  pendingNav = null;
                  dirty = false;
                  sheets.close(true);
                  run?.();
                }}
              >
                <Trans>Discard</Trans>
              </button>
            </div>
          </>
        ),
      });
    };
    return () => {
      askToLeave = null;
    };
  }, [sheets]);
  const go = useCallback<Navigation["go"]>(
    (path, options) => {
      if (dirty && !allowLeave) {
        askToLeave?.("unsaved", () => navigate(path, options));
        return;
      }
      sheets.close(true);
      navigate(path, options);
    },
    [navigate, sheets],
  );
  useEffect(() => {
    shellGo = (path) => go(path);
    return () => {
      shellGo = null;
    };
  }, [go]);
  const back = useCallback(() => {
    if (popover.back()) return;
    if (sheets.isOpen()) {
      sheets.close();
      return;
    }
    if (dirty && !allowLeave) {
      askToLeave?.("leave", () => {
        allowLeave = true;
        back();
        allowLeave = false;
      });
      return;
    }
    const state = window.history.state as { idx?: number } | null;
    if (typeof state?.idx === "number" && state.idx > 0) navigate(-1);
    else navigate("/app");
  }, [navigate, sheets, popover]);
  const value = useMemo<Navigation>(
    () => ({ route, key: location.key, go, back }),
    [route, location.key, go, back],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useNavigation() {
  const value = useContext(Context);
  if (!value) throw new Error("navigation_context_missing");
  return value;
}

/** The scroller remembers its position per history entry (chat views keep their own scroller). */
export function useScrollMemory(ref: React.RefObject<HTMLElement | null>, key: string) {
  const restored = useRef("");
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element || restored.current === key) return;
    restored.current = key;
    // A fresh entry keeps where its page placed itself (the chat list rests past its filters).
    const saved = scrollMemory.get(key);
    if (saved !== undefined) element.scrollTop = saved;
  }, [ref, key]);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    let frame = 0;
    const save = () => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        scrollMemory.set(key, element.scrollTop);
      });
    };
    element.addEventListener("scroll", save, { passive: true });
    return () => {
      element.removeEventListener("scroll", save);
      if (frame) cancelAnimationFrame(frame);
      scrollMemory.set(key, element.scrollTop);
    };
  }, [ref, key]);
}
export const rememberedScroll = (key: string) => scrollMemory.get(key);
