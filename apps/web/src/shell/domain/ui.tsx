import { Icon, type IconName } from "@lonora/ui-web";
import { type ReactNode, useEffect, useRef, useState } from "react";

/* The reference's small builders (R, V, F, T, Select, Check, Toggle, Form, empty, note,
   foldCard) as React parts, with the same markup and classes. */

export function Row({
  icon,
  lead,
  title,
  sub,
  value,
  onClick,
  chevron = true,
  className = "",
  children,
}: {
  icon?: IconName;
  lead?: ReactNode;
  title: ReactNode;
  sub?: ReactNode;
  value?: ReactNode;
  onClick?: () => void;
  chevron?: boolean;
  className?: string;
  children?: ReactNode;
}) {
  const inner = (
    <>
      {lead ?? (icon ? <Icon name={icon} /> : null)}
      <span className="body">
        <strong>{title}</strong>
        {sub ? <small>{sub}</small> : null}
      </span>
      {value ? <span className="value">{value}</span> : null}
      {children}
      {onClick && chevron ? (
        <span className="chevron">
          <Icon name="chev" />
        </span>
      ) : null}
    </>
  );
  return onClick ? (
    <button type="button" className={`row ${className}`.trim()} onClick={onClick}>
      {inner}
    </button>
  ) : (
    <div className={`row ${className}`.trim()}>{inner}</div>
  );
}

/** «V»: a label and its value on one row. */
export const ValueRow = ({ label, value }: { label: ReactNode; value: ReactNode }) => (
  <div className="row">
    <span className="body">{label}</span>
    <span className="value">{value}</span>
  </div>
);

export const Empty = ({ children }: { children: ReactNode }) => (
  <div className="empty">
    <Icon name="folder" />
    <div>{children}</div>
  </div>
);
export const Note = ({ children }: { children: ReactNode }) => <p className="note">{children}</p>;

/** «grouped»: rows in a group, or the empty state alone. */
export function Grouped({ children, empty }: { children: ReactNode[]; empty: ReactNode }) {
  return children.length ? <div className="group">{children}</div> : <Empty>{empty}</Empty>;
}

export function Toggle({
  on,
  label,
  onChange,
  disabled,
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

export function Field({
  label,
  name,
  defaultValue = "",
  type = "text",
  required,
  maxLength,
  dir,
  ...rest
}: {
  label: ReactNode;
  name: string;
  defaultValue?: string;
  type?: string;
  required?: boolean;
  maxLength?: number;
  dir?: "ltr" | "rtl" | "auto";
  min?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        name={name}
        type={type}
        defaultValue={defaultValue}
        required={required}
        maxLength={maxLength}
        dir={dir}
        {...rest}
      />
    </label>
  );
}

export function Area({
  label,
  name,
  defaultValue = "",
  maxLength,
  required,
}: {
  label: ReactNode;
  name: string;
  defaultValue?: string;
  maxLength?: number;
  required?: boolean;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {/* The label's own text would also read the textarea's content; name it by the label. */}
      <textarea
        name={name}
        aria-label={typeof label === "string" ? label : undefined}
        defaultValue={defaultValue}
        maxLength={maxLength}
        required={required}
      />
    </label>
  );
}

/** «Select»: the reference's picker (syncSelectMenus): the native select stays in the form,
    hidden, and a trigger opens a listbox of the options. */
export function SelectField({
  label,
  name,
  options,
  value,
  onChange,
}: {
  label: string;
  name: string;
  options: readonly (readonly [string, string])[];
  value?: string;
  onChange?: (value: string) => void;
}) {
  const first = options[0]?.[0] ?? "";
  const [current, setCurrent] = useState(value ?? first);
  const [menu, setMenu] = useState<{ left: number; top: number; width: number } | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (value !== undefined) setCurrent(value);
  }, [value]);
  useEffect(() => {
    if (!menu) return;
    const close = (event: Event) => {
      if (event instanceof KeyboardEvent && event.key !== "Escape") return;
      if (event.target instanceof Node && trigger.current?.parentElement?.contains(event.target))
        return;
      setMenu(null);
    };
    document.addEventListener("pointerdown", close, true);
    document.addEventListener("keydown", close, true);
    return () => {
      document.removeEventListener("pointerdown", close, true);
      document.removeEventListener("keydown", close, true);
    };
  }, [menu]);
  const choose = (next: string) => {
    setCurrent(next);
    onChange?.(next);
  };
  const shown = options.find(([key]) => key === current)?.[1] ?? options[0]?.[1] ?? "";
  const open = () => {
    const rect = trigger.current?.getBoundingClientRect();
    if (!rect) return;
    const width = Math.min(Math.max(rect.width, 210), window.innerWidth - 24);
    setMenu({
      width,
      left: Math.max(12, Math.min(rect.right - width, window.innerWidth - width - 12)),
      top: rect.bottom + 6,
    });
  };
  return (
    <label className="field">
      <span>{label}</span>
      <select
        name={name}
        className="select-native"
        aria-label={label}
        tabIndex={-1}
        value={current}
        onChange={(event) => choose(event.target.value)}
      >
        {options.map(([key, text]) => (
          <option key={key} value={key}>
            {text}
          </option>
        ))}
      </select>
      <button
        ref={trigger}
        type="button"
        className="select-trigger"
        aria-haspopup="listbox"
        aria-expanded={!!menu}
        aria-label={`${label}: ${shown}`}
        onClick={(event) => {
          event.preventDefault();
          if (menu) setMenu(null);
          else open();
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            open();
          }
        }}
      >
        <span>{shown}</span>
        <Icon name="down" />
      </button>
      {menu && (
        <div
          className="select-popup"
          role="listbox"
          aria-label={`${label}: ${shown}`}
          style={{ left: menu.left, top: menu.top, width: menu.width }}
        >
          {options.map(([key, text]) => (
            <button
              key={key}
              type="button"
              className="select-option"
              role="option"
              aria-selected={key === current}
              onClick={(event) => {
                event.preventDefault();
                choose(key);
                setMenu(null);
                trigger.current?.focus();
              }}
            >
              <span>{text}</span>
              <span className="option-mark">{key === current ? <Icon name="check" /> : null}</span>
            </button>
          ))}
        </div>
      )}
    </label>
  );
}

