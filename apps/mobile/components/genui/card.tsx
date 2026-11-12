/** A lonora-ui v2 card on mobile, natively (mandate 10.1.5): the twin of the web `UiCard`.
 * The server compiled and checked it; this renders it with the same core evaluator, keeps its
 * values, and sends through `MessageCreate.ui_submit` only: the server writes the owner's
 * bubble and data. While the card builds, and until its message is committed, every control
 * is disabled. While it is locked only go, open and copy stay enabled. */
import type { UiActionKind, UiBlock, UiPart, UiRoute } from "@lonora/contracts";
import { cardLock, environment, evaluate, renderTemplate, sendBlocked } from "@lonora/core";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Clipboard,
  Linking,
  Platform,
  Pressable,
  Text,
  type TextInput,
  Vibration,
  View,
} from "react-native";
import { api } from "../../lib/api";
import { fill } from "../../lib/i18n";
import { useSession } from "../../lib/session";
import { useCardHost } from "./host";
import { buttonOff, type CardCtx, CardIcon, Node, visible } from "./nodes";
import { useCardPalette } from "./theme";

/** The server's routes on mobile's own screens. */
const ROUTES: Record<UiRoute, string> = {
  market: "/charts",
  tasks: "/tasks",
  schedules: "/routine",
  usage: "/account",
  files: "/artifacts",
  agents: "/agents",
};
const STALE_MS = 120_000;

type Values = Record<string, unknown>;

/** Android only: iOS plays a full system buzz for every duration (docs/genui.md). */
function tick(ms: number) {
  if (Platform.OS === "android") Vibration.vibrate(ms);
}

function requiredMissing(blocks: UiBlock[], ctx: CardCtx): UiBlock | null {
  for (const block of blocks) {
    if (!visible(block, ctx)) continue;
    if (block.required && [null, undefined, ""].includes(ctx.values[String(block.bind)] as never))
      return block;
    if (Array.isArray(block.children)) {
      const missing = requiredMissing(block.children as UiBlock[], ctx);
      if (missing) return missing;
    }
  }
  return null;
}

function nonce(): string {
  const random = globalThis.crypto?.randomUUID?.();
  if (random) return random;
  return `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`;
}

