/** Semantic native-response metrics shared by Web and React Native renderers. */
export const visual = {
  space: { small: 6, normal: 10, large: 16 },
  radius: { small: 8, normal: 12, large: 16 },
  border: 1,
  font: { small: 12, body: 14, label: 13, heading: [22, 20, 18, 16], metric: 24 },
  line: { body: 22, small: 18 },
  touch: 44,
  controlFont: 16,
  controlHeight: 44,
  panelPadding: 12,
  chartHeight: 200,
  contentWidth: 728,
  columnMinimum: 144,
} as const;
