/** lonora-ui v2 cards as stored and streamed (GENUI_PLAN §2.2, §9.1). Compiled by the server;
 * clients validate fail-closed with `packages/core/src/genui/spec.ts`. */
export type UiKind =
  | "calculator"
  | "form"
  | "picker"
  | "chart"
  | "choice"
  | "checklist"
  | "quiz"
  | "timer"
  | "diagram"
  | "receipt";
export type UiScalar = string | number | boolean | null;
export type UiOption =
  | UiScalar
  | { value: UiScalar; label?: string; also?: Record<string, UiScalar> };
export type UiAction =
  | { do: "send"; intent: string; data?: Record<string, unknown>; lock?: boolean }
  | { do: "go"; route: string }
  | { do: "set"; key: string; value: unknown }
  | { do: "toggle"; key: string }
  | { do: "reset" }
  | { do: "copy"; text: string }
  | { do: "open"; url: string };
export type UiBlock = {
  type: string;
  when?: unknown;
  [prop: string]: unknown;
};
export type UiFact = {
  value: unknown;
  source: string;
  observed_at?: string | null;
  account_id?: string | null;
};
export type UiDocument = {
  v: 2;
  kind: UiKind;
  title: string;
  sub?: string;
  icon: string;
  mode?: "observed" | "example" | "estimate";
  currency?: string;
  account_id?: string;
  agent_id?: string;
  facts: Record<string, UiFact>;
  state: Record<string, unknown>;
  /** Expressions, or literals (the reference's `uxExpr` returns non-strings as-is). */
  calc: Record<string, string | number | boolean | null>;
  blocks: UiBlock[];
  why?: string;
  fallback: string;
};
export type UiPart = { type: "ui"; document: UiDocument; building?: boolean; cut?: number };
/** `MessageCreate.ui_submit`: the server composes the bubble and computes the data. */
export type UiSubmitInput = {
  source_message_id: string;
  part: number;
  path: string;
  values: Record<string, unknown>;
};
/** What a client sees of a stored submission (`Message.ui_submit`). */
export type UiSubmitRecord = {
  source_message_id: string;
  part: number;
  intent: string;
  lock?: boolean;
  card_title?: string;
  run_id: string;
  started_at?: string;
  superseded_at?: string;
  /** The server's record that its Run ended without starting (rule N). */
  mark?: "superseded" | "not_run";
};
export type UiStatePart = { values?: Record<string, unknown>; fx?: unknown; unlocked_seq?: number };
export type UiState = { parts?: Record<string, UiStatePart>; updated_at?: string };
export type UiLock = { message_id: string; seq: number; agent_id: string | null };
