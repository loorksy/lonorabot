/** A lonora-ui v2 card in the reference's look (Desktop-37 aa_genui, `.ux*`; GENUI_PLAN §4,
 * §5.1). The server compiled and checked it; this renders it, keeps its values, and sends
 * through `MessageCreate.ui_submit` only: the server writes the owner's bubble and data.
 * While the card builds, and until its message is committed, every control is disabled. */
import { t } from "@lingui/core/macro";
import { useLingui } from "@lingui/react/macro";
import type { UiBlock, UiDocument, UiOption, UiPart } from "@lonora/contracts";
import {
  cardLock,
  environment,
  evaluate,
  parseCardNumber,
  renderTemplate,
  sendBlocked,
} from "@lonora/core";
import { ICON_PATHS, Icon, type IconName } from "@lonora/ui-web";
import { Fragment, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import "./genui.css";
import { type UiPartHost, useGenuiHost } from "./index";

const ROUTES: Record<string, string> = {
  market: "/app/market",
  tasks: "/app/tasks",
  agents: "/app/agents",
  files: "/app/artifacts",
  usage: "/app/settings?tab=usage",
};
const STALE_MS = 120_000;

type Values = Record<string, unknown>;
type Ctx = {
  doc: UiDocument;
  env: ReturnType<typeof environment>;
  values: Values;
  locked: boolean;
  frozen: boolean;
  invalid: string | null;
  pick: (key: string, value: unknown, also?: Values) => void;
  type: (key: string, value: unknown) => void;
  unreadable: (key: string, bad: boolean) => void;
  act: (block: UiBlock, path: string) => void;
  checkRequired: () => boolean;
  sendOff: boolean;
  newest: number;
  stale: (text: string) => string;
};

function iconName(name: unknown): IconName | null {
  return typeof name === "string" && Object.hasOwn(ICON_PATHS, name) ? (name as IconName) : null;
}

function UiIcon({ name }: { name: unknown }) {
  const icon = iconName(name);
  return icon ? <Icon name={icon} /> : null;
}

/** The reference's inline Markdown in card text: **bold** only, never HTML. */
function inline(text: string): ReactNode {
  return text.split(/(\*\*[^*]+\*\*)/g).map((piece, index) =>
    piece.startsWith("**") && piece.endsWith("**") && piece.length > 4 ? (
      // biome-ignore lint/suspicious/noArrayIndexKey: static split of one string
      <b key={index}>{piece.slice(2, -2)}</b>
    ) : (
      // biome-ignore lint/suspicious/noArrayIndexKey: static split of one string
      <Fragment key={index}>{piece}</Fragment>
    ),
  );
}

function optionList(options: unknown, ctx: Ctx) {
  if (!Array.isArray(options)) return [];
  return (options as UiOption[]).map((option) =>
    option !== null && typeof option === "object"
      ? {
          value: option.value,
          label: renderTemplate(String(option.label ?? option.value ?? ""), ctx.env),
          also: option.also,
        }
      : { value: option, label: String(option ?? ""), also: undefined },
  );
}

function visible(block: UiBlock, ctx: Ctx): boolean {
  return block.when === undefined || Boolean(evaluate(block.when, ctx.env, false));
}

function Block({ block, path, ctx }: { block: UiBlock; path: string; ctx: Ctx }) {
  const isNew = path === String(ctx.newest);
  const common = { "data-ux": path, ...(isNew ? { "data-ux-new": "" } : {}) };
  if (!visible(block, ctx)) return <div {...common} data-ux-off="" hidden />;
  const text = (value: unknown) => ctx.stale(renderTemplate(String(value ?? ""), ctx.env));
  const tone = typeof block.tone === "string" ? ` t-${block.tone}` : "";
  const id = `ux-${path.replace(/\./g, "-")}`;
  switch (block.type) {
    case "Row":
    case "More":
      if (block.type === "More") return <More path={path} block={block} ctx={ctx} />;
      return (
        <div className="ux-row" {...common}>
          {(block.children as UiBlock[]).map((child, index) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: node paths are positional (data-ux)
            <Block key={`${path}.${index}`} block={child} path={`${path}.${index}`} ctx={ctx} />
          ))}
        </div>
      );
    case "Divider":
      return <hr className="ux-hr" {...common} />;
    case "Text":
      return (
        <div
          className={`ux-text${tone}${block.size === "sm" ? " sm" : ""}`}
          {...common}
          role="status"
        >
          {inline(text(block.text))}
        </div>
      );
    case "Note": {
      const icon =
        block.icon ?? (block.tone === "warn" ? "alert" : block.tone === "good" ? "check" : "info");
      return (
        <div className={`ux-note${tone}`} {...common} role="status">
          <UiIcon name={icon} />
          <span>{inline(text(block.text))}</span>
        </div>
      );
    }
    case "KeyValue":
      return (
        <div className="ux-kv" {...common}>
          {(block.rows as unknown[][]).map((row, index) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: rows are positional
            <div key={index}>
              <span>{text(row[0])}</span>
              <b>{text(row[1])}</b>
            </div>
          ))}
        </div>
      );
    case "Segmented": {
      const key = String(block.bind);
      const options = optionList(block.options, ctx);
      const current = Math.max(
        0,
        options.findIndex((option) => String(option.value) === String(ctx.values[key])),
      );
      return (
        <div className="ux-field" {...common}>
          <span className="ux-label" id={`${id}-l`}>
            {text(block.label)}
          </span>
          <div
            className="ux-seg"
            role="radiogroup"
            aria-labelledby={`${id}-l`}
            style={{ "--n": options.length, "--i": current } as React.CSSProperties}
            onKeyDown={(event) => {
              // Left and Right follow the reading direction; Up and Down never do (review).
              const rtl = getComputedStyle(event.currentTarget).direction === "rtl";
              const step = {
                ArrowLeft: rtl ? 1 : -1,
                ArrowRight: rtl ? -1 : 1,
                ArrowDown: 1,
                ArrowUp: -1,
              }[event.key];
              if (!step || ctx.frozen || ctx.locked) return;
              event.preventDefault();
              const next = (current + step + options.length) % options.length;
              const option = options[next];
              if (!option) return;
              ctx.pick(key, option.value, option.also);
              const buttons = event.currentTarget.querySelectorAll("button");
              (buttons[next] as HTMLButtonElement | undefined)?.focus();
            }}
          >
            {options.map((option, index) => (
              // biome-ignore lint/a11y/useSemanticElements: the reference's radio buttons
              <button
                key={String(option.value)}
                type="button"
                role="radio"
                aria-checked={index === current}
                tabIndex={index === current ? 0 : -1}
                disabled={ctx.frozen || ctx.locked}
                onClick={() => ctx.pick(key, option.value, option.also)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      );
    }
    case "Number": {
      const key = String(block.bind);
      return (
        <NumberField
          block={block}
          path={path}
          id={id}
          value={ctx.values[key]}
          hint={block.hint !== undefined ? text(block.hint) : null}
          ctx={ctx}
          common={common}
        />
      );
    }
    case "Delivery":
      return (
        <div className="ux-field" {...common}>
          <span className="ux-label" id={`${id}-l`}>
            {t`Notification method`}
          </span>
          {/* biome-ignore lint/a11y/useSemanticElements: the reference's pick rows (Desktop-37 2230) */}
          <div className="ux-picks" role="group" aria-labelledby={`${id}-l`}>
            {(block.channels as string[]).map((channel) => (
              // biome-ignore lint/a11y/useSemanticElements: a read-only checked pick row (Q59)
              <button
                key={channel}
                type="button"
                className="ux-pick"
                role="checkbox"
                aria-checked="true"
                // Read-only, not disabled: the reference's disabled dim does not apply.
                aria-disabled="true"
              >
                <span className="ux-box" aria-hidden="true">
                  <Icon name="check" />
                </span>
                <span>
                  {channel === "app"
                    ? t`In the app`
                    : channel === "push"
                      ? t`Phone notification`
                      : t`Agent call`}
                </span>
              </button>
            ))}
          </div>
        </div>
      );
    case "Button": {
      const action = block.action as { do?: string } | undefined;
      const safe = action && ["go", "open", "copy"].includes(String(action.do));
      const sends = !action || action.do === "send";
      // Every control waits while the card builds; only a sent card keeps go/open/copy.
      const off =
        ctx.frozen ||
        (!safe && (ctx.locked || (sends && ctx.sendOff))) ||
        // A `disabled` that fails to evaluate disables, as the server refuses it (fail closed).
        (block.disabled !== undefined && Boolean(evaluate(block.disabled, ctx.env, true)));
      return (
        <button
          type="button"
          className={`btn sm ${block.style === "primary" ? "primary" : "outline"}${block.full ? " ux-full" : ""}`}
          {...common}
          disabled={off}
          onClick={() => ctx.act(block, path)}
        >
          <UiIcon name={block.icon} />
          <span>{text(block.label)}</span>
        </button>
      );
    }
  }
  return null;
}

function NumberField({
  block,
  id,
  value,
  hint,
  ctx,
  common,
}: {
  block: UiBlock;
  path: string;
  id: string;
  value: unknown;
  hint: string | null;
  ctx: Ctx;
  common: Record<string, string>;
}) {
  const key = String(block.bind);
  const [draft, setDraft] = useState(value == null ? "" : String(value));
  // Shown once the owner leaves the field or presses Enter, never mid-typing.
  const [checked, setChecked] = useState(false);
  const bad = parseCardNumber(draft) === undefined;
  const { unreadable } = ctx;
  // A field that is hidden or removed no longer holds the send (review round 4).
  useEffect(() => () => unreadable(key, false), [key, unreadable]);
  // Only an outside change (an option's `also`, a reset) replaces the owner's draft.
  // biome-ignore lint/correctness/useExhaustiveDependencies: the draft is the local echo
  useEffect(() => {
    const parsed = parseCardNumber(draft);
    if (parsed !== (value ?? null)) {
      setDraft(value == null ? "" : String(value));
      ctx.unreadable(key, false);
    }
  }, [value]);
  return (
    <div className="ux-field" {...common}>
      <label htmlFor={id}>
        <span>{ctx.stale(renderTemplate(String(block.label), ctx.env))}</span>
        {hint !== null && <small data-ux-out="">{hint}</small>}
      </label>
      <div className="ux-input">
        {typeof block.prefix === "string" && <span className="ux-affix">{block.prefix}</span>}
        <input
          id={id}
          type="text"
          inputMode="decimal"
          dir="ltr"
          autoComplete="off"
          value={draft}
          aria-required={block.required ? true : undefined}
          aria-invalid={ctx.invalid === key || (bad && checked) ? true : undefined}
          aria-describedby={bad && checked ? `${id}-err` : undefined}
          data-ux-bind={key}
          disabled={ctx.frozen || ctx.locked}
          onChange={(event) => {
            setDraft(event.target.value);
            // An unreadable draft («2,4») is never sent as a prefix value: it holds the
            // card's send until it reads as a number (review M7).
            const parsed = parseCardNumber(event.target.value);
            ctx.unreadable(key, parsed === undefined);
            if (parsed !== undefined) ctx.type(key, parsed);
          }}
          onBlur={() => setChecked(true)}
          onKeyDown={(event) => {
            if (event.key !== "Enter") return;
            event.preventDefault();
            setChecked(true);
            if (bad) return; // the field's own error says why nothing was sent
            const card = event.currentTarget.closest(".ux");
            const primary = card?.querySelector<HTMLButtonElement>(".btn.primary");
            if (primary && !primary.disabled) primary.click();
            else ctx.checkRequired();
          }}
        />
        {typeof block.suffix === "string" && <span className="ux-affix">{block.suffix}</span>}
      </div>
      {bad && checked && (
        // The reference's field error (Desktop-37 .field-err, 5547).
        <span className="field-err" id={`${id}-err`} role="alert">
          <Icon name="alert" />
          <span>{t`Invalid value.`}</span>
        </span>
      )}
    </div>
  );
}

function More({ block, path, ctx }: { block: UiBlock; path: string; ctx: Ctx }) {
  const [open, setOpen] = useState(false);
  if (!open)
    return (
      <button type="button" className="ux-more" data-ux={path} onClick={() => setOpen(true)}>
        {typeof block.label === "string" ? block.label : t`Show more`}
      </button>
    );
  return (
    <div className="ux-col" data-ux={path}>
      {(block.children as UiBlock[]).map((child, index) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: node paths are positional (data-ux)
        <Block key={`${path}.${index}`} block={child} path={`${path}.${index}`} ctx={ctx} />
      ))}
    </div>
  );
}

function requiredMissing(blocks: UiBlock[], ctx: Ctx): UiBlock | null {
  for (const block of blocks) {
    if (!visible(block, ctx)) continue;
    if (block.required && [null, undefined, ""].includes(ctx.values[String(block.bind)] as never)) {
      return block;
    }
    if (Array.isArray(block.children)) {
      const missing = requiredMissing(block.children as UiBlock[], ctx);
      if (missing) return missing;
    }
  }
  return null;
}

export default function UiCard({
  part,
  index,
  host,
}: {
  part: UiPart;
  index: number;
  host: UiPartHost;
}) {
  const { i18n } = useLingui();
  const navigate = useNavigate();
  const genui = useGenuiHost();
  const doc = part.document;
  const message = genui?.messages.find((item) => item.id === host.messageId);
  const saved = message?.ui_state?.parts?.[String(index)]?.values;
  const [values, setValues] = useState<Values>(() => ({ ...doc.state, ...(saved ?? {}) }));
  const [whyOpen, setWhyOpen] = useState(false);
  const [invalid, setInvalid] = useState<string | null>(null);
  const [unreadable, setUnreadable] = useState<ReadonlySet<string>>(() => new Set());
  // Stable, so a field's cleanup on hide or unmount runs only then.
  const markUnreadable = useCallback((key: string, bad: boolean) => {
    setUnreadable((old) => {
      if (old.has(key) === bad) return old;
      const next = new Set(old);
      if (bad) next.add(key);
      else next.delete(key);
      return next;
    });
  }, []);
  const [notice, setNotice] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [sentHere, setSentHere] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const committed = !host.messageId.startsWith("preview:");
  const building = Boolean(part.building);
  const facts = useMemo(
    () => Object.fromEntries(Object.entries(doc.facts).map(([key, fact]) => [key, fact.value])),
    [doc.facts],
  );
  const env = useMemo(
    () =>
      environment(doc.state, doc.calc, facts, values, {
        currency: doc.currency ?? null,
        language: i18n.locale.startsWith("en") ? "en" : "ar",
      }),
    [doc, facts, values, i18n.locale],
  );
  const lock = message && genui ? cardLock(message, index, genui.messages) : null;
  const awaiting =
    sentHere !== null && !genui?.messages.some((item) => item.client_nonce === sentHere);
  const locked = Boolean(lock) || awaiting;
  const agentId = host.agentId ?? doc.agent_id ?? null;
  const agent = genui?.agents.find((item) => item.id === agentId);
  const blocked = genui
    ? sendBlocked(agentId, host.threadId, genui.messages, genui.runs, Boolean(agent?.paused))
    : null;
  const oldest = Math.min(
    ...Object.values(doc.facts)
      .map((fact) => (fact.observed_at ? Date.parse(fact.observed_at) : Number.NaN))
      .filter(Number.isFinite),
  );
  const stale = (text: string) => {
    // «الآن» over a fact older than 120 s becomes «آخر تحديث HH:MM» (§9.6).
    if (!Number.isFinite(oldest) || Date.now() - oldest <= STALE_MS) return text;
    const time = new Date(oldest).toLocaleTimeString("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
    });
    // JavaScript's \b is ASCII-only, so «الآن» is matched up to a space or the end.
    return text.replace(/^(الآن|now)(?=[\s:،,.]|$)/iu, `${t`Last updated`} ${time}`);
  };

  /** The reference's `uxMissing`: the first visible required input left empty. */
  function checkRequired(): boolean {
    const missing = requiredMissing(doc.blocks, ctx);
    if (!missing) return true;
    const key = String(missing.bind);
    const label = renderTemplate(String(missing.label), env);
    setInvalid(key);
    setNotice(t`Complete «${label}» first`);
    ref.current?.querySelector<HTMLInputElement>(`[data-ux-bind="${CSS.escape(key)}"]`)?.focus();
    return false;
  }

  async function send(block: UiBlock, path: string) {
    if (!checkRequired() || sending || unreadable.size > 0) return;
    setSending(true);
    setNotice(null);
    const nonce = crypto.randomUUID();
    try {
      navigator.vibrate?.(8);
      await api.post(`/threads/${host.threadId}/messages`, {
        content: "",
        client_nonce: nonce,
        ui_submit: { source_message_id: host.messageId, part: index, path, values },
      });
      const action = block.action as { lock?: boolean } | undefined;
      // Locked at once; the submission's own message then carries the lock (§8.2).
      if (action?.lock !== false) setSentHere(nonce);
    } catch (error) {
      setNotice(userError(error));
    } finally {
      setSending(false);
    }
  }

  const ctx: Ctx = {
    doc,
    env,
    values,
    locked,
    frozen: building || !committed || sending,
    invalid,
    sendOff: Boolean(blocked) || unreadable.size > 0,
    newest: building ? doc.blocks.length - 1 : -1,
    stale,
    pick(key, value, also) {
      if (locked) return;
      navigator.vibrate?.(6);
      setValues((old) => ({ ...old, [key]: value, ...(also ?? {}) }));
      if (also && Object.hasOwn(also, invalid ?? "")) setInvalid(null);
    },
    type(key, value) {
      setValues((old) => ({ ...old, [key]: value }));
      if (invalid === key) setInvalid(null);
    },
    unreadable: markUnreadable,
    checkRequired: () => checkRequired(),
    act(block, path) {
      const action = block.action as Record<string, unknown> | undefined;
      if (!action || action.do === "send") {
        void send(block, path);
      } else if (action.do === "go") {
        const route = ROUTES[String(action.route)];
        if (route) navigate(route);
      } else if (action.do === "set") {
        setValues((old) => ({ ...old, [String(action.key)]: evaluate(action.value, env) }));
      } else if (action.do === "toggle") {
        setValues((old) => ({ ...old, [String(action.key)]: !old[String(action.key)] }));
      } else if (action.do === "reset") {
        setValues({ ...doc.state });
      }
    },
  };

  async function unlock() {
    try {
      await api.post(
        `/threads/${host.threadId}/messages/${host.messageId}/ui-state/${index}/unlock`,
        {},
      );
      setSentHere(null);
      setNotice(t`Edit, then send again`);
    } catch (error) {
      setNotice(userError(error));
    }
  }

  const title = renderTemplate(doc.title, env);
  // Stopped before any block was built: no card, its fallback text (review E2).
  if (part.cut === 0) return <p className="ux-fallback">{doc.fallback}</p>;
  const showFoot = !building && (locked || doc.why || part.cut !== undefined);
  const sources = Object.values(doc.facts).filter((fact) => fact.value !== null);
  return (
    // biome-ignore lint/a11y/useSemanticElements: the reference's card is a labelled group
    <div
      ref={ref}
      className={`ux${locked ? " is-sent" : ""}${building ? " is-building" : ""}`}
      data-ux-mid={host.messageId}
      role="group"
      aria-label={title || t`Interactive interface`}
      aria-busy={building || undefined}
    >
      <div className="ux-head">
        {doc.icon && (
          // No icon tile until the head line names one (Desktop-37 6539).
          <span className="ux-ic">
            <UiIcon name={doc.icon} />
          </span>
        )}
        <span className="ux-ht">
          <b>{title}</b>
          {doc.sub && <small>{renderTemplate(doc.sub, env)}</small>}
        </span>
      </div>
      <div className="ux-body">
        {doc.blocks.map((block, position) =>
          part.cut !== undefined && position >= part.cut ? null : (
            // biome-ignore lint/suspicious/noArrayIndexKey: blocks are positional and append-only
            <Block key={position} block={block} path={String(position)} ctx={ctx} />
          ),
        )}
        {building && (
          <div className="ux-skel" aria-hidden="true">
            <i />
            <i />
          </div>
        )}
      </div>
      {notice && (
        <p className="ux-notice" role="alert">
          {notice}
        </p>
      )}
      {showFoot && (
        <div className="ux-foot">
          {locked && (
            <>
              <span className="ux-sent">
                <Icon name="checks" />
                <span>{t`Sent to ${agent?.name ?? "Lonora"}`}</span>
              </span>
              <button type="button" className="ux-link" onClick={() => void unlock()}>
                {t`Edit`}
              </button>
            </>
          )}
          {part.cut !== undefined && (
            <span className="ux-cut">
              <Icon name="stop" />
              <span>{t`You stopped the reply before the interface was complete`}</span>
            </span>
          )}
          {doc.why && (
            <button
              type="button"
              className="ux-why-b"
              aria-expanded={whyOpen}
              onClick={() => setWhyOpen((open) => !open)}
            >
              <Icon name="sparkle" />
              <span>{t`Why this interface?`}</span>
            </button>
          )}
        </div>
      )}
      {showFoot && doc.why && whyOpen && (
        <p className="ux-why">
          {doc.why}
          {sources.length > 0 && (
            <span className="ux-sources">
              {t`Sources`}: {[...new Set(sources.map((fact) => fact.source))].join("، ")}
              {Number.isFinite(oldest) &&
                ` · ${new Date(oldest).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`}
            </span>
          )}
        </p>
      )}
    </div>
  );
}
