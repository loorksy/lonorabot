import { t } from "@lingui/core/macro";
import { Icon } from "@lonora/ui-web";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { LogoMark } from "../LogoMark";
import { useToast } from "../Toast";
import { checkPin, readLock, setPin, verifyBiometric, writeLock } from "./lock-state";

/* The #lock layer (reference lockOpen/lockRender/lockKey, 6070-6103): 4 dots, an LTR keypad, the
   biometric key when enrolled, 5 wrong codes → a 30 s cool-down. It covers the app when Lonora
   opens with the lock on and when it comes back after being hidden for the chosen delay. «set»
   asks for a new code twice. */
type Mode = "unlock" | "set" | "confirm";
type State = {
  mode: Mode;
  entry: string;
  first: string;
  tries: number;
  until: number;
  msg: string;
  bad: boolean;
  onDone?: (ok: boolean) => void;
};
type Api = { setCode: (onDone?: (ok: boolean) => void) => void; lockNow: () => void };
const Context = createContext<Api | null>(null);
function fresh(mode: Mode, onDone?: (ok: boolean) => void): State {
  return {
    mode,
    entry: "",
    first: "",
    tries: 0,
    until: 0,
    bad: false,
    onDone,
    msg:
      mode === "unlock"
        ? t`Enter the lock code`
        : mode === "set"
          ? t`Choose a 4-digit code`
          : t`Enter the code again`,
  };
}
/** The unlock state with the wrong tries and cool-down this device has recorded, so a reload
 * never resets the 5-try / 30 s limit. */
function unlockState(): State {
  const lock = readLock();
  return { ...fresh("unlock"), tries: lock.tries ?? 0, until: lock.until ?? 0 };
}
const vibrate = (pattern: number | number[]) => navigator.vibrate?.(pattern);

