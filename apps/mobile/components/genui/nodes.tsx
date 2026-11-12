// biome-ignore-all lint/suspicious/noArrayIndexKey: compiled card nodes, rows and options are positional and immutable.
/** The native renderer of every lonora-ui v2 node (mandate 10.1.5), the twin of the web
 * `UiCard` in the reference's look (Desktop-37 `.ux*`). `NODES` is typed against the catalog
 * generated from the server contract: a node the server accepts and this renderer does not
 * draw fails `pnpm check`. Agents compose; colours, type and spacing are the renderer's. */
import type { UiBlock, UiOption, UiRenderedNodeType } from "@lonora/contracts";
import {
  type CardInline,
  cardInline,
  cardMarkdown,
  type environment,
  evaluate,
  parseCardNumber,
  renderTemplate,
} from "@lonora/core";
import { ICON_PATHS, type IconName } from "@lonora/ui-tokens";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { Pressable, Text, TextInput, View } from "react-native";
import Svg, { Path } from "react-native-svg";
import type { Label } from "../../lib/i18n";
import type { CardPalette } from "./theme";

type Values = Record<string, unknown>;
export type CardCtx = {
  env: ReturnType<typeof environment>;
  values: Values;
  locked: boolean;
  frozen: boolean;
  invalid: string | null;
  sendOff: boolean;
  rtl: boolean;
  p: CardPalette;
  t: (key: Label) => string;
  stale: (text: string) => string;
  pick: (key: string, value: unknown, also?: Values) => void;
  type: (key: string, value: unknown) => void;
  unreadable: (key: string, bad: boolean) => void;
  act: (block: UiBlock, path: string) => void;
  /** The card's primary send, for Enter in a Number field. */
  submitPrimary: () => void;
  register: (key: string, input: TextInput | null) => void;
};
type NodeProps = { block: UiBlock; path: string; ctx: CardCtx };

