// biome-ignore-all lint/suspicious/noArrayIndexKey: Immutable server documents give stateless text, plot geometry and table rows positional identity.
import type {
  RichContent,
  VisualAction,
  VisualDocument,
  VisualNode,
  VisualScalar,
  VisualState,
} from "@lonora/contracts";
import {
  evaluateVisualValue,
  expandVisualAction,
  filterVisualRows,
  initialVisualState,
  updateVisualState,
  validateRichContent,
  visualStateStorageKey,
} from "@lonora/core";
import { visual } from "@lonora/ui-tokens";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  AppState,
  Image,
  Platform,
  Pressable,
  ScrollView,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";
import { isImage, useArtifact } from "../lib/artifacts";
import { useSession } from "../lib/session";
import { loadVisualState, saveVisualState } from "../lib/visual-state";
import { Markdown } from "./markdown";
import { NativeVisualInput, NativeVisualSlider } from "./native-rich-controls";
import { NativeVisualChart, NativeVisualDiagram } from "./native-rich-graphics";
import { type NativeVisualPalette, useNativeVisualTheme, visualTone } from "./native-rich-theme";
import { NativeSymbol, type SymbolName } from "./native-symbol";

export type NativeVisualAction = (action: VisualAction) => void | Promise<void>;
type Props = {
  content: RichContent;
  messageId: string;
  threadId: string;
  onAction?: NativeVisualAction;
  onChartLink?: (url: string) => boolean;
};

function validatedParts(content: RichContent) {
  return validateRichContent(content)?.parts ?? [];
}

/** Only already compiled native documents can suppress duplicate file previews. */
export function nativeRichImageIds(content?: RichContent | null): Set<string> {
  const ids = new Set<string>();
  if (!content) return ids;
  for (const part of validatedParts(content)) {
    if (part.type !== "ui") continue;
    const walk = (node: VisualNode) => {
      if (node.type === "image" && node.artifact_id) ids.add(node.artifact_id);
      for (const child of node.children ?? []) walk(child);
    };
    walk(part.document.root);
  }
  return ids;
}

export function NativeRichResponse({ content, messageId, threadId, onAction, onChartLink }: Props) {
  const palette = useNativeVisualTheme();
  const parts = useMemo(() => validatedParts(content), [content]);
  const { rtl, t } = useSession();
  if (!parts.length)
    return <Text style={{ color: palette["muted-foreground"] }}>{t("visualUnavailable")}</Text>;
  return (
    <View
      testID="native-rich-response"
      style={{ gap: visual.space.normal, maxWidth: visual.contentWidth, width: "100%" }}
    >
      {parts.map((part, index) =>
        part.type === "text" ? (
          <View key={`text:${index}`} style={{ minWidth: 0 }}>
            <Markdown content={part.text} palette={palette} onChartLink={onChartLink} />
          </View>
        ) : (
          <NativeVisualDocument
            key={`ui:${index}:${part.document.root.id}`}
            document={part.document}
            messageId={messageId}
            threadId={threadId}
            palette={palette}
            onAction={onAction}
            rtl={rtl}
          />
        ),
      )}
    </View>
  );
}

