/** A lonora-ui v2 card in the reference's look (Desktop-37 aa_genui, `.ux*`; docs/genui.md §8).
 * The server compiled and checked it; this renders it, keeps its values, and sends
 * through `MessageCreate.ui_submit` only: the server writes the owner's bubble and data.
 * While the card builds, and until its message is committed, every control is disabled. */
import { t } from "@lingui/core/macro";
import { useLingui } from "@lingui/react/macro";
import type {
  UiActionKind,
  UiBlock,
  UiDocument,
  UiNodeProps,
  UiOption,
  UiPart,
  UiRenderedNodeType,
  UiRoute,
  UiSlotCard,
} from "@lonora/contracts";
import {
  type CardInline,
  cardInline,
  cardLock,
  cardMarkdown,
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

const ROUTES: Record<UiRoute, string> = {
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

/** The reference's inline Markdown in card text: **bold** only, never HTML, never a link. */
function inline(text: string): ReactNode {
  return pieces(cardInline(text));
}

function pieces(parts: CardInline[]): ReactNode {
  return parts.map((piece, index) =>
    piece.bold ? (
      // biome-ignore lint/suspicious/noArrayIndexKey: static split of one string
      <b key={index}>{piece.text}</b>
    ) : (
      // biome-ignore lint/suspicious/noArrayIndexKey: static split of one string
      <Fragment key={index}>{piece.text}</Fragment>
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

type NodeProps = {
  block: UiBlock;
  path: string;
  ctx: Ctx;
  /** `data-ux` (and `data-ux-new` on the block being built). */
  common: Record<string, string>;
  id: string;
  /** A display template rendered against the card's values. */
  text: (value: unknown) => string;
  /** ` t-<tone>` or "". */
  tone: string;
};

function Block({ block, path, ctx }: { block: UiBlock; path: string; ctx: Ctx }) {
  const isNew = path === String(ctx.newest);
  const common = {
    "data-ux": path,
    "data-ux-type": block.type,
    ...(isNew ? { "data-ux-new": "" } : {}),
  };
  if (!visible(block, ctx)) return <div {...common} data-ux-off="" hidden />;
  const Render = Object.hasOwn(NODES, block.type)
    ? NODES[block.type as UiRenderedNodeType]
    : undefined;
  if (!Render) return null;
  return (
    <Render
      block={block}
      path={path}
      ctx={ctx}
      common={common}
      id={`ux-${path.replace(/\./g, "-")}`}
      text={(value) => ctx.stale(renderTemplate(String(value ?? ""), ctx.env))}
      tone={typeof block.tone === "string" ? ` t-${block.tone}` : ""}
    />
  );
}

function Children({ block, path, ctx }: { block: UiBlock; path: string; ctx: Ctx }) {
  return (
    <>
      {((block.children as UiBlock[]) ?? []).map((child, index) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: node paths are positional (data-ux)
        <Block key={`${path}.${index}`} block={child} path={`${path}.${index}`} ctx={ctx} />
      ))}
    </>
  );
}

function Segmented({ block, ctx, common, id, text }: NodeProps) {
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

/** The reference's Select (Desktop-37 6418): a native select with a chevron. */
function Select({ block, ctx, common, id, text }: NodeProps) {
  const key = String(block.bind);
  const options = optionList(block.options, ctx);
  const current = options.findIndex((option) => String(option.value) === String(ctx.values[key]));
  return (
    <div className="ux-field" {...common}>
      <label htmlFor={id}>
        <span>{text(block.label)}</span>
      </label>
      <div className="ux-input ux-select">
        <select
          id={id}
          data-ux-bind={key}
          value={current < 0 ? "" : String(current)}
          disabled={ctx.frozen || ctx.locked}
          onChange={(event) => {
            const option = options[Number(event.target.value)];
            if (option) ctx.pick(key, option.value, option.also);
          }}
        >
          {current < 0 && <option value="" disabled hidden />}
          {options.map((option, index) => (
            <option key={String(option.value)} value={String(index)}>
              {option.label}
            </option>
          ))}
        </select>
        <Icon name="down" />
      </div>
    </div>
  );
}

function NumberNode({ block, path, ctx, common, id, text }: NodeProps) {
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

/** The reference's Slider (Desktop-37 6416): a range with its `show` readout. */
function Slider({ block, ctx, common, id, text }: NodeProps) {
  const key = String(block.bind);
  const min = typeof block.min === "number" ? block.min : 0;
  const max = typeof block.max === "number" ? block.max : 100;
  const step = typeof block.step === "number" && block.step > 0 ? block.step : 1;
  const raw = Number(ctx.values[key] ?? min);
  const value = Number.isFinite(raw) ? Math.max(min, Math.min(max, raw)) : min;
  const pct = max > min ? ((value - min) / (max - min)) * 100 : 0;
  const show = text(typeof block.show === "string" ? block.show : `{$${key}}`);
  return (
    <div className="ux-field ux-slider" {...common}>
      <label htmlFor={id}>
        <span>{text(block.label)}</span>
        <output htmlFor={id} data-ux-out="">
          {show}
        </output>
      </label>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        style={{ "--p": `${pct}%` } as React.CSSProperties}
        data-ux-bind={key}
        aria-valuetext={show}
        disabled={ctx.frozen || ctx.locked}
        onChange={(event) => ctx.type(key, Number(event.target.value))}
      />
    </div>
  );
}

function TextNode({ block, common, text, tone }: NodeProps) {
  return (
    <div className={`ux-text${tone}${block.size === "sm" ? " sm" : ""}`} {...common} role="status">
      {inline(text(block.text))}
    </div>
  );
}

function Title({ block, common, text }: NodeProps) {
  return (
    <div className="ux-title" {...common}>
      {text(block.text)}
    </div>
  );
}

/** Paragraphs and lists with **bold**; never HTML, links show as their label. */
function MarkdownNode({ block, common, text }: NodeProps) {
  return (
    <div className="ux-md" {...common}>
      {cardMarkdown(text(block.text)).map((item, index) => {
        const lines = item.lines.map((line, at) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: static lines of one text
          <Fragment key={at}>{pieces(line)}</Fragment>
        ));
        if (item.kind === "p")
          return (
            // biome-ignore lint/suspicious/noArrayIndexKey: static blocks of one text
            <p key={index}>
              {lines.map((line, at) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: static lines of one text
                <Fragment key={at}>
                  {at > 0 && <br />}
                  {line}
                </Fragment>
              ))}
            </p>
          );
        const List = item.kind;
        return (
          // biome-ignore lint/suspicious/noArrayIndexKey: static blocks of one text
          <List key={index}>
            {lines.map((line, at) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: static lines of one text
              <li key={at}>{line}</li>
            ))}
          </List>
        );
      })}
    </div>
  );
}

function Badge({ block, common, text, tone }: NodeProps) {
  return (
    <span className={`ux-badge${tone}`} {...common}>
      <UiIcon name={block.icon} />
      <span>{text(block.text)}</span>
    </span>
  );
}

function Note({ block, common, text, tone }: NodeProps) {
  const icon =
    block.icon ?? (block.tone === "warn" ? "alert" : block.tone === "good" ? "check" : "info");
  return (
    <div className={`ux-note${tone}`} {...common} role="status">
      <UiIcon name={icon} />
      <span>{inline(text(block.text))}</span>
    </div>
  );
}

function KeyValue({ block, common, text }: NodeProps) {
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
}

/** The reference's Stat (Desktop-37 6412): label, value, and a sub line with its trend. */
function Stat({ block, ctx, common, text, tone }: NodeProps) {
  const trend = block.trend !== undefined ? String(evaluate(block.trend, ctx.env, "") ?? "") : "";
  const arrow = trend === "up" || trend === "down" ? trend : "";
  return (
    <div className={`ux-stat${tone}`} {...common}>
      <small>
        <UiIcon name={block.icon} />
        {text(block.label)}
      </small>
      <b>{text(block.value)}</b>
      {block.sub !== undefined && (
        <span className={`ux-sub${arrow ? ` tr-${arrow}` : ""}`} dir="auto">
          {arrow && <Icon name={arrow === "down" ? "trendDown" : "trend"} />}
          {text(block.sub)}
        </span>
      )}
    </div>
  );
}

function ButtonNode({ block, path, ctx, common, text }: NodeProps) {
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

function Divider({ common }: NodeProps) {
  return <hr className="ux-hr" {...common} />;
}

function Row({ block, path, ctx, common }: NodeProps) {
  return (
    <div className="ux-row" {...common}>
      <Children block={block} path={path} ctx={ctx} />
    </div>
  );
}

function Col({ block, path, ctx, common }: NodeProps) {
  return (
    <div className="ux-col" {...common}>
      <Children block={block} path={path} ctx={ctx} />
    </div>
  );
}

function Grid({ block, path, ctx, common }: NodeProps) {
  const cols = block.cols === 1 || block.cols === 3 ? block.cols : 2;
  return (
    <div className="ux-grid" {...common} style={{ "--cols": cols } as React.CSSProperties}>
      <Children block={block} path={path} ctx={ctx} />
    </div>
  );
}

/** The reference's inner panel (Desktop-37 6402). */
function Card({ block, path, ctx, common, text }: NodeProps) {
  return (
    <div className="ux-panel" {...common}>
      {block.title !== undefined && (
        <div className="ux-panel-h">
          <UiIcon name={block.icon} />
          <b>{text(block.title)}</b>
        </div>
      )}
      <Children block={block} path={path} ctx={ctx} />
    </div>
  );
}

function More({ block, path, ctx, common, text }: NodeProps) {
  const [open, setOpen] = useState(false);
  if (!open)
    return (
      <button type="button" className="ux-more" {...common} onClick={() => setOpen(true)}>
        {typeof block.label === "string" ? text(block.label) : t`Show more`}
      </button>
    );
  return (
    <div className="ux-col" {...common}>
      <Children block={block} path={path} ctx={ctx} />
    </div>
  );
}

function Delivery({ block, common, id }: NodeProps) {
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
}

/** A trusted slot (mandate 10.2): a fixed card in the agent's card. The agent chose only
 * where it sits; the conversation draws the live record inside (`GenuiHost.slot`), with its
 * own server actions, and this frame, which no agent node can draw, says it is Lonora's. */
function Slot({ block, common }: NodeProps) {
  const host = useGenuiHost();
  const card = block.card as UiSlotCard;
  const inner = host?.slot?.({ card, record: String(block.record) }) ?? null;
  return (
    <section
      className="ux-slot"
      {...common}
      data-slot-card={card}
      data-slot-live={inner ? "" : undefined}
      aria-label={t`Fixed card from Lonora`}
    >
      <div className="ux-slot-mark" aria-hidden="true">
        <Icon name="shield" width={14} height={14} style={{ flex: "none" }} />
        <span>{t`Fixed card from Lonora`}</span>
      </div>
      {inner ?? <p className="ux-slot-gone">{t`This card is not available here.`}</p>}
    </section>
  );
}

/** Every node type of the catalog generated from the server contract, and the server's
 * delivery row (mandate 10.1.5): a node the server accepts and this map lacks fails
 * `pnpm check`. */
const NODES: Record<UiRenderedNodeType, (props: NodeProps) => ReactNode> = {
  Segmented,
  Select,
  Number: NumberNode,
  Slider,
  Text: TextNode,
  Title,
  Markdown: MarkdownNode,
  Note,
  Badge,
  KeyValue,
  Stat,
  Button: ButtonNode,
  Divider,
  Row,
  Col,
  Grid,
  Card,
  More,
  Slot,
  Delivery,
};

/** Every prop of every catalog node, each drawn by this renderer (typed against the catalog:
 * a prop the server contract gains, or loses, fails `pnpm check` until it is drawn here). */
export const DRAWN_PROPS: UiNodeProps = {
  Segmented: { bind: true, label: true, options: true, when: true },
  Select: { bind: true, label: true, options: true, when: true },
  Number: {
    bind: true,
    label: true,
    hint: true,
    prefix: true,
    suffix: true,
    required: true,
    when: true,
  },
  Slider: { bind: true, label: true, min: true, max: true, step: true, show: true, when: true },
  Text: { text: true, tone: true, size: true, when: true },
  Title: { text: true, when: true },
  Markdown: { text: true, when: true },
  Note: { text: true, tone: true, icon: true, when: true },
  Badge: { text: true, tone: true, icon: true, when: true },
  KeyValue: { rows: true, when: true },
  Stat: { label: true, value: true, sub: true, trend: true, tone: true, icon: true, when: true },
  Button: {
    label: true,
    action: true,
    style: true,
    icon: true,
    full: true,
    disabled: true,
    when: true,
  },
  Divider: { when: true },
  Row: { children: true, when: true },
  Col: { children: true, when: true },
  Grid: { children: true, cols: true, when: true },
  Card: { children: true, title: true, icon: true, when: true },
  More: { children: true, label: true, when: true },
  Slot: { card: true, record: true },
};

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
            // The card's own primary Button only, never a fixed card's inside a slot.
            const card = event.currentTarget.closest(".ux");
            const primary = card?.querySelector<HTMLButtonElement>(
              '.btn.primary[data-ux-type="Button"]',
            );
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
    // «الآن» over a fact older than 120 s becomes «آخر تحديث HH:MM» (docs/genui.md §8).
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
      // Locked at once; the submission's own message then carries the lock (docs/genui.md §7).
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
      // Every action of the catalog (exhaustive: an action the contract gains fails tsc).
      const kind = (action?.do ?? "send") as UiActionKind;
      switch (kind) {
        case "send":
          void send(block, path);
          break;
        case "go": {
          const name = String(action?.route);
          if (Object.hasOwn(ROUTES, name)) navigate(ROUTES[name as UiRoute]);
          break;
        }
        case "open": {
          // A literal https URL the server matched to the owner's message or a tool result.
          const url = String(action?.url);
          if (url.startsWith("https://")) window.open(url, "_blank", "noopener,noreferrer");
          break;
        }
        case "copy": {
          const copied = renderTemplate(String(action?.text ?? ""), env);
          void navigator.clipboard?.writeText(copied).then(
            () => {
              navigator.vibrate?.(8);
              setNotice(t`Copied`);
            },
            () => setNotice(copied),
          );
          break;
        }
        case "set":
          setValues((old) => ({ ...old, [String(action?.key)]: evaluate(action?.value, env) }));
          break;
        case "toggle":
          setValues((old) => ({ ...old, [String(action?.key)]: !old[String(action?.key)] }));
          break;
        case "reset":
          setValues({ ...doc.state });
          break;
        default:
          kind satisfies never;
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
          {/* When the card's facts were read; never the tools' internal names (mandate 17). */}
          {sources.length > 0 && Number.isFinite(oldest) && (
            <span className="ux-sources">
              {t`Last updated`}{" "}
              {new Date(oldest).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
        </p>
      )}
    </div>
  );
}
