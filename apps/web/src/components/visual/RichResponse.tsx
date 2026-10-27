// biome-ignore-all lint/suspicious/noArrayIndexKey: Committed response parts and scalar rows are immutable and contain no per-row component state.
/** OpenUI-inspired native composition on Lonora's existing message/runtime boundary. */
import { useLingui } from "@lingui/react/macro";
import { ChatMarkdown } from "@lonora/chat-ui/web";
import type {
  VisualAction,
  VisualDocument,
  VisualNode,
  VisualScalar,
  VisualState,
  VisualValue,
} from "@lonora/contracts";
import {
  evaluateVisualValue,
  expandVisualAction,
  filterVisualRows,
  initialVisualState,
  updateVisualState,
  validateRichContent,
  visualDocumentKey,
  visualStateStorageKey,
} from "@lonora/core";
import { visual } from "@lonora/ui-tokens";
import {
  ArrowRight,
  Check,
  ChevronDown,
  Circle,
  Info,
  Minus,
  Plus,
  TrendingDown,
  TrendingUp,
  TriangleAlert,
  X,
} from "lucide-react";
import {
  type CSSProperties,
  type ReactNode,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import type { Resource } from "../../lib/api";
import { artifactUrl } from "../../lib/artifacts";
import { userError } from "../../lib/user_error";
import { VisualChart, VisualDiagram } from "./VisualGraphics";
import { VisualNumberInput } from "./VisualNumberInput";
import { VisualTable } from "./VisualTable";
import "./visual.css";

type Props = {
  content: unknown;
  fallback: string;
  ownerId: string;
  threadId: string;
  messageId: string;
  /** Exact prior preview identity, scoped to this owner/thread/document. */
  previousMessageId?: string;
  artifacts?: Resource[];
  onAction?: (action: VisualAction) => Promise<void>;
};

// Only renderer chrome is translated here; model-owned content retains its language.
function labels(arabic: boolean) {
  return arabic
    ? {
        unavailable: "غير متاح",
        example: "مثال توضيحي",
        estimate: "تقدير",
        filter: "تصفية",
        source: "المصادر",
        verified: "بيانات مؤكدة",
        error: "تعذر عرض هذا الجزء.",
        reset: "إعادة ضبط المدخلات",
        image: "صورة",
        working: "جارٍ الإرسال…",
        more: "عرض المزيد",
        less: "عرض أقل",
      }
    : {
        unavailable: "Unavailable",
        example: "Illustrative example",
        estimate: "Estimate",
        filter: "Filter",
        source: "Sources",
        verified: "Verified data",
        error: "This part could not be displayed.",
        reset: "Reset inputs",
        image: "Image",
        working: "Sending…",
        more: "Show more",
        less: "Show less",
      };
}

export function RichResponse(props: Props) {
  const rich = useMemo(() => validateRichContent(props.content), [props.content]);
  if (!rich) return <ChatMarkdown>{props.fallback}</ChatMarkdown>;
  return (
    <div className="native-rich-response" data-rich-response-version="1">
      {rich.parts.map((part, index) =>
        part.type === "text" ? (
          <div className="native-rich-text" key={`text:${index}`}>
            <ChatMarkdown>{part.text}</ChatMarkdown>
          </div>
        ) : (
          <VisualDocumentView
            key={`${index}:${visualDocumentKey(part.document)}`}
            {...props}
            document={part.document}
          />
        ),
      )}
    </div>
  );
}

export function VisualDocumentView({
  document,
  ownerId,
  threadId,
  messageId,
  previousMessageId,
  artifacts = [],
  onAction,
}: Omit<Props, "content" | "fallback"> & { document: VisualDocument }) {
  const { i18n } = useLingui();
  const instanceId = useId();
  const chrome = labels(i18n.locale.startsWith("ar"));
  const storageKey = useMemo(
    () => visualStateStorageKey(ownerId, threadId, messageId, document),
    [ownerId, threadId, messageId, document],
  );
  const previousStorageKey = previousMessageId
    ? visualStateStorageKey(ownerId, threadId, previousMessageId, document)
    : null;
  const formatter = useMemo(
    () => new Intl.NumberFormat(i18n.locale, { maximumFractionDigits: 8 }),
    [i18n.locale],
  );
  const [initial] = useState(() => {
    try {
      const canonical = localStorage.getItem(storageKey);
      const prior =
        canonical ?? (previousStorageKey ? localStorage.getItem(previousStorageKey) : null);
      return {
        state: initialVisualState(document, JSON.parse(prior ?? "null")),
        canonical: canonical !== null,
      };
    } catch {
      return { state: initialVisualState(document), canonical: false };
    }
  });
  const [state, setState] = useState<VisualState>(initial.state);
  const userEdited = useRef(false);
  const migratedFrom = useRef(previousStorageKey);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    // A canonical message may arrive before its run links it to the preview.
    // Restore only that exact document, and never overwrite edits made here.
    if (
      !previousStorageKey ||
      migratedFrom.current === previousStorageKey ||
      initial.canonical ||
      userEdited.current
    )
      return;
    migratedFrom.current = previousStorageKey;
    try {
      const prior = localStorage.getItem(previousStorageKey);
      if (prior !== null) setState(initialVisualState(document, JSON.parse(prior)));
    } catch {
      /* The answer remains usable when local storage is unavailable. */
    }
  }, [previousStorageKey, document, initial.canonical]);
  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(state));
    } catch {
      /* Storage denial does not disable the UI. */
    }
  }, [state, storageKey]);
  const value = (item: VisualValue | undefined) => evaluateVisualValue(item, document, state);
  const display = (item: VisualValue | undefined) => {
    const evaluated = value(item);
    return evaluated === null
      ? chrome.unavailable
      : typeof evaluated === "number"
        ? formatter.format(evaluated)
        : String(evaluated);
  };
  const change = (node: VisualNode, next: VisualScalar) => {
    userEdited.current = true;
    setState((old) => updateVisualState(document, old, node, next));
  };
  async function act(node: VisualNode) {
    if (!node.action || busy) return;
    const action = expandVisualAction(node.action, document, state);
    if (!action || !onAction) {
      setError(new Error("visual_action_unavailable"));
      return;
    }
    setBusy(node.id);
    setError(undefined);
    try {
      await onAction(action);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(null);
    }
  }
  function render(node: VisualNode): ReactNode {
    if (node.visible !== undefined && !value(node.visible)) return null;
    const children = () =>
      (node.children ?? []).map((child) => (
        <div className="native-visual-child" key={child.id}>
          {render(child)}
        </div>
      ));
    const title = node.label ? <div className="native-visual-label">{node.label}</div> : null;
    const fieldId = `${messageId}:${instanceId}:${node.id}`;
    const tone = `native-visual-tone-${node.tone ?? "neutral"}`;
    const className = `native-visual-node native-visual-${node.type} ${tone}`;
    const stateValue = node.state_key ? state[node.state_key] : null;
    const styles = {
      "--visual-gap": `${visual.space[node.gap ?? "normal"]}px`,
      "--visual-columns": node.columns ?? 2,
    } as CSSProperties;
    switch (node.type) {
      case "column":
      case "row":
      case "grid":
      case "card":
      case "container":
        return (
          <section className={className} style={styles} data-visual-node={node.id}>
            {title}
            {children()}
          </section>
        );
      case "form":
        return (
          <fieldset className={className} style={styles}>
            {node.label && <legend>{node.label}</legend>}
            {children()}
          </fieldset>
        );
      case "divider":
        return <hr className={className} />;
      case "text":
        return (
          <div className={className}>
            {node.text != null ? <ChatMarkdown>{node.text}</ChatMarkdown> : display(node.value)}
          </div>
        );
      case "heading": {
        const content = node.text ?? "";
        if (node.level === 1) return <h2 className={className}>{content}</h2>;
        if (node.level === 3) return <h4 className={className}>{content}</h4>;
        if (node.level === 4) return <h5 className={className}>{content}</h5>;
        return <h3 className={className}>{content}</h3>;
      }
      case "badge":
        return <span className={className}>{node.text ?? display(node.value)}</span>;
      case "icon": {
        const Icon =
          (
            {
              check: Check,
              info: Info,
              warning: TriangleAlert,
              up: TrendingUp,
              down: TrendingDown,
              arrow: ArrowRight,
              plus: Plus,
              minus: Minus,
              close: X,
              expand: ChevronDown,
            } as Record<string, typeof Info>
          )[node.text ?? ""] ?? Circle;
        return (
          <Icon
            className={className}
            size={20}
            aria-label={node.text ?? undefined}
            aria-hidden={!node.text}
          />
        );
      }
      case "metric":
        return (
          <dl className={className}>
            {node.label && <dt>{node.label}</dt>}
            <dd>
              <bdi data-visual-value={node.id}>{display(node.value)}</bdi>
              {node.unit != null && (
                <small>
                  <bdi>{display(node.unit)}</bdi>
                </small>
              )}
            </dd>
          </dl>
        );
      case "list":
        return (
          <section className={className}>
            {title}
            <ul>
              {(node.children ?? []).map((child) => (
                <li key={child.id}>{render(child)}</li>
              ))}
            </ul>
          </section>
        );
      case "timeline":
        return (
          <section className={className}>
            {title}
            <ol>
              {(node.children ?? []).map((child) => (
                <li key={child.id}>{render(child)}</li>
              ))}
            </ol>
          </section>
        );
      case "progress": {
        const current = value(node.value),
          maximum = node.maximum ?? 100;
        return (
          <div className={className}>
            {title}
            {typeof current === "number" && maximum > 0 ? (
              <progress
                aria-label={node.label ?? node.id}
                max={maximum}
                value={Math.min(maximum, Math.max(0, current))}
              />
            ) : (
              <span>{chrome.unavailable}</span>
            )}
            <output>{display(node.value)}</output>
          </div>
        );
      }
      case "table": {
        const rows = filterVisualRows(node, document, state);
        return (
          <VisualTable
            node={node}
            fieldId={fieldId}
            rows={rows}
            display={display}
            numeric={(item) => typeof value(item) === "number"}
            filter={String(state[node.filter_key ?? ""] ?? "")}
            onFilter={(next) => change(node, next)}
            labels={chrome}
          />
        );
      }
      case "chart":
        return (
          <VisualChart
            node={node}
            unavailable={chrome.unavailable}
            formatValue={(number) =>
              number === null ? chrome.unavailable : formatter.format(number)
            }
            moreLabel={chrome.more}
            points={(node.points ?? []).map((point) => {
              const number = value(point.value);
              return {
                label: display(point.label),
                value: typeof number === "number" ? number : null,
              };
            })}
          />
        );
      case "diagram":
        return <VisualDiagram node={node} />;
      case "image": {
        const artifact = artifacts.find((item) => item.id === node.artifact_id);
        return (
          <figure className={className}>
            <img
              src={artifactUrl(node.artifact_id ?? "", true)}
              alt={node.label ?? String(artifact?.payload.name ?? chrome.image)}
              loading="lazy"
              decoding="async"
            />
            {node.label && <figcaption>{node.label}</figcaption>}
          </figure>
        );
      }
      case "disclosure":
        return (
          <details className={className}>
            <summary>{node.label ?? chrome.source}</summary>
            <div>{children()}</div>
          </details>
        );
      case "tabs": {
        const selected = (node.options ?? []).findIndex((option) => option.value === stateValue);
        return (
          <section className={className}>
            <div role="tablist">
              {(node.options ?? []).map((option, index) => (
                <button
                  type="button"
                  role="tab"
                  id={`${fieldId}:tab:${index}`}
                  aria-controls={`${fieldId}:panel:${index}`}
                  aria-selected={selected === index}
                  tabIndex={selected === index ? 0 : -1}
                  key={option.value}
                  onKeyDown={(event) => {
                    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
                    event.preventDefault();
                    const length = node.options?.length ?? 0;
                    const direction = i18n.locale.startsWith("ar") ? -1 : 1;
                    const next =
                      event.key === "Home"
                        ? 0
                        : event.key === "End"
                          ? length - 1
                          : (index +
                              (event.key === "ArrowRight" ? direction : -direction) +
                              length) %
                            length;
                    change(node, node.options?.[next]?.value ?? "");
                    globalThis.document.getElementById(`${fieldId}:tab:${next}`)?.focus();
                  }}
                  onClick={() => change(node, option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
            {(node.children ?? []).map((child, index) => (
              <div
                key={child.id}
                role="tabpanel"
                id={`${fieldId}:panel:${index}`}
                aria-labelledby={`${fieldId}:tab:${index}`}
                hidden={selected !== index}
              >
                {render(child)}
              </div>
            ))}
          </section>
        );
      }
      case "button":
        return (
          <button
            type="button"
            className={className}
            disabled={busy !== null || !onAction}
            aria-busy={busy === node.id}
            onClick={() => void act(node)}
          >
            {busy === node.id ? chrome.working : node.label}
          </button>
        );
      case "select":
        return (
          <label className={className} htmlFor={fieldId}>
            {title}
            <select
              id={fieldId}
              value={String(stateValue ?? "")}
              onChange={(event) => change(node, event.target.value)}
            >
              {(node.options ?? []).map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        );
      case "checkbox":
        return (
          <label className={className} htmlFor={fieldId}>
            <input
              id={fieldId}
              type="checkbox"
              checked={Boolean(stateValue)}
              onChange={(event) => change(node, event.target.checked)}
            />
            <span>{node.label}</span>
          </label>
        );
      case "slider":
        return (
          <label className={className} htmlFor={fieldId}>
            {title}
            <div>
              <input
                id={fieldId}
                type="range"
                min={node.minimum ?? 0}
                max={node.maximum ?? 100}
                step={node.step ?? 1}
                value={typeof stateValue === "number" ? stateValue : (node.minimum ?? 0)}
                onChange={(event) => change(node, Number(event.target.value))}
              />
              <output htmlFor={fieldId}>
                {display(node.state_key ? { state: node.state_key } : null)}
              </output>
            </div>
          </label>
        );
      case "input":
        return (
          <label className={className} htmlFor={fieldId}>
            {title}
            {node.input_kind === "number" ? (
              <VisualNumberInput
                id={fieldId}
                node={node}
                value={stateValue}
                onChange={(next) => change(node, next)}
              />
            ) : (
              <input
                id={fieldId}
                type="text"
                maxLength={2000}
                value={stateValue === null ? "" : String(stateValue)}
                onChange={(event) => change(node, event.target.value)}
              />
            )}
          </label>
        );
    }
  }
  const facts = Object.values(document.facts ?? {});
  const style = {
    "--visual-space": `${visual.space.normal}px`,
    "--visual-radius": `${visual.radius.normal}px`,
    "--visual-touch": `${visual.touch}px`,
    "--visual-panel-padding": `${visual.panelPadding}px`,
    "--visual-body-font": `${visual.font.body}px`,
    "--visual-label-font": `${visual.font.label}px`,
    "--visual-small-font": `${visual.font.small}px`,
    "--visual-control-font": `${visual.controlFont}px`,
    "--visual-body-line": `${visual.line.body}px`,
    "--visual-heading-1": `${visual.font.heading[0]}px`,
    "--visual-heading-2": `${visual.font.heading[1]}px`,
    "--visual-heading-3": `${visual.font.heading[2]}px`,
    "--visual-heading-4": `${visual.font.heading[3]}px`,
    "--visual-metric-font": `${visual.font.metric}px`,
    "--visual-column-minimum": `${visual.columnMinimum}px`,
  } as CSSProperties;
  return (
    <section
      className="native-visual-response"
      data-visual-document={document.root.id}
      data-visual-mode={document.mode}
      style={style}
      dir="auto"
    >
      {document.mode !== "observed" && (
        <p className="native-visual-mode">
          {document.mode === "example" ? chrome.example : chrome.estimate}
        </p>
      )}
      {render(document.root)}
      {error != null && (
        <p className="native-visual-error" role="alert">
          {userError(error)}
        </p>
      )}
      {facts.length > 0 && (
        <details className="native-visual-provenance">
          <summary>{chrome.source}</summary>
          <ul>
            {facts.map((fact, index) => (
              <li key={index}>
                <bdi>{chrome.verified}</bdi>
                {fact.observed_at && (
                  <>
                    {" "}
                    ·{" "}
                    <time dateTime={fact.observed_at}>
                      {new Date(fact.observed_at).toLocaleString(i18n.locale)}
                    </time>
                  </>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
      {Object.keys(document.state ?? {}).length > 0 && (
        <button
          type="button"
          className="native-visual-reset"
          onClick={() => {
            userEdited.current = true;
            setState(initialVisualState(document));
          }}
        >
          {chrome.reset}
        </button>
      )}
    </section>
  );
}