type DocumentProps = {
  document: VisualDocument;
  messageId: string;
  threadId: string;
  palette: NativeVisualPalette;
  onAction?: NativeVisualAction;
  rtl: boolean;
};
function NativeVisualDocument({
  document,
  messageId,
  threadId,
  palette,
  onAction,
  rtl,
}: DocumentProps) {
  const { owner, server, locale, t, errorText } = useSession();
  const storageKey = useMemo(
    () =>
      visualStateStorageKey(
        `${server}|${owner?.id ?? "signed-out"}`,
        threadId,
        messageId,
        document,
      ),
    [document, messageId, owner?.id, server, threadId],
  );
  const [state, setState] = useState<VisualState>(() => initialVisualState(document));
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [hydrated, setHydrated] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latestDocument = useRef(document);
  latestDocument.current = document;
  const savedState = useRef({ storageKey, state, expanded, ready: false });
  savedState.current = {
    storageKey,
    state,
    expanded,
    ready: hydrated === storageKey && Boolean(owner),
  };
  useEffect(() => {
    let live = true;
    setState(initialVisualState(latestDocument.current));
    setExpanded({});
    setHydrated("");
    void loadVisualState(storageKey).then((saved) => {
      if (!live) return;
      setState(initialVisualState(latestDocument.current, saved?.state));
      setExpanded(saved?.expanded ?? {});
      setHydrated(storageKey);
    });
    return () => {
      live = false;
    };
  }, [storageKey]);
  useEffect(() => {
    if (hydrated !== storageKey || !owner) return;
    const timer = setTimeout(() => void saveVisualState(storageKey, { state, expanded }), 100);
    return () => clearTimeout(timer);
  }, [expanded, hydrated, owner, state, storageKey]);
  useEffect(() => {
    const flush = () => {
      const current = savedState.current;
      if (current.ready)
        void saveVisualState(current.storageKey, {
          state: current.state,
          expanded: current.expanded,
        });
    };
    const subscription = AppState.addEventListener("change", (status) => {
      if (status !== "active") flush();
    });
    if (Platform.OS === "web" && typeof window !== "undefined")
      window.addEventListener("pagehide", flush);
    return () => {
      flush();
      subscription.remove();
      if (Platform.OS === "web" && typeof window !== "undefined")
        window.removeEventListener("pagehide", flush);
    };
  }, []);
  const value = (raw: VisualNode["value"]) => evaluateVisualValue(raw, document, state);
  const print = (raw: VisualScalar) =>
    raw === null
      ? t("visualUnavailable")
      : typeof raw === "boolean"
        ? t(raw ? "visualTrue" : "visualFalse")
        : String(raw);
  const action = async (node: VisualNode) => {
    if (!node.action || pending) return;
    const next = expandVisualAction(node.action, document, state);
    if (!next || !onAction) {
      setError(t("visualActionUnavailable"));
      return;
    }
    setPending(node.id);
    setError(null);
    try {
      await onAction(next);
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setPending(null);
    }
  };
  const change = (node: VisualNode, next: VisualScalar) =>
    setState((old) => updateVisualState(document, old, node, next));
  const textStyle = {
    color: palette.foreground,
    fontSize: visual.font.body,
    lineHeight: visual.line.body,
    textAlign: rtl ? ("right" as const) : ("left" as const),
    writingDirection: "auto" as const,
  };
  const label = (text?: string | null) =>
    text ? (
      <Text style={{ ...textStyle, fontSize: visual.font.label, fontWeight: "600" }}>{text}</Text>
    ) : null;
  const frame = {
    backgroundColor: palette.card,
    borderColor: palette.border,
    borderWidth: visual.border,
    borderRadius: visual.radius.normal,
    padding: visual.space.normal,
  };
  const choiceStyle = (selected: boolean) => ({
    minHeight: visual.touch,
    paddingHorizontal: visual.space.normal,
    paddingVertical: visual.space.small,
    borderRadius: visual.radius.small,
    borderWidth: visual.border,
    borderColor: selected ? palette.link : palette.border,
    backgroundColor: selected ? palette.accent : palette.card,
    justifyContent: "center" as const,
  });
  const children = (node: VisualNode) =>
    (node.children ?? []).map((child) => (
      <View
        key={child.id}
        style={
          node.type === "row"
            ? { flexGrow: 1, flexBasis: visual.columnMinimum, minWidth: 0 }
            : undefined
        }
      >
        {render(child)}
      </View>
    ));
  const render = (node: VisualNode): ReactNode => {
    if (!evaluateVisualValue(node.visible ?? true, document, state)) return null;
    const color = visualTone(palette, node.tone);
    const gap = visual.space[node.gap ?? "normal"];
    switch (node.type) {
      case "text":
        return (
          <Text selectable style={{ ...textStyle, color }}>
            {node.text ?? print(value(node.value))}
          </Text>
        );
      case "heading":
        return (
          <Text
            accessibilityRole="header"
            selectable
            style={{
              ...textStyle,
              color,
              fontSize: visual.font.heading[(node.level ?? 2) - 1],
              fontWeight: "700",
              lineHeight: visual.font.heading[(node.level ?? 2) - 1] * 1.35,
            }}
          >
            {node.text ?? ""}
          </Text>
        );
      case "badge":
        return (
          <View
            style={{
              alignSelf: rtl ? "flex-end" : "flex-start",
              paddingHorizontal: visual.space.small,
              paddingVertical: 4,
              borderWidth: visual.border,
              borderColor: color,
              borderRadius: visual.radius.small,
            }}
          >
            <Text style={{ color, fontSize: visual.font.small }}>
              {node.text ?? print(value(node.value))}
            </Text>
          </View>
        );
      case "icon": {
        const allowed: SymbolName[] = [
          "call",
          "mic",
          "search",
          "activity",
          "layers",
          "plus",
          "back",
          "chevron",
          "chart",
          "send",
          "close",
          "file",
          "clock",
          "settings",
          "group",
          "agent",
          "download",
          "check",
          "stop",
          "refresh",
          "globe",
        ];
        return (
          <NativeSymbol
            name={
              allowed.includes(node.text as SymbolName) ? (node.text as SymbolName) : "activity"
            }
            size={24}
            color={color}
          />
        );
      }
      case "divider":
        return (
          <View
            style={{
              borderBottomWidth: visual.border,
              borderBottomColor: palette.border,
              marginVertical: visual.space.small,
            }}
          />
        );
      case "metric":
        return (
          <View style={{ ...frame, gap: visual.space.small }}>
            {label(node.label)}
            <Text
              selectable
              style={{
                color,
                fontSize: visual.font.metric,
                fontWeight: "700",
                textAlign: rtl ? "right" : "left",
              }}
            >
              {print(value(node.value))}
              {node.unit != null ? ` ${print(value(node.unit))}` : ""}
            </Text>
          </View>
        );
      case "column":
      case "container":
        return (
          <View style={{ gap }}>
            {label(node.label)}
            {children(node)}
          </View>
        );
      case "card":
      case "form":
        return (
          <View style={{ ...frame, gap }} accessibilityLabel={node.label ?? undefined}>
            {label(node.label)}
            {children(node)}
          </View>
        );
      case "row":
        return (
          <View style={{ flexDirection: rtl ? "row-reverse" : "row", flexWrap: "wrap", gap }}>
            {children(node)}
          </View>
        );
      case "grid":
        return (
          <View style={{ flexDirection: rtl ? "row-reverse" : "row", flexWrap: "wrap", gap }}>
            {(node.children ?? []).map((child) => (
              <View
                key={child.id}
                style={{
                  flexGrow: 1,
                  flexBasis: `${Math.floor(100 / (node.columns ?? 2)) - 4}%`,
                  minWidth: visual.columnMinimum,
                }}
              >
                {render(child)}
              </View>
            ))}
          </View>
        );
      case "list":
      case "timeline":
        return (
          <View style={{ gap }}>
            {label(node.label)}
            {(node.children ?? []).map((child, index) => (
              <View
                key={child.id}
                style={{ flexDirection: rtl ? "row-reverse" : "row", gap: visual.space.normal }}
              >
                <Text style={{ color: palette["muted-foreground"], fontSize: visual.font.body }}>
                  {node.type === "timeline" ? `${index + 1}` : "•"}
                </Text>
                <View style={{ flex: 1 }}>{render(child)}</View>
              </View>
            ))}
          </View>
        );
      case "progress": {
        const observed = value(node.value);
        const number = observed === null ? Number.NaN : Number(observed);
        const ratio =
          Number.isFinite(number) && (node.maximum ?? 100) > 0
            ? Math.max(0, Math.min(1, number / (node.maximum ?? 100)))
            : null;
        return (
          <View style={{ gap: visual.space.small }}>
            {label(node.label)}
            <Text style={{ ...textStyle, color }}>{print(observed)}</Text>
            {ratio !== null ? (
              <View
                accessibilityRole="progressbar"
                accessibilityValue={{ min: 0, max: node.maximum ?? 100, now: number }}
                style={{
                  height: 8,
                  backgroundColor: palette.border,
                  borderRadius: visual.radius.small,
                }}
              >
                <View
                  style={{
                    width: `${ratio * 100}%`,
                    height: 8,
                    backgroundColor: color,
                    borderRadius: visual.radius.small,
                  }}
                />
              </View>
            ) : null}
          </View>
        );
      }
      case "table": {
        const rows = filterVisualRows(node, document, state);
        return (
          <View style={{ gap: visual.space.small }}>
            {label(node.label)}
            {node.filter_key ? (
              <TextInput
                accessibilityLabel={`${t("visualFilter")} ${node.label ?? ""}`}
                value={String(state[node.filter_key] ?? "")}
                onChangeText={(next) => change(node, next)}
                placeholder={t("visualFilter")}
                placeholderTextColor={palette["muted-foreground"]}
                style={{
                  ...frame,
                  minHeight: visual.touch,
                  color: palette.foreground,
                  textAlign: rtl ? "right" : "left",
                }}
              />
            ) : null}
            <ScrollView
              horizontal
              nestedScrollEnabled
              contentContainerStyle={{ flexDirection: "column" }}
            >
              <View style={{ ...frame, padding: 0, overflow: "hidden" }}>
                <View
                  style={{
                    flexDirection: rtl ? "row-reverse" : "row",
                    backgroundColor: palette.accent,
                  }}
                >
                  {(node.fields ?? []).map((field) => (
                    <Text
                      key={field.key}
                      style={{
                        ...textStyle,
                        width: 145,
                        padding: visual.space.normal,
                        fontWeight: "600",
                      }}
                    >
                      {field.label}
                    </Text>
                  ))}
                </View>
                {rows.map((row, index) => (
                  <View
                    key={index}
                    style={{
                      flexDirection: rtl ? "row-reverse" : "row",
                      borderTopWidth: visual.border,
                      borderTopColor: palette.border,
                    }}
                  >
                    {(node.fields ?? []).map((field) => (
                      <Text
                        selectable
                        key={field.key}
                        style={{ ...textStyle, width: 145, padding: visual.space.normal }}
                      >
                        {print(value(row[field.key]))}
                      </Text>
                    ))}
                  </View>
                ))}
              </View>
            </ScrollView>
          </View>
        );
      }
      case "chart":
        return (
          <NativeVisualChart
            node={node}
            document={document}
            state={state}
            palette={palette}
            unavailable={t("visualUnavailable")}
          />
        );
      case "diagram":
        return (
          <NativeVisualDiagram
            node={node}
            palette={palette}
            unavailable={t("visualUnavailable")}
            rtl={rtl}
          />
        );
      case "image":
        return node.artifact_id ? (
          <NativeVisualImage
            id={node.artifact_id}
            label={node.label ?? undefined}
            palette={palette}
            onOpen={() =>
              void action({
                ...node,
                action: { kind: "open_artifact", resource_id: node.artifact_id as string },
              })
            }
          />
        ) : null;
      case "disclosure": {
        const open = expanded[node.id] ?? false;
        return (
          <View style={{ ...frame, gap: visual.space.small }}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={node.label ?? t("visualDetails")}
              accessibilityState={{ expanded: open }}
              aria-expanded={open}
              onPress={() => setExpanded((old) => ({ ...old, [node.id]: !open }))}
              style={{
                minHeight: visual.touch,
                flexDirection: rtl ? "row-reverse" : "row",
                alignItems: "center",
                justifyContent: "space-between",
                gap: visual.space.normal,
              }}
            >
              {label(node.label ?? t("visualDetails"))}
              <Text style={{ color: palette["muted-foreground"] }}>{open ? "−" : "+"}</Text>
            </Pressable>
            {open ? children(node) : null}
          </View>
        );
      }
      case "tabs":
      case "select": {
        const selected = String(state[node.state_key ?? ""] ?? node.options?.[0]?.value ?? "");
        const index = Math.max(
          0,
          (node.options ?? []).findIndex((option) => option.value === selected),
        );
        return (
          <View style={{ gap: visual.space.normal }}>
            {label(node.label)}
            <View
              accessibilityRole={node.type === "tabs" ? "tablist" : undefined}
              style={{
                flexDirection: rtl ? "row-reverse" : "row",
                flexWrap: "wrap",
                gap: visual.space.small,
              }}
            >
              {(node.options ?? []).map((option) => (
                <Pressable
                  key={option.value}
                  accessibilityRole={node.type === "tabs" ? "tab" : "radio"}
                  accessibilityLabel={option.label}
                  aria-selected={node.type === "tabs" ? option.value === selected : undefined}
                  aria-checked={node.type === "select" ? option.value === selected : undefined}
                  accessibilityState={{
                    selected: option.value === selected,
                    checked: option.value === selected,
                  }}
                  onPress={() => change(node, option.value)}
                  style={choiceStyle(option.value === selected)}
                >
                  <Text style={{ ...textStyle, fontSize: visual.font.label }}>{option.label}</Text>
                </Pressable>
              ))}
            </View>
            {node.type === "tabs" && node.children?.[index] ? render(node.children[index]) : null}
          </View>
        );
      }
      case "checkbox":
        return (
          <View
            style={{
              flexDirection: rtl ? "row-reverse" : "row",
              alignItems: "center",
              justifyContent: "space-between",
              gap: visual.space.normal,
            }}
          >
            {label(node.label)}
            <Switch
              accessibilityLabel={node.label ?? node.id}
              value={Boolean(state[node.state_key ?? ""])}
              aria-checked={Boolean(state[node.state_key ?? ""])}
              onValueChange={(next) => change(node, next)}
              trackColor={{ true: palette.link }}
            />
          </View>
        );
      case "input":
        return (
          <NativeVisualInput
            node={node}
            value={state[node.state_key ?? ""] ?? null}
            palette={palette}
            rtl={rtl}
            onChange={(next) => change(node, next)}
          />
        );
      case "slider":
        return (
          <NativeVisualSlider
            node={node}
            value={state[node.state_key ?? ""] ?? null}
            palette={palette}
            rtl={rtl}
            onChange={(next) => change(node, next)}
          />
        );
      case "button":
        return (
          <Pressable
            testID={`visual-action-${node.id}`}
            accessibilityRole="button"
            accessibilityLabel={node.label ?? ""}
            aria-disabled={pending !== null || !onAction}
            aria-busy={pending === node.id}
            accessibilityState={{
              disabled: pending !== null || !onAction,
              busy: pending === node.id,
            }}
            disabled={pending !== null || !onAction}
            onPress={() => void action(node)}
            style={({ pressed }) => ({
              ...choiceStyle(false),
              alignItems: "center",
              backgroundColor: palette.primary,
              opacity: pressed || pending ? 0.6 : 1,
            })}
          >
            {pending === node.id ? (
              <ActivityIndicator color={palette["primary-foreground"]} />
            ) : (
              <Text
                style={{
                  color: palette["primary-foreground"],
                  fontSize: visual.font.label,
                  fontWeight: "600",
                }}
              >
                {node.label}
              </Text>
            )}
          </Pressable>
        );
    }
  };
  const observed = [
    ...new Set(
      Object.values(document.facts ?? {})
        .map((fact) => fact.observed_at)
        .filter((value): value is string => Boolean(value)),
    ),
  ];
  return (
    <View
      testID={`native-visual-${document.root.id}`}
      style={{
        backgroundColor: palette.background,
        borderRadius: visual.radius.large,
        padding: visual.space.normal,
        gap: visual.space.normal,
      }}
    >
      {document.mode !== "observed" ? (
        <Text
          style={{
            color: document.mode === "estimate" ? palette.warning : palette["muted-foreground"],
            fontSize: visual.font.small,
            textAlign: rtl ? "right" : "left",
          }}
        >
          {t(document.mode === "example" ? "visualExample" : "visualEstimate")}
        </Text>
      ) : null}
      {render(document.root)}
      {observed.length ? (
        <View style={{ gap: visual.space.small }}>
          {observed.map((time) => (
            <Text
              key={time}
              style={{
                color: palette["muted-foreground"],
                fontSize: visual.font.small,
                textAlign: rtl ? "right" : "left",
              }}
            >
              {t("visualObservedAt")}:{" "}
              {Number.isFinite(Date.parse(time))
                ? new Date(time).toLocaleString(locale)
                : t("visualUnavailable")}
            </Text>
          ))}
        </View>
      ) : null}
      {error ? (
        <Text accessibilityRole="alert" style={{ color: palette.destructive }}>
          {error}
        </Text>
      ) : null}
    </View>
  );
}