export function AppLockProvider({ children }: { children: ReactNode }) {
  const toast = useToast();
  const [state, setState] = useState<State | null>(() => (readLock().on ? unlockState() : null));
  const [, tick] = useState(0);
  const hiddenAt = useRef(0);
  const live = useRef(state);
  live.current = state;

  const lockNow = useCallback(() => {
    if (readLock().on && !live.current) setState(unlockState());
  }, []);
  useEffect(() => {
    const changed = () => {
      const lock = readLock();
      if (!lock.on) return;
      if (document.hidden) hiddenAt.current = Date.now();
      else if (hiddenAt.current && Date.now() - hiddenAt.current >= lock.after * 1000) lockNow();
    };
    document.addEventListener("visibilitychange", changed);
    return () => document.removeEventListener("visibilitychange", changed);
  }, [lockNow]);

  const wait = state && state.until > Date.now() ? Math.ceil((state.until - Date.now()) / 1000) : 0;
  useEffect(() => {
    if (!wait) return;
    const timer = setTimeout(() => tick((n) => n + 1), 1000);
    return () => clearTimeout(timer);
  }, [wait]);

  const finish = useCallback(
    async (current: State) => {
      if (current.mode === "set") {
        setState({
          ...current,
          mode: "confirm",
          first: current.entry,
          entry: "",
          msg: t`Enter the code again`,
          bad: false,
        });
        return;
      }
      if (current.mode === "confirm") {
        if (current.entry === current.first) {
          await setPin(current.entry);
          setState(null);
          current.onDone?.(true);
          toast(t`App lock turned on`, { type: "success" });
          return;
        }
        vibrate([10, 40, 10]);
        setState({
          ...fresh("set", current.onDone),
          msg: t`The codes do not match. Choose a new code`,
          bad: true,
        });
        return;
      }
      if (await checkPin(current.entry)) {
        writeLock({ tries: 0, until: 0 });
        setState(null);
        return;
      }
      vibrate([10, 40, 10]);
      const tries = current.tries + 1;
      const locked = tries >= 5;
      writeLock({ tries: locked ? 0 : tries, until: locked ? Date.now() + 30_000 : 0 });
      setState({
        ...current,
        entry: "",
        tries: locked ? 0 : tries,
        until: locked ? Date.now() + 30_000 : 0,
        bad: true,
        msg: locked ? t`Wrong code` : t`Wrong code. ${5 - tries} tries left`,
      });
    },
    [toast],
  );

  const key = useCallback(
    (digit: string) => {
      const current = live.current;
      if (!current || current.until > Date.now()) return;
      if (digit === "del")
        return setState({ ...current, entry: current.entry.slice(0, -1), bad: false });
      if (digit === "bio") {
        const id = readLock().credential;
        if (!id) return;
        setState({ ...current, msg: t`Verifying…`, bad: false });
        verifyBiometric(id).then(
          (ok) => {
            if (ok) {
              writeLock({ tries: 0, until: 0 });
              setState(null);
              toast(t`Unlocked`, { type: "success" });
            } else setState({ ...current, msg: t`Enter the lock code`, bad: true });
          },
          () => setState({ ...current, msg: t`Enter the lock code`, bad: false }),
        );
        return;
      }
      if (current.entry.length >= 4) return;
      const next = { ...current, entry: current.entry + digit, bad: false };
      vibrate(4);
      setState(next);
      if (next.entry.length === 4) setTimeout(() => void finish(next), 120);
    },
    [finish, toast],
  );
  const layer = useRef<HTMLDivElement>(null);
  const locked = state !== null;
  // While the lock is up nothing behind it takes input: every other layer of the page is inert
  // and hidden from assistive tech, focus moves into the lock and stays there, and no other key
  // handler (the composer, the shell's shortcuts) sees a key.
  useEffect(() => {
    if (!locked) return;
    const others = [...document.body.children].filter(
      (node): node is HTMLElement =>
        node instanceof HTMLElement && node !== layer.current && !node.hasAttribute("inert"),
    );
    for (const node of others) {
      node.setAttribute("inert", "");
      node.setAttribute("aria-hidden", "true");
    }
    layer.current?.querySelector<HTMLElement>(".lk-key")?.focus({ preventScroll: true });
    return () => {
      for (const node of others) {
        node.removeAttribute("inert");
        node.removeAttribute("aria-hidden");
      }
    };
  }, [locked]);
  useEffect(() => {
    if (!locked) return;
    const down = (event: KeyboardEvent) => {
      if (event.key === "Tab") {
        const keys = [
          ...(layer.current?.querySelectorAll<HTMLElement>("button:not([disabled])") ?? []),
        ];
        if (!keys.length) return event.preventDefault();
        const at = keys.indexOf(document.activeElement as HTMLElement);
        const next = event.shiftKey ? (at <= 0 ? keys.length - 1 : at - 1) : (at + 1) % keys.length;
        event.preventDefault();
        event.stopImmediatePropagation();
        keys[next].focus();
        return;
      }
      event.stopImmediatePropagation();
      if (/^[0-9]$/.test(event.key)) {
        event.preventDefault();
        key(event.key);
      } else if (event.key === "Backspace") {
        event.preventDefault();
        key("del");
      } else if (event.key !== "Enter" && event.key !== " ") event.preventDefault();
    };
    window.addEventListener("keydown", down, true);
    return () => window.removeEventListener("keydown", down, true);
  }, [locked, key]);

  const api = useMemo<Api>(
    () => ({ setCode: (onDone) => setState(fresh("set", onDone)), lockNow }),
    [lockNow],
  );
  const setup = state && state.mode !== "unlock";
  const bio = state?.mode === "unlock" && Boolean(readLock().credential);
  const button = (digit: string, label = digit) => (
    <button
      key={digit}
      type="button"
      className="lk-key"
      aria-label={label}
      disabled={Boolean(wait)}
      onClick={() => key(digit)}
    >
      {digit === "del" ? (
        <Icon name="backspace" />
      ) : digit === "bio" ? (
        <Icon name="fingerprint" />
      ) : (
        <b>{digit}</b>
      )}
    </button>
  );
  return (
    <Context.Provider value={api}>
      {children}
      {state &&
        createPortal(
          <div className="app-shell" ref={layer}>
            <div id="lock" role="dialog" aria-modal="true" aria-label={t`App lock`}>
              <div className="lk">
                {setup && (
                  <button
                    type="button"
                    className="icon lk-close"
                    aria-label={t`Cancel`}
                    onClick={() => {
                      state.onDone?.(false);
                      setState(null);
                    }}
                  >
                    <Icon name="close" />
                  </button>
                )}
                <span className="lk-logo">
                  <LogoMark size={44} />
                </span>
                <p className={`lk-msg${state.bad ? " bad" : ""}`} aria-live="assertive">
                  {wait ? t`Too many tries. Try again in ${wait} s` : state.msg}
                </p>
                <div className={`lk-dots${state.bad ? " shake" : ""}`} aria-hidden="true">
                  {[0, 1, 2, 3].map((index) => (
                    <i key={index} className={index < state.entry.length ? "on" : ""} />
                  ))}
                </div>
                <div className="lk-pad">
                  {["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((digit) => button(digit))}
                  {bio ? button("bio", t`Unlock with fingerprint`) : <span />}
                  {button("0")}
                  {button("del", t`Delete`)}
                </div>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </Context.Provider>
  );
}

export function useAppLock() {
  const value = useContext(Context);
  if (!value) throw new Error("app_lock_missing");
  return value;
}
