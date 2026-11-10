import { Icon, type IconName } from "@lonora/ui-web";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { isRequestCancelled } from "../../lib/api";
import { useNavigation } from "../navigation";

/* The reference's settings building blocks (R, V, togRow, Toggle, note, empty: lines 2874-2889,
   6130), as components. */

export function NavRow({
  icon,
  label,
  to,
  value,
  sub,
  onClick,
}: {
  icon: IconName | ReactNode;
  label: ReactNode;
  to?: string;
  value?: ReactNode;
  sub?: ReactNode;
  onClick?: () => void;
}) {
  const nav = useNavigation();
  return (
    <button
      type="button"
      className="row"
      onClick={onClick ?? (() => (to ? nav.go(to) : undefined))}
    >
      {typeof icon === "string" ? <Icon name={icon as IconName} /> : icon}
      <span className="body">
        <strong>{label}</strong>
        {sub ? <small>{sub}</small> : null}
      </span>
      {value ? <span className="value">{value}</span> : null}
      <span className="chevron">
        <Icon name="chev" />
      </span>
    </button>
  );
}

export function ValueRow({ label, value }: { label: ReactNode; value: ReactNode }) {
  return (
    <div className="row">
      <span className="body">{label}</span>
      <span className="value">{value}</span>
    </div>
  );
}

export function Toggle({
  on,
  label,
  onChange,
  disabled = false,
}: {
  on: boolean;
  label: string;
  onChange: (next: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      className="switch"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!on)}
    />
  );
}

export function ToggleRow({
  title,
  sub,
  on,
  icon,
  onChange,
  disabled,
}: {
  title: string;
  sub?: ReactNode;
  on: boolean;
  icon?: IconName;
  onChange: (next: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <div className="row">
      {icon && (
        <span className="row-icon">
          <Icon name={icon} />
        </span>
      )}
      <span className="body">
        <strong>{title}</strong>
        {sub ? <small>{sub}</small> : null}
      </span>
      <Toggle on={on} label={title} onChange={onChange} disabled={disabled} />
    </div>
  );
}

export const Note = ({ children }: { children: ReactNode }) => <p className="note">{children}</p>;

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="empty">
      <Icon name="folder" />
      <div>{children}</div>
    </div>
  );
}

/** One server read for a page: its value, its error, and a reload. A late answer never lands
 * after the page left. */
export function useLoad<T>(load: () => Promise<T>, deps: readonly unknown[]) {
  const [state, setState] = useState<{ value?: T; error?: unknown; loading: boolean }>({
    loading: true,
  });
  const serial = useRef(0);
  const loader = useRef(load);
  loader.current = load;
  const key = JSON.stringify(deps);
  // biome-ignore lint/correctness/useExhaustiveDependencies: the caller names what the read depends on (key).
  const reload = useCallback(() => {
    serial.current += 1;
    const mine = serial.current;
    setState((current) => ({ ...current, loading: true }));
    loader.current().then(
      (value) => {
        if (mine === serial.current) setState({ value, loading: false });
      },
      (error) => {
        if (mine === serial.current && !isRequestCancelled(error))
          setState({ error, loading: false });
      },
    );
  }, [key]);
  useEffect(() => {
    reload();
    return () => {
      serial.current += 1;
    };
  }, [reload]);
  return { ...state, reload, set: (value: T) => setState({ value, loading: false }) };
}
