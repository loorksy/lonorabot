import { writeFile } from "node:fs/promises";
import { appearance } from "./appearance";
import { reference } from "./reference";

type Tokens = Readonly<Record<string, string | number>>;

const DARK = ':root,\n[data-theme="dark"]';
const LIGHT = '[data-theme="light"]';
const HC = '[data-contrast="high"]';

const vars = (tokens: Tokens, prefix = "", unit = "") =>
  Object.entries(tokens).map(([name, value]) => `--${prefix}${name}: ${value}${unit};`);

const block = (selector: string, lines: readonly string[], indent = "") =>
  `${selector
    .split("\n")
    .map((s) => indent + s)
    .join("\n")} {\n${lines.map((l) => `${indent}  ${l}`).join("\n")}\n${indent}}`;

const file = (header: string, blocks: readonly string[]) => `${[header, ...blocks].join("\n\n")}\n`;

const tokensCss = file(
  "/* Modified for Lonora; source attribution in THIRD_PARTY_NOTICES.md. Apache-2.0. */\n/* Shared design palette: keep this stylesheet and src/index.ts in sync. */",
  [
    block(DARK, ["color-scheme: dark;", ...vars(appearance.dark)]),
    block(LIGHT, ["color-scheme: light;", ...vars(appearance.light)]),
  ],
);

const shared = [
  `--blur: ${reference.blur};`,
  ...vars(reference.radius, "r-", "px"),
  ...vars(reference.type, "fs-", "px"),
  ...vars(reference.weight, "fw-"),
  ...vars(reference.motion),
  `--app-height: ${reference["app-height"]};`,
];
const opaque = (indent: string) =>
  [
    block(DARK, vars(reference.opaqueGlass.dark), indent),
    block(LIGHT, vars(reference.opaqueGlass.light), indent),
  ].join("\n");
const referenceCss = file(
  "/* Generated from src/reference.ts by `pnpm generate`; do not edit. Values: docs/ui-reference/Lonora-Desktop-37.html. */",
  [
    block(DARK, [
      "color-scheme: dark;",
      `--font: ${reference.font};`,
      ...vars(reference.dark),
      ...shared,
    ]),
    block(LIGHT, ["color-scheme: light;", ...vars(reference.light)]),
    `@supports not ((backdrop-filter: blur(2px)) or (-webkit-backdrop-filter: blur(2px))) {\n${opaque("  ")}\n}`,
    `@media (prefers-reduced-transparency: reduce) {\n${opaque("  ")}\n}`,
    block(HC, vars(reference.highContrast.dark)),
    block(`${LIGHT}${HC}`, vars(reference.highContrast.light)),
  ],
);

await writeFile(new URL("./tokens.css", import.meta.url), tokensCss);
await writeFile(new URL("./reference.css", import.meta.url), referenceCss);
