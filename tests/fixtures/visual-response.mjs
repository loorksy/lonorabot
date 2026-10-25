/** Native compiled-response fixture shared by browser and Expo acceptance. */
export function visualFixture({ artifactId } = {}) {
  const text = (id, value, visible) => ({
    id,
    type: "text",
    text: value,
    ...(visible ? { visible } : {}),
  });
  const metric = (id, label, value) => ({ id, type: "metric", label, value });
  const points = [
    { label: "A", value: 3 },
    { label: "B", value: 5 },
    { label: "C", value: 4 },
  ];
  const graph = (id, kind) => ({
    id,
    type: "chart",
    label: `${kind} illustration`,
    chart_kind: kind,
    points,
  });
  return {
    version: 1,
    parts: [
      { type: "text", text: "This is an interactive illustration, using no live account data." },
      {
        type: "ui",
        document: {
          version: 1,
          mode: "example",
          state: {
            quantity: 2,
            risk: 10,
            enabled: false,
            speed: "slow",
            tab: "overview",
            search: "",
          },
          root: {
            id: "illustration",
            type: "column",
            gap: "large",
            children: [
              { id: "heading", type: "heading", text: "Native response illustration", level: 2 },
              {
                id: "row",
                type: "row",
                children: [
                  { id: "badge", type: "badge", text: "Local calculation", tone: "info" },
                  { id: "icon", type: "icon", text: "info" },
                ],
              },
              {
                id: "card",
                type: "card",
                label: "Inputs",
                children: [
                  {
                    id: "form",
                    type: "form",
                    label: "Illustration settings",
                    children: [
                      {
                        id: "quantity",
                        type: "input",
                        input_kind: "number",
                        label: "Quantity",
                        state_key: "quantity",
                        minimum: 0,
                        maximum: 10,
                        step: 1,
                      },
                      {
                        id: "risk",
                        type: "slider",
                        label: "Risk input",
                        state_key: "risk",
                        minimum: 1,
                        maximum: 30,
                        step: 1,
                      },
                      {
                        id: "enabled",
                        type: "checkbox",
                        label: "Show additional context",
                        state_key: "enabled",
                      },
                      {
                        id: "speed",
                        type: "select",
                        label: "Pace",
                        state_key: "speed",
                        options: [
                          { value: "slow", label: "Slow" },
                          { value: "fast", label: "Fast" },
                        ],
                      },
                    ],
                  },
                  {
                    id: "grid",
                    type: "grid",
                    columns: 2,
                    children: [
                      metric("calculated", "Calculated illustration", {
                        op: "mul",
                        args: [{ state: "quantity" }, { state: "risk" }],
                      }),
                      metric("fixed", "Illustrative amount", 100),
                    ],
                  },
                  {
                    id: "progress",
                    type: "progress",
                    label: "Illustrative progress",
                    value: { state: "risk" },
                    maximum: 30,
                  },
                  text("conditional", "Additional context is visible.", { state: "enabled" }),
                ],
              },
              { id: "divider", type: "divider" },
              { id: "search", type: "input", label: "Search illustration", state_key: "search" },
              {
                id: "table",
                type: "table",
                label: "Illustrative table",
                filter_key: "search",
                fields: [
                  { key: "name", label: "Name" },
                  { key: "amount", label: "Amount" },
                ],
                rows: [
                  { name: "Alpha", amount: 10 },
                  { name: "Beta", amount: 20 },
                ],
              },
              {
                id: "tabs",
                type: "tabs",
                state_key: "tab",
                options: [
                  { value: "overview", label: "Overview" },
                  { value: "flow", label: "Flow" },
                ],
                children: [
                  {
                    id: "charts",
                    type: "container",
                    children: [graph("line", "line"), graph("bar", "bar"), graph("pie", "pie")],
                  },
                  {
                    id: "diagram",
                    type: "diagram",
                    label: "Illustrative flow",
                    vertices: [
                      { id: "a", label: "Observe" },
                      { id: "b", label: "Review" },
                    ],
                    edges: [{ source: "a", target: "b", label: "Continue" }],
                  },
                ],
              },
              {
                id: "disclosure",
                type: "disclosure",
                label: "Illustration details",
                children: [
                  {
                    id: "list",
                    type: "list",
                    children: [
                      text("list_text", "No broker action is performed by local controls."),
                    ],
                  },
                  {
                    id: "timeline",
                    type: "timeline",
                    children: [
                      text(
                        "timeline_text",
                        "The existing conversation receives follow-up requests.",
                      ),
                    ],
                  },
                ],
              },
              ...(artifactId
                ? [
                    {
                      id: "image",
                      type: "image",
                      artifact_id: artifactId,
                      label: "Verified uploaded image",
                    },
                    {
                      id: "open_artifact",
                      type: "button",
                      label: "Open image",
                      action: { kind: "open_artifact", resource_id: artifactId },
                    },
                  ]
                : []),
              {
                id: "follow_up",
                type: "button",
                label: "Discuss these inputs",
                action: {
                  kind: "follow_up",
                  text: "Discuss quantity {{quantity}}, risk {{risk}}, pace {{speed}}.",
                },
              },
            ],
          },
        },
      },
      { type: "text", text: "The surrounding response remains ordinary Markdown." },
    ],
  };
}
