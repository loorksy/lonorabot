import { Trans } from "@lingui/react/macro";
import { Icon, type IconName } from "@lonora/ui-web";
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
import { isRequestCancelled } from "../lib/api";

/* Notices: one live region. Typed toasts carry an icon; a toast with an action moves to the
   bottom as a snackbar and stays longer. Errors announce as alerts. */
export type ToastType = "success" | "error" | "warn" | "info";
export type ToastOptions = {
  type?: ToastType;
  action?: { label: ReactNode; run: () => void };
  duration?: number;
};
type Toast = ToastOptions & { text: ReactNode; serial: number };
type Api = (text: ReactNode, options?: ToastOptions) => void;
const Context = createContext<Api | null>(null);
const icons: Record<ToastType, IconName> = {
  success: "check",
  error: "alert",
  warn: "alert",
  info: "info",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<Toast | null>(null);
  const [visible, setVisible] = useState(false);
  const serial = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const show = useCallback<Api>((text, options = {}) => {
    serial.current += 1;
    setToast({ ...options, text, serial: serial.current });
    setVisible(true);
    clearTimeout(timer.current);
    timer.current = setTimeout(
      () => setVisible(false),
      options.duration ?? (options.action ? 5200 : 3300),
    );
  }, []);
  useEffect(() => {
    let lastCrash = 0;
    const throttled = () => {
      if (Date.now() - lastCrash < 6000) return true;
      lastCrash = Date.now();
      return false;
    };
    const failed = () => {
      if (throttled()) return;
      show(<Trans>An unexpected error occurred</Trans>, {
        type: "error",
        action: { label: <Trans>Reload</Trans>, run: () => location.reload() },
      });
    };
    const rejected = (event: PromiseRejectionEvent) => {
      if (isRequestCancelled(event.reason) || throttled()) return;
      show(<Trans>The operation could not be completed</Trans>, { type: "error" });
    };
    window.addEventListener("error", failed);
    window.addEventListener("unhandledrejection", rejected);
    return () => {
      window.removeEventListener("error", failed);
      window.removeEventListener("unhandledrejection", rejected);
      clearTimeout(timer.current);
    };
  }, [show]);
  const value = useMemo(() => show, [show]);
  const type = toast?.type;
  return (
    <Context.Provider value={value}>
      {children}
      <div
        id="toast"
        key={toast?.serial ?? 0}
        role={type === "error" ? "alert" : "status"}
        aria-live="polite"
        className={[
          visible && toast ? "show" : "",
          type ? `t-${type}` : "",
          toast?.action ? "has-action" : "",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {toast && (
          <>
            {type && (
              <span className="t-ic">
                <Icon name={icons[type]} />
              </span>
            )}
            <span className="t-msg">{toast.text}</span>
            {toast.action && (
              <button
                type="button"
                className="t-act"
                onClick={() => {
                  setVisible(false);
                  toast.action?.run();
                }}
              >
                {toast.action.label}
              </button>
            )}
          </>
        )}
      </div>
    </Context.Provider>
  );
}

export function useToast() {
  const value = useContext(Context);
  if (!value) throw new Error("toast_context_missing");
  return value;
}