export function CardIcon({ name, size, color }: { name: unknown; size: number; color: string }) {
  if (typeof name !== "string" || !Object.hasOwn(ICON_PATHS, name)) return null;
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <Path
        d={ICON_PATHS[name as IconName]}
        stroke={color}
        strokeWidth={1.7}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

const row = (rtl: boolean) => (rtl ? ("row-reverse" as const) : ("row" as const));
const align = (rtl: boolean) => (rtl ? ("right" as const) : ("left" as const));

function Inline({ pieces, color, size, weight }: InlineProps) {
  return (
    <>
      {pieces.map((piece, index) => (
        <Text
          key={index}
          style={{
            color,
            fontSize: size,
            fontWeight: piece.bold ? "700" : (weight ?? "400"),
          }}
        >
          {piece.text}
        </Text>
      ))}
    </>
  );
}
type InlineProps = {
  pieces: CardInline[];
  color: string;
  size: number;
  weight?: "400" | "500" | "600" | "700";
};

function text(ctx: CardCtx, value: unknown): string {
  return ctx.stale(renderTemplate(String(value ?? ""), ctx.env));
}

function optionList(options: unknown, ctx: CardCtx) {
  if (!Array.isArray(options)) return [];
  return (options as UiOption[]).map((option) =>
    option !== null && typeof option === "object"
      ? {
          value: option.value,
          label: renderTemplate(String(option.label ?? option.value ?? ""), ctx.env),
          also: option.also as Values | undefined,
        }
      : { value: option, label: String(option ?? ""), also: undefined },
  );
}

export function visible(block: UiBlock, ctx: CardCtx): boolean {
  return block.when === undefined || Boolean(evaluate(block.when, ctx.env, false));
}

/** One node: hidden when its `when` is false, else its renderer. */
export function Node({ block, path, ctx }: NodeProps): ReactNode {
  const testID = `ux-node-${block.type}-${path}`;
  if (!visible(block, ctx)) return <View testID={`${testID}-off`} style={{ display: "none" }} />;
  const Render = NODES[block.type as UiRenderedNodeType];
  if (!Render) return null;
  return (
    <View testID={testID} style={{ minWidth: 0 }}>
      <Render block={block} path={path} ctx={ctx} />
    </View>
  );
}

function Children({ block, path, ctx }: NodeProps) {
  return (
    <>
      {((block.children as UiBlock[]) ?? []).map((child, index) => (
        <Node key={`${path}.${index}`} block={child} path={`${path}.${index}`} ctx={ctx} />
      ))}
    </>
  );
}

function FieldLabel({ label, aside, ctx }: { label: string; aside?: ReactNode; ctx: CardCtx }) {
  return (
    <View
      style={{
        flexDirection: row(ctx.rtl),
        alignItems: "baseline",
        justifyContent: "space-between",
        gap: 8,
      }}
    >
      <Text style={{ color: ctx.p.muted, fontSize: 13, fontWeight: "500" }}>{label}</Text>
      {aside}
    </View>
  );
}

function Segmented({ block, ctx }: NodeProps) {
  const key = String(block.bind);
  const options = optionList(block.options, ctx);
  const current = Math.max(
    0,
    options.findIndex((option) => String(option.value) === String(ctx.values[key])),
  );
  const label = text(ctx, block.label);
  return (
    <View style={{ gap: 6 }}>
      <FieldLabel label={label} ctx={ctx} />
      <View
        accessibilityRole="radiogroup"
        accessibilityLabel={label}
        style={{
          flexDirection: row(ctx.rtl),
          padding: 3,
          borderRadius: 12,
          backgroundColor: ctx.p.track,
        }}
      >
        {options.map((option, index) => {
          const on = index === current;
          return (
            <Pressable
              key={String(option.value)}
              accessibilityRole="radio"
              accessibilityState={{ checked: on, disabled: ctx.frozen || ctx.locked }}
              disabled={ctx.frozen || ctx.locked}
              onPress={() => ctx.pick(key, option.value, option.also)}
              style={{
                flex: 1,
                minHeight: 36,
                paddingHorizontal: 6,
                borderRadius: 9,
                alignItems: "center",
                justifyContent: "center",
                backgroundColor: on ? ctx.p.thumb : "transparent",
                ...(on
                  ? {
                      shadowColor: "#000",
                      shadowOpacity: 0.25,
                      shadowRadius: 3,
                      shadowOffset: { width: 0, height: 1 },
                      elevation: 1,
                    }
                  : {}),
              }}
            >
              <Text
                numberOfLines={1}
                style={{ color: on ? ctx.p.text : ctx.p.muted, fontSize: 13, fontWeight: "600" }}
              >
                {option.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

function Radio({ on, ctx }: { on: boolean; ctx: CardCtx }) {
  return (
    <View
      style={{
        width: 18,
        height: 18,
        borderRadius: 9,
        borderWidth: on ? 5.5 : 2,
        borderColor: on ? ctx.p.accent : ctx.p.lineStrong,
      }}
    />
  );
}

function Select({ block, ctx }: NodeProps) {
  const key = String(block.bind);
  const options = optionList(block.options, ctx);
  const [open, setOpen] = useState(false);
  const chosen = options.find((option) => String(option.value) === String(ctx.values[key]));
  const label = text(ctx, block.label);
  const off = ctx.frozen || ctx.locked;
  return (
    <View style={{ gap: 6 }}>
      <FieldLabel label={label} ctx={ctx} />
      <Pressable
        accessibilityRole="combobox"
        accessibilityLabel={label}
        accessibilityState={{ expanded: open, disabled: off }}
        disabled={off}
        onPress={() => setOpen((value) => !value)}
        style={{
          flexDirection: row(ctx.rtl),
          alignItems: "center",
          gap: 6,
          height: 44,
          paddingHorizontal: 12,
          borderRadius: 12,
          borderWidth: 1,
          borderColor: open ? ctx.p.lineStrong : ctx.p.line,
          backgroundColor: ctx.p.input,
        }}
      >
        <Text style={{ flex: 1, color: ctx.p.text, fontSize: 16, textAlign: align(ctx.rtl) }}>
          {chosen?.label ?? ""}
        </Text>
        <CardIcon name="down" size={16} color={ctx.p.muted} />
      </Pressable>
      {open && !off ? (
        <View
          accessibilityRole="radiogroup"
          accessibilityLabel={label}
          style={{ borderWidth: 1, borderColor: ctx.p.line, borderRadius: 12, overflow: "hidden" }}
        >
          {options.map((option, index) => {
            const on = option === chosen;
            return (
              <Pressable
                key={String(option.value)}
                accessibilityRole="radio"
                accessibilityState={{ checked: on }}
                onPress={() => {
                  ctx.pick(key, option.value, option.also);
                  setOpen(false);
                }}
                style={{
                  flexDirection: row(ctx.rtl),
                  alignItems: "center",
                  gap: 10,
                  minHeight: 42,
                  paddingHorizontal: 12,
                  paddingVertical: 8,
                  borderTopWidth: index ? 1 : 0,
                  borderColor: ctx.p.line,
                }}
              >
                <Radio on={on} ctx={ctx} />
                <Text style={{ color: ctx.p.text, fontSize: 14, fontWeight: on ? "600" : "400" }}>
                  {option.label}
                </Text>
              </Pressable>
            );
          })}
        </View>
      ) : null}
    </View>
  );
}

function NumberField({ block, ctx }: NodeProps) {
  const key = String(block.bind);
  const value = ctx.values[key];
  const [draft, setDraft] = useState(value == null ? "" : String(value));
  // Shown once the owner leaves the field or submits, never mid-typing.
  const [checked, setChecked] = useState(false);
  const bad = parseCardNumber(draft) === undefined;
  const { unreadable } = ctx;
  // A field that is hidden or removed no longer holds the send.
  useEffect(() => () => unreadable(key, false), [key, unreadable]);
  // Only an outside change (an option's `also`, a reset) replaces the owner's draft.
  // biome-ignore lint/correctness/useExhaustiveDependencies: the draft is the local echo
  useEffect(() => {
    if (parseCardNumber(draft) !== (value ?? null)) {
      setDraft(value == null ? "" : String(value));
      ctx.unreadable(key, false);
    }
  }, [value]);
  const label = text(ctx, block.label);
  const invalid = ctx.invalid === key || (bad && checked);
  return (
    <View style={{ gap: 6 }}>
      <FieldLabel
        label={label}
        ctx={ctx}
        aside={
          block.hint !== undefined ? (
            <Text style={{ color: ctx.p.faint, fontSize: 12 }}>{text(ctx, block.hint)}</Text>
          ) : null
        }
      />
      <View
        style={{
          flexDirection: row(ctx.rtl),
          alignItems: "center",
          gap: 6,
          height: 44,
          paddingHorizontal: 12,
          borderRadius: 12,
          borderWidth: 1,
          borderColor: invalid ? ctx.p.red : ctx.p.line,
          backgroundColor: ctx.p.input,
        }}
      >
        {typeof block.prefix === "string" ? (
          <Text style={{ color: ctx.p.muted, fontSize: 14 }}>{block.prefix}</Text>
        ) : null}
        <TextInput
          ref={(input) => ctx.register(key, input)}
          accessibilityLabel={label}
          aria-required={block.required ? true : undefined}
          aria-invalid={invalid || undefined}
          inputMode="decimal"
          keyboardType="decimal-pad"
          autoComplete="off"
          autoCorrect={false}
          editable={!(ctx.frozen || ctx.locked)}
          value={draft}
          onChangeText={(next) => {
            setDraft(next);
            // An unreadable draft («2,4») is never sent as a prefix value: it holds the
            // card's send until it reads as a number (review M7).
            const parsed = parseCardNumber(next);
            ctx.unreadable(key, parsed === undefined);
            if (parsed !== undefined) ctx.type(key, parsed);
          }}
          onBlur={() => setChecked(true)}
          onSubmitEditing={() => {
            setChecked(true);
            if (!bad) ctx.submitPrimary();
          }}
          style={{
            flex: 1,
            minWidth: 0,
            height: "100%",
            color: ctx.p.text,
            fontSize: 16,
            // Numbers read left to right in both languages, aligned to the field's end.
            writingDirection: "ltr",
            textAlign: "right",
            fontVariant: ["tabular-nums"],
          }}
        />
        {typeof block.suffix === "string" ? (
          <Text style={{ color: ctx.p.muted, fontSize: 14 }}>{block.suffix}</Text>
        ) : null}
      </View>
      {bad && checked ? (
        <View
          accessibilityRole="alert"
          style={{ flexDirection: row(ctx.rtl), alignItems: "center", gap: 6, marginTop: 6 }}
        >
          <CardIcon name="alert" size={15} color={ctx.p.red} />
          <Text style={{ color: ctx.p.red, fontSize: 14, fontWeight: "500" }}>
            {ctx.t("uiInvalidValue")}
          </Text>
        </View>
      ) : null}
    </View>
  );
}

function Slider({ block, ctx }: NodeProps) {
  const key = String(block.bind);
  const min = typeof block.min === "number" ? block.min : 0;
  const max = typeof block.max === "number" ? block.max : 100;
  const step = typeof block.step === "number" && block.step > 0 ? block.step : 1;
  const raw = Number(ctx.values[key] ?? min);
  const value = Number.isFinite(raw) ? Math.max(min, Math.min(max, raw)) : min;
  const fraction = max > min ? (value - min) / (max - min) : 0;
  const width = useRef(1);
  const off = ctx.frozen || ctx.locked;
  const show = text(ctx, typeof block.show === "string" ? block.show : `{$${key}}`);
  const label = text(ctx, block.label);
  const set = (next: number) => {
    const snapped = min + Math.round((next - min) / step) * step;
    const clean = Number(Math.max(min, Math.min(max, snapped)).toFixed(10));
    if (clean !== value) ctx.type(key, clean);
  };
  const at = (x: number) => {
    const ratio = Math.min(1, Math.max(0, x / width.current));
    set(min + (ctx.rtl ? 1 - ratio : ratio) * (max - min));
  };
  return (
    <View style={{ gap: 6 }}>
      <FieldLabel
        label={label}
        ctx={ctx}
        aside={<Text style={{ color: ctx.p.text, fontSize: 14, fontWeight: "700" }}>{show}</Text>}
      />
      <View
        accessible
        accessibilityRole="adjustable"
        accessibilityLabel={label}
        accessibilityValue={{ min, max, now: value, text: show }}
        accessibilityState={{ disabled: off }}
        accessibilityActions={[{ name: "increment" }, { name: "decrement" }]}
        onAccessibilityAction={(event) => {
          if (!off) set(value + (event.nativeEvent.actionName === "increment" ? step : -step));
        }}
        onLayout={(event) => {
          width.current = Math.max(1, event.nativeEvent.layout.width);
        }}
        onStartShouldSetResponder={() => !off}
        onMoveShouldSetResponder={() => !off}
        onResponderTerminationRequest={() => false}
        onResponderGrant={(event) => at(event.nativeEvent.locationX)}
        onResponderMove={(event) => at(event.nativeEvent.locationX)}
        style={{ height: 28, justifyContent: "center", opacity: off ? 0.6 : 1 }}
      >
        <View
          pointerEvents="none"
          style={{
            height: 6,
            borderRadius: 999,
            backgroundColor: ctx.p.track,
            flexDirection: row(ctx.rtl),
          }}
        >
          <View
            style={{
              width: `${fraction * 100}%`,
              borderRadius: 999,
              backgroundColor: ctx.p.accent,
            }}
          />
        </View>
        <View
          pointerEvents="none"
          style={{
            position: "absolute",
            [ctx.rtl ? "right" : "left"]: `${fraction * 100}%`,
            [ctx.rtl ? "marginRight" : "marginLeft"]: -11,
            width: 22,
            height: 22,
            borderRadius: 11,
            backgroundColor: "#ffffff",
            shadowColor: "#000",
            shadowOpacity: 0.35,
            shadowRadius: 5,
            shadowOffset: { width: 0, height: 2 },
            elevation: 3,
          }}
        />
      </View>
    </View>
  );
}

function TextNode({ block, ctx }: NodeProps) {
  const color =
    block.tone === "muted" ? ctx.p.muted : block.tone === "accent" ? ctx.p.accentInk : ctx.p.text;
  const size = block.size === "sm" ? 13 : 14;
  return (
    <Text
      accessibilityLiveRegion="polite"
      style={{ color, fontSize: size, lineHeight: size * 1.6, textAlign: align(ctx.rtl) }}
    >
      <Inline pieces={cardInline(text(ctx, block.text))} color={color} size={size} />
    </Text>
  );
}

function Title({ block, ctx }: NodeProps) {
  return (
    <Text
      accessibilityRole="header"
      style={{ color: ctx.p.text, fontSize: 16, fontWeight: "700", textAlign: align(ctx.rtl) }}
    >
      {text(ctx, block.text)}
    </Text>
  );
}

function MarkdownNode({ block, ctx }: NodeProps) {
  const blocks = cardMarkdown(text(ctx, block.text));
  const line = (pieces: CardInline[], key: number, marker?: string) => (
    <View key={key} style={{ flexDirection: row(ctx.rtl), gap: 8 }}>
      {marker ? <Text style={{ color: ctx.p.muted, fontSize: 14 }}>{marker}</Text> : null}
      <Text style={{ flex: 1, color: ctx.p.text, fontSize: 14, lineHeight: 22.4 }}>
        <Inline pieces={pieces} color={ctx.p.text} size={14} />
      </Text>
    </View>
  );
  return (
    <View style={{ gap: 8 }}>
      {blocks.map((item, index) => (
        <View key={index} style={{ gap: 4 }}>
          {item.lines.map((pieces, at) =>
            line(pieces, at, item.kind === "ul" ? "•" : item.kind === "ol" ? `${at + 1}.` : ""),
          )}
        </View>
      ))}
    </View>
  );
}

function Badge({ block, ctx }: NodeProps) {
  const good = block.tone === "accent" || block.tone === "good";
  const color = good ? ctx.p.accentInk : ctx.p.text;
  return (
    <View
      style={{
        alignSelf: ctx.rtl ? "flex-end" : "flex-start",
        flexDirection: row(ctx.rtl),
        alignItems: "center",
        gap: 4,
        paddingHorizontal: 8,
        paddingVertical: 2,
        borderRadius: 999,
        backgroundColor: good ? ctx.p.badgeGood : ctx.p.raise,
      }}
    >
      <CardIcon name={block.icon} size={13} color={color} />
      <Text style={{ color, fontSize: 11, fontWeight: "700" }}>{text(ctx, block.text)}</Text>
    </View>
  );
}

function Note({ block, ctx }: NodeProps) {
  const tone = typeof block.tone === "string" ? block.tone : "info";
  const icon = block.icon ?? (tone === "warn" ? "alert" : tone === "good" ? "check" : "info");
  const iconColor =
    tone === "warn"
      ? ctx.p.amber
      : tone === "good"
        ? ctx.p.accentInk
        : tone === "bad"
          ? ctx.p.red
          : ctx.p.muted;
  return (
    <View
      accessibilityLiveRegion="polite"
      style={{
        flexDirection: row(ctx.rtl),
        alignItems: "flex-start",
        gap: 8,
        paddingHorizontal: 12,
        paddingVertical: 10,
        borderRadius: 12,
        backgroundColor: ctx.p.toneBg[tone] ?? ctx.p.raise,
      }}
    >
      <View style={{ marginTop: 1 }}>
        <CardIcon name={icon} size={17} color={iconColor} />
      </View>
      <Text style={{ flex: 1, color: ctx.p.text, fontSize: 13, lineHeight: 20.8 }}>
        <Inline pieces={cardInline(text(ctx, block.text))} color={ctx.p.text} size={13} />
      </Text>
    </View>
  );
}

function KeyValue({ block, ctx }: NodeProps) {
  const rows = (block.rows as unknown[][]) ?? [];
  return (
    <View>
      {rows.map((item, index) => (
        <View
          key={index}
          style={{
            flexDirection: row(ctx.rtl),
            justifyContent: "space-between",
            gap: 16,
            paddingVertical: 8,
            borderBottomWidth: index < rows.length - 1 ? 1 : 0,
            borderColor: ctx.p.line,
          }}
        >
          <Text style={{ color: ctx.p.muted, fontSize: 14 }}>{text(ctx, item[0])}</Text>
          <Text
            style={{
              flexShrink: 1,
              color: ctx.p.text,
              fontSize: 14,
              fontWeight: "600",
              textAlign: ctx.rtl ? "left" : "right",
            }}
          >
            {text(ctx, item[1])}
          </Text>
        </View>
      ))}
    </View>
  );
}

function Stat({ block, ctx }: NodeProps) {
  const trend = block.trend !== undefined ? String(evaluate(block.trend, ctx.env, "") ?? "") : "";
  const valueColor = block.tone === "accent" ? ctx.p.accentInk : ctx.p.text;
  return (
    <View
      style={{
        gap: 1,
        minWidth: 0,
        paddingHorizontal: 12,
        paddingVertical: 10,
        borderRadius: 12,
        backgroundColor: ctx.p.raise,
      }}
    >
      <View style={{ flexDirection: row(ctx.rtl), alignItems: "center", gap: 4 }}>
        <CardIcon name={block.icon} size={14} color={ctx.p.muted} />
        <Text numberOfLines={1} style={{ color: ctx.p.muted, fontSize: 12, flexShrink: 1 }}>
          {text(ctx, block.label)}
        </Text>
      </View>
      <Text
        style={{
          color: valueColor,
          fontSize: 19,
          fontWeight: "700",
          lineHeight: 24.7,
          textAlign: align(ctx.rtl),
        }}
      >
        {text(ctx, block.value)}
      </Text>
      {block.sub !== undefined ? (
        <View style={{ flexDirection: row(ctx.rtl), alignItems: "center", gap: 3 }}>
          {trend === "up" || trend === "down" ? (
            <CardIcon
              name={trend === "down" ? "trendDown" : "trend"}
              size={14}
              color={trend === "down" ? ctx.p.amber : ctx.p.accentInk}
            />
          ) : null}
          <Text style={{ color: ctx.p.muted, fontSize: 12 }}>{text(ctx, block.sub)}</Text>
        </View>
      ) : null}
    </View>
  );
}

function Button({ block, path, ctx }: NodeProps) {
  const action = block.action as { do?: string } | undefined;
  const safe = action && ["go", "open", "copy"].includes(String(action.do));
  const sends = !action || action.do === "send";
  // Every control waits while the card builds; only a sent card keeps go/open/copy.
  const off =
    ctx.frozen ||
    (!safe && (ctx.locked || (sends && ctx.sendOff))) ||
    // A `disabled` that fails to evaluate disables, as the server refuses it (fail closed).
    (block.disabled !== undefined && Boolean(evaluate(block.disabled, ctx.env, true)));
  const primary = block.style === "primary";
  const color = primary ? ctx.p.onPrimary : ctx.p.text;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: off }}
      disabled={off}
      onPress={() => ctx.act(block, path)}
      style={({ pressed }) => ({
        flexGrow: 1,
        alignSelf: block.full ? "stretch" : undefined,
        flexDirection: row(ctx.rtl),
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
        minHeight: 40,
        paddingHorizontal: 14,
        paddingVertical: 6,
        borderRadius: 999,
        borderWidth: 1,
        borderColor: primary ? "transparent" : ctx.p.lineStrong,
        backgroundColor: primary ? ctx.p.primary : "transparent",
        opacity: off ? 0.5 : 1,
        transform: [{ scale: pressed ? 0.97 : 1 }],
      })}
    >
      <CardIcon name={block.icon} size={16} color={color} />
      <Text style={{ color, fontSize: 14, fontWeight: "600" }}>{text(ctx, block.label)}</Text>
    </Pressable>
  );
}

function RowNode(props: NodeProps) {
  return (
    <View style={{ flexDirection: row(props.ctx.rtl), flexWrap: "wrap", gap: 8 }}>
      <Children {...props} />
    </View>
  );
}

function Col(props: NodeProps) {
  return (
    <View style={{ gap: 12 }}>
      <Children {...props} />
    </View>
  );
}

function Grid({ block, path, ctx }: NodeProps) {
  const cols = block.cols === 1 || block.cols === 3 ? block.cols : 2;
  const children = (block.children as UiBlock[]) ?? [];
  const rows: UiBlock[][] = [];
  for (let at = 0; at < children.length; at += cols) rows.push(children.slice(at, at + cols));
  return (
    <View style={{ gap: 8 }}>
      {rows.map((cells, index) => (
        <View key={index} style={{ flexDirection: row(ctx.rtl), gap: 8 }}>
          {Array.from({ length: cols }, (_, column) => {
            const child = cells[column];
            const at = index * cols + column;
            return (
              <View key={column} style={{ flex: 1, minWidth: 0 }}>
                {child ? <Node block={child} path={`${path}.${at}`} ctx={ctx} /> : null}
              </View>
            );
          })}
        </View>
      ))}
    </View>
  );
}

function Card(props: NodeProps) {
  const { block, ctx } = props;
  return (
    <View style={{ gap: 10, padding: 12, borderRadius: 12, backgroundColor: ctx.p.raise }}>
      {block.title !== undefined ? (
        <View style={{ flexDirection: row(ctx.rtl), alignItems: "center", gap: 6 }}>
          <CardIcon name={block.icon} size={16} color={ctx.p.text} />
          <Text style={{ color: ctx.p.text, fontSize: 14, fontWeight: "700" }}>
            {text(ctx, block.title)}
          </Text>
        </View>
      ) : null}
      <Children {...props} />
    </View>
  );
}

function More(props: NodeProps) {
  const { block, ctx } = props;
  const [open, setOpen] = useState(false);
  if (!open)
    return (
      <Pressable
        accessibilityRole="button"
        onPress={() => setOpen(true)}
        style={{ alignSelf: ctx.rtl ? "flex-end" : "flex-start", paddingVertical: 4 }}
      >
        <Text
          style={{
            color: ctx.p.muted,
            fontSize: 14,
            fontWeight: "600",
            textDecorationLine: "underline",
          }}
        >
          {typeof block.label === "string" ? text(ctx, block.label) : ctx.t("uiShowMore")}
        </Text>
      </Pressable>
    );
  return <Col {...props} />;
}

function Divider({ ctx }: NodeProps) {
  return <View style={{ height: 1, backgroundColor: ctx.p.line }} />;
}

function Delivery({ block, ctx }: NodeProps) {
  const labels: Record<string, Label> = {
    app: "uiDeliveryApp",
    push: "uiDeliveryPush",
    call: "uiDeliveryCall",
  };
  return (
    <View style={{ gap: 6 }}>
      <FieldLabel label={ctx.t("uiDelivery")} ctx={ctx} />
      <View
        style={{ borderWidth: 1, borderColor: ctx.p.line, borderRadius: 12, overflow: "hidden" }}
      >
        {((block.channels as string[]) ?? []).map((channel, index) => (
          // A read-only checked pick row (Q59).
          <View
            key={channel}
            accessible
            accessibilityRole="checkbox"
            accessibilityState={{ checked: true, disabled: true }}
            style={{
              flexDirection: row(ctx.rtl),
              alignItems: "center",
              gap: 10,
              minHeight: 42,
              paddingHorizontal: 12,
              paddingVertical: 8,
              borderTopWidth: index ? 1 : 0,
              borderColor: ctx.p.line,
            }}
          >
            <View
              style={{
                width: 22,
                height: 22,
                borderRadius: 7,
                alignItems: "center",
                justifyContent: "center",
                backgroundColor: ctx.p.accent,
              }}
            >
              <CardIcon name="check" size={14} color={ctx.p.onAccent} />
            </View>
            <Text style={{ color: ctx.p.text, fontSize: 14, fontWeight: "600" }}>
              {ctx.t(labels[channel] ?? "uiDeliveryApp")}
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

/** Every node type of the catalog, and the server's delivery row. */
export const NODES: Record<UiRenderedNodeType, (props: NodeProps) => ReactNode> = {
  Segmented,
  Select,
  Number: NumberField,
  Slider,
  Text: TextNode,
  Title,
  Markdown: MarkdownNode,
  Note,
  Badge,
  KeyValue,
  Stat,
  Button,
  Divider,
  Row: RowNode,
  Col,
  Grid,
  Card,
  More,
  Delivery,
};
