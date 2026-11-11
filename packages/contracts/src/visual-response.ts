import type { UiPart } from "./genui";
/** Native, declarative response vocabulary. It never carries executable code. */
export type VisualScalar = string | number | boolean | null;
export type VisualOperator =
  | "add"
  | "sub"
  | "mul"
  | "div"
  | "min"
  | "max"
  | "round"
  | "abs"
  | "eq"
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "and"
  | "or"
  | "not"
  | "if"
  | "floor"
  | "ceil"
  | "pow"
  | "sqrt"
  | "clamp"
  | "percent"
  | "change"
  | "concat";
export type VisualValue =
  | VisualScalar
  | { state: string }
  | { source: string }
  | { op: VisualOperator; args: VisualValue[] };
/** Fact references exist only while the server compiles a model draft. */
export type VisualDraftValue = VisualValue | { fact: { call_id: string; path: string } };
export type VisualNodeKind =
  | "column"
  | "row"
  | "grid"
  | "card"
  | "container"
  | "divider"
  | "text"
  | "heading"
  | "badge"
  | "icon"
  | "metric"
  | "table"
  | "list"
  | "progress"
  | "timeline"
  | "diagram"
  | "chart"
  | "image"
  | "disclosure"
  | "tabs"
  | "button"
  | "select"
  | "checkbox"
  | "slider"
  | "input"
  | "form";
export type VisualAction =
  | { kind: "follow_up"; text: string; resource_id?: null }
  | { kind: "open_chart" | "open_artifact"; resource_id: string; text?: null };
export type VisualChoice = { value: string; label: string };
export type VisualField = { key: string; label: string };
export type VisualNode = {
  id: string;
  type: VisualNodeKind;
  visible?: VisualValue;
  tone?: "neutral" | "info" | "success" | "warning" | "danger";
  children?: VisualNode[];
  text?: string | null;
  label?: string | null;
  value?: VisualValue;
  unit?: VisualValue;
  gap?: "small" | "normal" | "large";
  level?: number;
  columns?: number;
  fields?: VisualField[];
  rows?: Record<string, VisualValue>[];
  filter_key?: string | null;
  chart_kind?: "line" | "bar" | "pie";
  points?: { label: VisualValue; value: VisualValue }[];
  vertices?: { id: string; label: string }[];
  edges?: { source: string; target: string; label?: string }[];
  options?: VisualChoice[];
  state_key?: string | null;
  minimum?: number;
  maximum?: number;
  step?: number;
  input_kind?: "text" | "number";
  artifact_id?: string | null;
  action?: VisualAction | null;
};
export type VisualState = Record<string, VisualScalar>;
export type VisualFact = { value: VisualScalar; source: string; observed_at?: string | null };
export type VisualDocument = {
  version: 1;
  mode: "observed" | "example" | "estimate";
  root: VisualNode;
  state?: VisualState;
  facts?: Record<string, VisualFact>;
};
/** An owner voice note (server-written): the transcript is the message's content. */
export type VoiceTranscriptStatus = "pending" | "done" | "failed";
export type VoicePart = {
  type: "voice";
  artifact_id: string;
  /** Seconds, 0 < duration <= 120. */
  duration: number;
  /** Exactly 44 bars, each 0..100. */
  peaks: number[];
  transcript_status: VoiceTranscriptStatus;
};
/** A call log bubble (server-written system message). */
export type CallPart = {
  type: "call";
  direction: "outgoing" | "incoming";
  duration_seconds: number;
  missed: boolean;
};
export type VisualResponsePart =
  | { type: "text"; text: string }
  | { type: "ui"; document: VisualDocument }
  | UiPart
  | VoicePart
  | CallPart;
export type RichContent = { version: 1; parts: VisualResponsePart[] };