export function NativeUiCard({
  part,
  index,
  messageId,
  threadId,
}: {
  part: UiPart;
  index: number;
  messageId: string;
  threadId: string;
}) {
  const { rtl, locale, t, errorText } = useSession();
  const router = useRouter();
  const p = useCardPalette();
  const host = useCardHost();
  const doc = part.document;
  const message = host?.messages.find((item) => item.id === messageId);
  const saved = message?.ui_state?.parts?.[String(index)]?.values;
  const [values, setValues] = useState<Values>(() => ({ ...doc.state, ...(saved ?? {}) }));
  const [whyOpen, setWhyOpen] = useState(false);
  const [invalid, setInvalid] = useState<string | null>(null);
  const [unreadable, setUnreadable] = useState<ReadonlySet<string>>(() => new Set());
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
  const inputs = useRef(new Map<string, TextInput>());
  const toast = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (toast.current) clearTimeout(toast.current);
    },
    [],
  );
  const committed = !messageId.startsWith("preview:");
  const building = Boolean(part.building);
  const facts = useMemo(
    () => Object.fromEntries(Object.entries(doc.facts).map(([key, fact]) => [key, fact.value])),
    [doc.facts],
  );
  const env = useMemo(
    () =>
      environment(doc.state, doc.calc, facts, values, {
        currency: doc.currency ?? null,
        language: locale === "en" ? "en" : "ar",
      }),
    [doc, facts, values, locale],
  );
  const lock = message && host ? cardLock(message, index, host.messages) : null;
  const awaiting =
    sentHere !== null && !host?.messages.some((item) => item.client_nonce === sentHere);
  const locked = Boolean(lock) || awaiting;
  const agentId = message?.agent_id ?? doc.agent_id ?? null;
  const agent = host?.agents.find((item) => item.id === agentId);
  const blocked = host
    ? sendBlocked(agentId, threadId, host.messages, host.runs, Boolean(agent?.paused))
    : null;
  const oldest = Math.min(
    ...Object.values(doc.facts)
      .map((fact) => (fact.observed_at ? Date.parse(fact.observed_at) : Number.NaN))
      .filter(Number.isFinite),
  );
  const clock = (at: number) =>
    new Date(at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  const stale = (text: string) => {
    // «الآن» over a fact older than 120 s becomes «آخر تحديث HH:MM» (§9.6).
    if (!Number.isFinite(oldest) || Date.now() - oldest <= STALE_MS) return text;
    return text.replace(/^(الآن|now)(?=[\s:،,.]|$)/iu, `${t("uiLastUpdated")} ${clock(oldest)}`);
  };

  function checkRequired(): boolean {
    const missing = requiredMissing(doc.blocks, ctx);
    if (!missing) return true;
    const key = String(missing.bind);
    setInvalid(key);
    setNotice(fill(t("uiCompleteFirst"), renderTemplate(String(missing.label), env)));
    inputs.current.get(key)?.focus();
    return false;
  }

  async function send(block: UiBlock, path: string) {
    if (!host || !checkRequired() || sending || unreadable.size > 0) return;
    setSending(true);
    setNotice(null);
    const id = nonce();
    try {
      tick(8);
      await host.submit({
        content: "",
        client_nonce: id,
        ui_submit: { source_message_id: messageId, part: index, path, values },
      });
      const action = block.action as { lock?: boolean } | undefined;
      // Locked at once; the submission's own message then carries the lock (§8.2).
      if (action?.lock !== false) setSentHere(id);
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setSending(false);
    }
  }

  function flash(text: string) {
    setNotice(text);
    if (toast.current) clearTimeout(toast.current);
    toast.current = setTimeout(() => setNotice((now) => (now === text ? null : now)), 1600);
  }

  const primaries = useRef(new Map<string, UiBlock>());
  const primaryAt = useCallback((path: string, block: UiBlock | null) => {
    if (block) primaries.current.set(path, block);
    else primaries.current.delete(path);
  }, []);
  /** The first rendered primary Button in reading order, as web's DOM query finds it. */
  const primary = (): [UiBlock, string] | null => {
    const order = (path: string) => path.split(".").map(Number);
    const paths = [...primaries.current.keys()].sort((a, b) => {
      const [x, y] = [order(a), order(b)];
      for (let at = 0; at < Math.max(x.length, y.length); at += 1)
        if ((x[at] ?? -1) !== (y[at] ?? -1)) return (x[at] ?? -1) - (y[at] ?? -1);
      return 0;
    });
    const path = paths[0];
    const block = path === undefined ? undefined : primaries.current.get(path);
    return block && path !== undefined ? [block, path] : null;
  };

  const ctx: CardCtx = {
    env,
    values,
    locked,
    frozen: building || !committed || sending,
    invalid,
    sendOff: Boolean(blocked) || unreadable.size > 0 || !host,
    rtl,
    p,
    t,
    stale,
    pick(key, value, also) {
      if (locked) return;
      tick(6);
      setValues((old) => ({ ...old, [key]: value, ...(also ?? {}) }));
      if (also && Object.hasOwn(also, invalid ?? "")) setInvalid(null);
    },
    type(key, value) {
      setValues((old) => ({ ...old, [key]: value }));
      if (invalid === key) setInvalid(null);
    },
    unreadable: markUnreadable,
    register(key, input) {
      if (input) inputs.current.set(key, input);
      else inputs.current.delete(key);
    },
    primaryAt,
    submitPrimary() {
      const found = primary();
      if (found && !buttonOff(found[0], ctx)) ctx.act(found[0], found[1]);
      else checkRequired();
    },
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
          if (Object.hasOwn(ROUTES, name)) router.push(ROUTES[name as UiRoute] as never);
          break;
        }
        case "open": {
          // A literal https URL the server matched to the owner's message or a tool result.
          const url = String(action?.url);
          if (url.startsWith("https://")) void Linking.openURL(url).catch(() => undefined);
          break;
        }
        case "copy":
          Clipboard.setString(renderTemplate(String(action?.text ?? ""), env));
          tick(8);
          flash(t("uiCopied"));
          break;
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
      await api.post(`/threads/${threadId}/messages/${messageId}/ui-state/${index}/unlock`, {});
      setSentHere(null);
      setNotice(t("uiEditThenSend"));
    } catch (error) {
      setNotice(errorText(error));
    }
  }

  const title = renderTemplate(doc.title, env);
  const direction = rtl ? ("row-reverse" as const) : ("row" as const);
  // Stopped before any block was built: no card, its fallback text (review E2).
  if (part.cut === 0)
    return <Text style={{ color: p.text, fontSize: 14, lineHeight: 22 }}>{doc.fallback}</Text>;
  const showFoot = !building && (locked || doc.why || part.cut !== undefined);
  const sources = Object.values(doc.facts).filter((fact) => fact.value !== null);
  return (
    <View
      testID="ux-card"
      accessibilityLabel={title || t("uiCard")}
      accessibilityState={{ busy: building }}
      style={{
        marginTop: 8,
        marginBottom: 2,
        borderRadius: 16,
        borderWidth: 1,
        borderColor: p.line,
        backgroundColor: p.card,
        overflow: "hidden",
      }}
    >
      <View
        style={{
          flexDirection: direction,
          alignItems: "center",
          gap: 10,
          paddingTop: 12,
          paddingHorizontal: 12,
          paddingBottom: 2,
        }}
      >
        {doc.icon ? (
          <View
            style={{
              width: 34,
              height: 34,
              borderRadius: 11,
              alignItems: "center",
              justifyContent: "center",
              backgroundColor: p.iconTile,
            }}
          >
            <CardIcon name={doc.icon} size={19} color={p.accentInk} />
          </View>
        ) : null}
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text
            accessibilityRole="header"
            style={{
              color: p.text,
              fontSize: 15,
              fontWeight: "700",
              lineHeight: 20,
              textAlign: rtl ? "right" : "left",
            }}
          >
            {title}
          </Text>
          {doc.sub ? (
            <Text style={{ color: p.muted, fontSize: 12, textAlign: rtl ? "right" : "left" }}>
              {renderTemplate(doc.sub, env)}
            </Text>
          ) : null}
        </View>
      </View>
      <View
        style={{
          gap: 14,
          paddingTop: 10,
          paddingHorizontal: 12,
          paddingBottom: 12,
          opacity: locked ? 0.82 : 1,
        }}
      >
        {doc.blocks.map((block, position) =>
          part.cut !== undefined && position >= part.cut ? null : (
            // biome-ignore lint/suspicious/noArrayIndexKey: blocks are positional and append-only
            <Node key={position} block={block} path={String(position)} ctx={ctx} />
          ),
        )}
        {building ? (
          <View testID="ux-skeleton" style={{ gap: 8, paddingVertical: 2 }}>
            <View style={{ height: 13, borderRadius: 7, backgroundColor: p.track }} />
            <View style={{ height: 13, width: "62%", borderRadius: 7, backgroundColor: p.track }} />
          </View>
        ) : null}
      </View>
      {notice ? (
        <Text
          accessibilityRole="alert"
          style={{ color: p.amber, fontSize: 13, paddingHorizontal: 12, paddingBottom: 10 }}
        >
          {notice}
        </Text>
      ) : null}
      {showFoot ? (
        <View
          style={{
            flexDirection: direction,
            flexWrap: "wrap",
            alignItems: "center",
            columnGap: 12,
            rowGap: 6,
            paddingVertical: 7,
            paddingHorizontal: 12,
            borderTopWidth: 1,
            borderColor: p.line,
          }}
        >
          {locked ? (
            <>
              <View style={{ flexDirection: direction, alignItems: "center", gap: 5 }}>
                <CardIcon name="checks" size={15} color={p.accentInk} />
                <Text
                  testID="ux-sent"
                  style={{ color: p.accentInk, fontSize: 12, fontWeight: "600" }}
                >
                  {fill(t("uiSentTo"), agent?.name ?? "Lonora")}
                </Text>
              </View>
              <Pressable accessibilityRole="button" onPress={() => void unlock()} hitSlop={8}>
                <Text
                  style={{
                    color: p.text,
                    fontSize: 12,
                    fontWeight: "600",
                    textDecorationLine: "underline",
                  }}
                >
                  {t("uiEdit")}
                </Text>
              </Pressable>
            </>
          ) : null}
          {part.cut !== undefined ? (
            <View style={{ flexDirection: direction, alignItems: "center", gap: 5 }}>
              <CardIcon name="stop" size={15} color={p.muted} />
              <Text style={{ color: p.muted, fontSize: 12, fontWeight: "500" }}>{t("uiCut")}</Text>
            </View>
          ) : null}
          {doc.why ? (
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ expanded: whyOpen }}
              onPress={() => setWhyOpen((open) => !open)}
              hitSlop={8}
              style={{
                flexDirection: direction,
                alignItems: "center",
                gap: 5,
                [rtl ? "marginRight" : "marginLeft"]: "auto",
              }}
            >
              <CardIcon name="sparkle" size={14} color={p.accentInk} />
              <Text style={{ color: whyOpen ? p.text : p.muted, fontSize: 12 }}>{t("uiWhy")}</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}
      {showFoot && doc.why && whyOpen ? (
        <View style={{ paddingHorizontal: 12, paddingBottom: 12, gap: 4 }}>
          <Text style={{ color: p.muted, fontSize: 13, lineHeight: 21 }}>{doc.why}</Text>
          {/* When the card's facts were read; never the tools' internal names (mandate 17). */}
          {sources.length > 0 && Number.isFinite(oldest) ? (
            <Text style={{ color: p.faint, fontSize: 12 }}>
              {t("uiLastUpdated")} {clock(oldest)}
            </Text>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}