function NativeVisualImage({
  id,
  label,
  palette,
  onOpen,
}: {
  id: string;
  label?: string;
  palette: NativeVisualPalette;
  onOpen: () => void;
}) {
  const { content, loading } = useArtifact(id);
  const { t } = useSession();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label ?? content?.artifact.payload.name ?? t("preview")}
      onPress={onOpen}
      style={{
        borderRadius: visual.radius.normal,
        overflow: "hidden",
        borderWidth: visual.border,
        borderColor: palette.border,
        backgroundColor: palette.card,
      }}
    >
      {content && isImage(content.mediaType) ? (
        <Image
          source={{ uri: content.uri }}
          accessibilityLabel={label ?? content.artifact.payload.name}
          resizeMode="contain"
          style={{ width: "100%", height: visual.chartHeight }}
        />
      ) : (
        <View style={{ minHeight: visual.touch, padding: visual.space.normal }}>
          {loading ? (
            <ActivityIndicator color={palette.foreground} />
          ) : (
            <Text style={{ color: palette["muted-foreground"] }}>{t("visualUnavailable")}</Text>
          )}
        </View>
      )}
      {label ? (
        <Text style={{ color: palette.foreground, padding: visual.space.normal }}>{label}</Text>
      ) : null}
    </Pressable>
  );
}