export function Check({
  label,
  name,
  defaultChecked = false,
}: {
  label: ReactNode;
  name: string;
  defaultChecked?: boolean;
}) {
  const [on, setOn] = useState(defaultChecked);
  return (
    <label className="check">
      <span>{label}</span>
      <input
        type="checkbox"
        role="switch"
        name={name}
        checked={on}
        aria-checked={on}
        onChange={(event) => setOn(event.target.checked)}
      />
    </label>
  );
}

/** «Form»: the fields, then the actions row with the submit button last. */
export function FormPage({
  name,
  submit,
  busy,
  disabled,
  extra,
  onSubmit,
  children,
}: {
  name: string;
  submit: ReactNode;
  busy?: boolean;
  /** Nothing can be saved as the form stands (the form itself says why). */
  disabled?: boolean;
  extra?: ReactNode;
  onSubmit: (data: FormData, form: HTMLFormElement) => void;
  children: ReactNode;
}) {
  return (
    <form
      data-form={name}
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        const form = event.currentTarget;
        if (!form.reportValidity()) return;
        onSubmit(new FormData(form), form);
      }}
    >
      {children}
      <div className="actions">
        {extra}
        <button type="submit" className="btn primary" disabled={busy || disabled} aria-busy={busy}>
          {submit}
        </button>
      </div>
    </form>
  );
}

/** «foldCard»: a card whose body folds; open by default. */
export function FoldCard({
  title,
  summary,
  children,
}: {
  title: ReactNode;
  summary: ReactNode;
  children: ReactNode;
}) {
  const [closed, setClosed] = useState(false);
  return (
    <section className={`card fold-card ${closed ? "is-collapsed" : ""}`.trim()}>
      <button
        className="fold-top"
        type="button"
        aria-expanded={!closed}
        onClick={() => setClosed((value) => !value)}
      >
        <span className="fold-title">
          <strong>{title}</strong>
          <small>{summary}</small>
        </span>
        <span className="fold-arrow">
          <Icon name="down" />
        </span>
      </button>
      <div className="fold-content">
        <div className="fold-inner">{children}</div>
      </div>
    </section>
  );
}

export const text = (data: FormData, key: string) => String(data.get(key) ?? "").trim();
