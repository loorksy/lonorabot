/** The lonora-ui v2 component catalog (mandate 10.1.5), generated from the server
 * contract `lonora_contracts.genui` by `scripts/export_genui_catalog.py`. Do not edit:
 * the client validator and both renderers type against it, so they accept exactly
 * the node types and actions the server accepts. */
export const UI_NODE_TYPES = [
  "Segmented",
  "Select",
  "Number",
  "Slider",
  "Text",
  "Title",
  "Markdown",
  "Note",
  "Badge",
  "KeyValue",
  "Stat",
  "Button",
  "Divider",
  "Row",
  "Col",
  "Grid",
  "Card",
  "More",
  "Slot",
] as const;
export type UiNodeType = (typeof UI_NODE_TYPES)[number];
/** Rows only the server writes into a compiled card (never taught to the model). */
export const UI_SERVER_NODE_TYPES = ["Delivery"] as const;
export type UiServerNodeType = (typeof UI_SERVER_NODE_TYPES)[number];
export type UiRenderedNodeType = UiNodeType | UiServerNodeType;
export const UI_ACTIONS = ["set", "toggle", "reset", "copy", "open", "go", "send"] as const;
export type UiActionKind = (typeof UI_ACTIONS)[number];
/** The client routes a `go` action may name (`lonora_agent.genui_capabilities`). */
export const UI_ROUTES = ["market", "tasks", "usage", "files", "agents"] as const;
export type UiRoute = (typeof UI_ROUTES)[number];
export const UI_TONES = ["info", "good", "warn", "bad", "muted", "accent"] as const;
/** The fixed cards a Slot may place (mandate 10.2); the client draws them from the
 * live record. */
export const UI_SLOT_CARDS = ["trade_approval", "settle"] as const;
export type UiSlotCard = (typeof UI_SLOT_CARDS)[number];
export type UiTone = (typeof UI_TONES)[number];
/** Each node's props: true when required. Each renderer declares that it draws every
 * one (`UiNodeProps`), so a prop the contract gains fails `pnpm check`. */
export const UI_NODE_PROPS = {
  Segmented: { bind: true, label: true, options: true, when: false },
  Select: { bind: true, label: true, options: true, when: false },
  Number: {
    bind: true,
    label: true,
    hint: false,
    prefix: false,
    suffix: false,
    required: false,
    when: false,
  },
  Slider: {
    bind: true,
    label: true,
    min: false,
    max: false,
    step: false,
    show: false,
    when: false,
  },
  Text: { text: true, tone: false, size: false, when: false },
  Title: { text: true, when: false },
  Markdown: { text: true, when: false },
  Note: { text: true, tone: false, icon: false, when: false },
  Badge: { text: true, tone: false, icon: false, when: false },
  KeyValue: { rows: true, when: false },
  Stat: {
    label: true,
    value: true,
    sub: false,
    trend: false,
    tone: false,
    icon: false,
    when: false,
  },
  Button: {
    label: true,
    action: false,
    style: false,
    icon: false,
    full: false,
    disabled: false,
    when: false,
  },
  Divider: { when: false },
  Row: { children: true, when: false },
  Col: { children: true, when: false },
  Grid: { children: true, cols: false, when: false },
  Card: { children: true, title: false, icon: false, when: false },
  More: { children: true, label: false, when: false },
  Slot: { card: true, record: true },
} as const satisfies Record<UiNodeType, Readonly<Record<string, boolean>>>;
/** Every prop of every node, each marked as drawn by a renderer. */
export type UiNodeProps = {
  [Node in UiNodeType]: { [Prop in keyof (typeof UI_NODE_PROPS)[Node]]: true };
};
