#!/usr/bin/env node
// Ports Lonora's own words to the Android app: the Expo app's label catalogs become
// assets/l10n/{ar,en}.json, the @lonora/core text tables become lib/l10n/core/core_tables.g.dart,
// and the TS functions' real outputs become test fixtures the Dart ports are checked against.
// Nothing here writes new wording: every string is read from the TS sources by running them.
//
//   node apps/android/tool/i18n/port_i18n.mjs          (see tool/i18n/README.md)
//
// Deterministic: the same sources always give byte-identical outputs (TZ is pinned, keys keep
// their source order, fixtures use fixed dates).
process.env.TZ = "UTC";

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const app = resolve(here, "../.."); // apps/android
const repo = resolve(app, "../.."); // the monorepo root
const rel = (path) => relative(repo, path).split(sep).join("/");
const src = (path) => join(repo, path);

// ---------------------------------------------------------------------------------------------
// Sources
// ---------------------------------------------------------------------------------------------

const MOBILE = {
  i18n: "apps/mobile/lib/i18n.ts",
  shell: "apps/mobile/lib/labels-shell.ts",
  shellExtra: "apps/mobile/lib/labels-shell-extra.ts",
  incoming: "apps/mobile/lib/incoming-call-labels.json",
  attention: "apps/mobile/lib/attention-labels.ts",
  threadRow: "apps/mobile/components/shell/thread-row.tsx",
  artifacts: "apps/mobile/lib/artifacts.ts",
  networkStrip: "apps/mobile/components/shell/network-strip.tsx",
};

// The @lonora/core modules whose text the Android UI shows, with the module-private tables the
// converter also reads (they are exported to the converter's bundle only, never changed).
const CORE = {
  agentPermissionErrors: ["agent-permission-errors.ts", ["messages", "categories"]],
  financialBoundary: [
    "financial-boundary.ts",
    ["messages", "uncertainMessages", "UNCONFIRMED", "statusTexts", "approvalTexts", "runTexts"],
  ],
  ownerActions: ["owner-actions.ts", ["errors", "TARGET_LABEL"]],
  ownerProfile: [
    "owner-profile.ts",
    ["channels", "activityOnly", "channelHints", "languages", "labels", "fields", "errors"],
  ],
  chatgptPlan: ["chatgpt-plan.ts", ["errors"]],
  agentStatus: ["agent-status.ts", ["METRICS"]],
  agentModel: ["agent-model.ts", []],
  capabilities: ["capabilities.ts", []],
  tradingReadiness: ["trading-readiness.ts", []],
  tradeActionLabels: ["trade-action-labels.ts", []],
  orderLine: ["order-line.ts", []],
  turnActivity: [
    "turn-activity.ts",
    ["callLabels", "genericCall", "toolLabels", "statuses", "avatar"],
  ],
  timeSeparators: ["time-separators.ts", []],
  attachments: ["attachments.ts", []],
  plainLine: ["plain-line.ts", []],
  searchFeed: ["search-feed.ts", []],
  genuiFunctions: ["genui/functions.ts", []],
};
const coreFile = (name) => `packages/core/src/${CORE[name][0]}`;

// Expo component files whose small pure helpers are run as they are; their other imports
// (React Native, the session) are replaced by empty stubs while bundling.
const STUB_IMPORTS_OF = new Set([MOBILE.threadRow, MOBILE.artifacts].map(src));

// ---------------------------------------------------------------------------------------------
// esbuild (bundles the TS sources so the converter can run them)
// ---------------------------------------------------------------------------------------------

function loadEsbuild() {
  const bases = [process.env.LONORA_I18N_TOOLS, join(here, ".tools"), repo].filter(Boolean);
  for (const base of bases) {
    const require = createRequire(join(resolve(base), "package.json"));
    try {
      return require("esbuild");
    } catch {}
    try {
      // pnpm keeps esbuild under tsx (a root devDependency), not at the root.
      let dir = dirname(require.resolve("tsx"));
      while (!existsSync(join(dir, "package.json"))) dir = dirname(dir);
      return createRequire(join(dir, "package.json"))("esbuild");
    } catch {}
  }
  throw new Error(
    `esbuild not found (looked in ${bases.join(", ")}).\n` +
      "Install it once, e.g.:  npm install --prefix <dir> esbuild@0.28.2  and run with " +
      "LONORA_I18N_TOOLS=<dir>, or run `pnpm install` at the repository root.",
  );
}

async function loadSources() {
  const esbuild = loadEsbuild();
  const exposeByFile = new Map(
    Object.values(CORE).map(([file, names]) => [src(`packages/core/src/${file}`), names]),
  );
  const plugin = {
    name: "lonora-sources",
    setup(build) {
      build.onResolve({ filter: /.*/ }, (args) => {
        if (STUB_IMPORTS_OF.has(args.importer)) return { path: args.path, namespace: "stub" };
        if (args.path === "@lonora/contracts")
          return { path: src("packages/contracts/src/index.ts") };
        if (args.path === "@lonora/core") return { path: src("packages/core/src/index.ts") };
        return undefined;
      });
      // Any name read from a stub is a callable stub (so `memo(...)` at the top of a component
      // file still evaluates); the helpers that are run never touch one.
      build.onLoad({ filter: /.*/, namespace: "stub" }, () => ({
        contents: `
          const skip = (key) => key === "__esModule" || key === Symbol.toPrimitive;
          const proto = new Proxy({}, { get: (_, key) => (skip(key) ? undefined : stub) });
          const stub = new Proxy(function () {}, {
            get: (_, key) => (skip(key) ? undefined : stub),
            apply: () => stub,
            construct: () => stub,
            getPrototypeOf: () => proto,
          });
          module.exports = stub;`,
        loader: "js",
      }));
      build.onLoad({ filter: /\.tsx?$/ }, (args) => {
        let contents = readFileSync(args.path, "utf8");
        const names = exposeByFile.get(args.path);
        if (names?.length)
          contents += `\nexport { ${names.map((n) => `${n} as __${n}`).join(", ")} };\n`;
        return { contents, loader: args.path.endsWith(".tsx") ? "tsx" : "ts" };
      });
    },
  };
  const entries = {
    i18n: MOBILE.i18n,
    shell: MOBILE.shell,
    shellExtra: MOBILE.shellExtra,
    attention: MOBILE.attention,
    threadRow: MOBILE.threadRow,
    artifacts: MOBILE.artifacts,
    ...Object.fromEntries(Object.keys(CORE).map((name) => [name, coreFile(name)])),
  };
  // attention-labels.ts keeps its model-access table private as well.
  exposeByFile.set(src(MOBILE.attention), ["modelAccess"]);
  const result = await esbuild.build({
    stdin: {
      contents: Object.entries(entries)
        .map(([name, path]) => `export * as ${name} from ${JSON.stringify(src(path))};`)
        .join("\n"),
      resolveDir: repo,
      loader: "ts",
    },
    bundle: true,
    write: false,
    format: "esm",
    platform: "node",
    target: "node22",
    jsx: "automatic",
    logLevel: "silent",
    plugins: [plugin],
  });
  const code = result.outputFiles[0].text;
  return import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
}

// ---------------------------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------------------------

function fail(message) {
  throw new Error(message);
}

function write(path, text) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, text);
  console.log(`  wrote ${rel(path)}`);
}

const json = (value) => `${JSON.stringify(value, null, 2)}\n`;
/** A list with one item per line: readable fixtures with small diffs. */
const lines = (items) => `[\n${items.map((item) => JSON.stringify(item)).join(",\n")}\n]\n`;
const sha256 = (path) => createHash("sha256").update(readFileSync(src(path))).digest("hex");

/** The 1-based line where `const name` / `export const name` is declared in a source file. */
function declLine(path, name) {
  const lines = readFileSync(src(path), "utf8").split("\n");
  const pattern = new RegExp(`^(export )?(const|function) ${name}\\b`);
  const index = lines.findIndex((line) => pattern.test(line));
  if (index < 0) fail(`${path}: no declaration of ${name}`);
  return index + 1;
}

/** Fails when a pure helper that lives inline in a component is no longer what was ported. */
function guard(path, ...snippets) {
  const text = readFileSync(src(path), "utf8");
  for (const snippet of snippets)
    if (!text.includes(snippet)) fail(`${path} changed: "${snippet}" not found; re-port it.`);
}

const isText = (v) =>
  v && typeof v === "object" && Object.keys(v).length === 2 && typeof v.en === "string" &&
  typeof v.ar === "string";

// ---------------------------------------------------------------------------------------------
// 1. Catalogs: assets/l10n/ar.json and en.json
// ---------------------------------------------------------------------------------------------

/** The keys of a `name = { key: [...], ... }` table, as written in the source file. */
function sourceKeys(path) {
  return [...readFileSync(src(path), "utf8").matchAll(/^ {2}(\w+): \[/gm)].map((m) => m[1]);
}

function buildCatalogs(mod) {
  const labels = mod.i18n.labels;
  const shell = mod.shell.shellLabels;
  const extra = mod.shellExtra.shellExtraLabels;
  const own = sourceKeys(MOBILE.i18n);
  const shellKeys = Object.keys(shell);
  const extraKeys = Object.keys(extra);
  if (sourceKeys(MOBILE.shell).length !== shellKeys.length) fail("labels-shell.ts parse mismatch");
  if (sourceKeys(MOBILE.shellExtra).length !== extraKeys.length)
    fail("labels-shell-extra.ts parse mismatch");
  const overlap = own.filter((key) => shellKeys.includes(key) || extraKeys.includes(key));
  if (overlap.length) fail(`own keys shadowed by the shell spread: ${overlap.join(", ")}`);
  const expected = new Set([...own, ...shellKeys, ...extraKeys]);
  if (expected.size !== Object.keys(labels).length) fail("i18n.ts labels: unexpected key count");

  const ar = {};
  const en = {};
  for (const [key, value] of Object.entries(labels)) {
    if (!Array.isArray(value) || value.length !== 2 || value.some((v) => typeof v !== "string"))
      fail(`labels.${key}: not an [ar, en] pair`);
    ar[key] = value[0];
    en[key] = value[1];
  }

  const incoming = JSON.parse(readFileSync(src(MOBILE.incoming), "utf8"));
  const incomingKeys = Object.keys(incoming.en);
  if (incomingKeys.join() !== Object.keys(incoming.ar).join())
    fail("incoming-call-labels.json: en and ar keys differ");
  for (const key of incomingKeys) {
    ar[`incoming.${key}`] = incoming.ar[key];
    en[`incoming.${key}`] = incoming.en[key];
  }

  // attention.<code>: the label each attention code names (attention-labels.ts), resolved;
  // attention.model.<reason>: a refused model's family line, with its {provider}.
  const attention = mod.attention.attentionLabels;
  const modelAccess = mod.attention.__modelAccess;
  for (const [code, label] of Object.entries(attention)) {
    if (!(label in labels)) fail(`attentionLabels.${code}: unknown label ${label}`);
    ar[`attention.${code}`] = labels[label][0];
    en[`attention.${code}`] = labels[label][1];
  }
  for (const [reason, label] of Object.entries(modelAccess)) {
    ar[`attention.model.${reason}`] = labels[label][0];
    en[`attention.model.${reason}`] = labels[label][1];
  }

  const manifest = {
    generator: "apps/android/tool/i18n/port_i18n.mjs",
    sources: {
      [MOBILE.i18n]: { prefix: "", keys: own.length, sha256: sha256(MOBILE.i18n) },
      [MOBILE.shell]: { prefix: "sh_", keys: shellKeys.length, sha256: sha256(MOBILE.shell) },
      [MOBILE.shellExtra]: {
        prefix: "sh_",
        keys: extraKeys.length,
        sha256: sha256(MOBILE.shellExtra),
      },
      [MOBILE.incoming]: {
        prefix: "incoming.",
        keys: incomingKeys.length,
        sha256: sha256(MOBILE.incoming),
      },
      [MOBILE.attention]: {
        prefix: "attention.",
        keys: Object.keys(attention).length + Object.keys(modelAccess).length,
        sha256: sha256(MOBILE.attention),
      },
    },
    total: Object.keys(en).length,
    attention: attention,
    attentionModel: modelAccess,
  };
  return { ar, en, manifest };
}

// ---------------------------------------------------------------------------------------------
// 2. Core tables: lib/l10n/core/core_tables.g.dart
// ---------------------------------------------------------------------------------------------

function dartString(value) {
  let out = "";
  for (const char of value) {
    const code = char.codePointAt(0);
    if (char === "\\") out += "\\\\";
    else if (char === "'") out += "\\'";
    else if (char === "$") out += "\\$";
    else if (char === "\n") out += "\\n";
    else if (
      code < 0x20 ||
      (code >= 0x7f && code <= 0xa0) ||
      (code >= 0x200b && code <= 0x200f) ||
      (code >= 0x2028 && code <= 0x202f) ||
      (code >= 0x2060 && code <= 0x206f) ||
      code === 0xfeff
    )
      out += `\\u{${code.toString(16)}}`;
    else out += char;
  }
  return `'${out}'`;
}

const DART_RESERVED = new Set(
  (
    "assert break case catch class const continue default do else enum extends false final " +
    "finally for if in is new null rethrow return super switch this throw true try var void " +
    "while with hashCode runtimeType toString noSuchMethod keys"
  ).split(" "),
);
const getterName = (key) => (DART_RESERVED.has(key) ? `${key}_` : key);

const textLiteral = (t) => `CoreText(en: ${dartString(t.en)}, ar: ${dartString(t.ar)})`;
const stringMap = (o) =>
  `{${Object.entries(o)
    .map(([k, v]) => `${dartString(k)}: ${dartString(v)},`)
    .join("\n")}}`;

/** One table as Dart. `shape` is checked, never guessed. */
function dartTable({ module, source, dart, shape, className, doc }) {
  const value = source.value;
  const where = `/// ${coreFile(module)}:${declLine(coreFile(module), source.name)} \`${source.name}\``;
  const head = doc ? `${where}\n/// ${doc}` : where;
  switch (shape) {
    case "byLanguage": {
      const en = value.en;
      const ar = value.ar;
      const keys = Object.keys(en);
      if (keys.join() !== Object.keys(ar).join())
        fail(`${source.name}: en and ar keys differ in order or content`);
      for (const key of keys)
        if (typeof en[key] !== "string" || typeof ar[key] !== "string")
          fail(`${source.name}.${key}: not a string`);
      const getters = keys
        .map((key) => `  String get ${getterName(key)} => _v[${dartString(key)}]!;`)
        .join("\n");
      return `${head}
class ${className} {
  const ${className}._(this._v);
  final Map<String, String> _v;

  /// A label by its source key (for keys that come from server values); null if unknown.
  String? operator [](String key) => _v[key];

  /// Every source key, in source order.
  Iterable<String> get keys => _v.keys;

${getters}
}

${head}
const Map<String, ${className}> ${dart} = {
  'en': ${className}._(${stringMap(en)}),
  'ar': ${className}._(${stringMap(ar)}),
};
`;
    }
    case "textMap": {
      for (const [key, text] of Object.entries(value))
        if (!isText(text)) fail(`${source.name}.${key}: not {en, ar}`);
      return `${head}
const Map<String, CoreText> ${dart} = {
${Object.entries(value)
  .map(([key, text]) => `  ${dartString(key)}: ${textLiteral(text)},`)
  .join("\n")}
};
`;
    }
    case "text":
      if (!isText(value)) fail(`${source.name}: not {en, ar}`);
      return `${head}\nconst CoreText ${dart} = ${textLiteral(value)};\n`;
    case "stringMap":
      for (const [key, text] of Object.entries(value))
        if (typeof text !== "string") fail(`${source.name}.${key}: not a string`);
      return `${head}\nconst Map<String, String> ${dart} = ${stringMap(value)};\n`;
    case "stringList":
      if (!Array.isArray(value) || value.some((v) => typeof v !== "string"))
        fail(`${source.name}: not a string list`);
      return `${head}\nconst List<String> ${dart} = [${value.map(dartString).join(", ")}];\n`;
    case "nestedTextMap":
      return `${head}
const Map<String, Map<String, CoreText>> ${dart} = {
${Object.entries(value)
  .map(
    ([outer, inner]) =>
      `  ${dartString(outer)}: {\n${Object.entries(inner)
        .map(([key, text]) => {
          if (!isText(text)) fail(`${source.name}.${outer}.${key}: not {en, ar}`);
          return `    ${dartString(key)}: ${textLiteral(text)},`;
        })
        .join("\n")}\n  },`,
  )
  .join("\n")}
};
`;
    default:
      fail(`unknown shape ${shape}`);
  }
}

function buildCoreTables(mod) {
  const table = (module, name, dart, shape, extra = {}) => {
    const exported = mod[module][name];
    const internal = mod[module][`__${name}`];
    const value = exported ?? internal;
    if (value === undefined) fail(`${module}: no ${name}`);
    return { module, source: { name, value }, dart, shape, ...extra };
  };
  const tables = [
    table("agentPermissionErrors", "messages", "agentPermissionMessages", "textMap"),
    table("agentPermissionErrors", "categories", "agentPermissionCategories", "stringMap"),
    table("financialBoundary", "messages", "financialBoundaryMessages", "textMap"),
    table("financialBoundary", "UNCONFIRMED", "financialUnconfirmed", "text"),
    table("financialBoundary", "uncertainMessages", "financialUncertainMessages", "textMap"),
    table("financialBoundary", "statusTexts", "operationStatusTexts", "textMap"),
    table("financialBoundary", "approvalTexts", "approvalStatusTexts", "textMap"),
    table("financialBoundary", "runTexts", "runStatusTexts", "textMap"),
    table("ownerActions", "ownerActionLabels", "ownerActionLabels", "byLanguage", {
      className: "OwnerActionText",
    }),
    table("ownerActions", "errors", "ownerActionErrors", "textMap"),
    table("ownerActions", "TARGET_LABEL", "ownerActionTargetLabel", "stringMap"),
    table("ownerProfile", "channels", "reachMeChannelTexts", "textMap"),
    table("ownerProfile", "activityOnly", "reachMeActivityOnly", "text"),
    table("ownerProfile", "channelHints", "reachMeHintTexts", "textMap"),
    table("ownerProfile", "languages", "replyLanguageTexts", "textMap"),
    table("ownerProfile", "labels", "ownerProfileLabels", "textMap"),
    table("ownerProfile", "fields", "preferenceFieldTexts", "textMap"),
    table("ownerProfile", "errors", "ownerProfileErrors", "textMap"),
    table("chatgptPlan", "chatgptLabels", "chatgptLabels", "byLanguage", {
      className: "ChatGptText",
    }),
    table("chatgptPlan", "errors", "chatgptErrors", "textMap"),
    table("agentStatus", "agentStatusLabels", "agentStatusLabels", "byLanguage", {
      className: "AgentStatusText",
    }),
    table("agentStatus", "METRICS", "agentStatusMetrics", "stringList"),
    table("agentModel", "agentModelLabels", "agentModelLabels", "byLanguage", {
      className: "AgentModelText",
    }),
    table("capabilities", "capabilityLabels", "capabilityLabels", "byLanguage", {
      className: "CapabilityText",
    }),
    table("tradingReadiness", "tradingSafetyLabels", "tradingSafetyLabels", "byLanguage", {
      className: "TradingSafetyText",
    }),
    table("tradeActionLabels", "tradeActionLabels", "tradeActionLabels", "byLanguage", {
      className: "TradeActionText",
    }),
    table("orderLine", "orderLineLabels", "orderLineLabels", "byLanguage", {
      className: "OrderLineText",
    }),
    table("turnActivity", "callLabels", "activityCallLabels", "nestedTextMap"),
    table("turnActivity", "genericCall", "activityGenericCall", "text"),
    table("turnActivity", "toolLabels", "activityToolLabels", "textMap"),
    table("turnActivity", "statuses", "activityRunStatuses", "stringMap"),
    table("turnActivity", "avatar", "activityAvatar", "stringMap"),
  ];
  const header = `// GENERATED by apps/android/tool/i18n/port_i18n.mjs from the @lonora/core sources named
// above each table. Do not edit: change the TS source and run the converter again.
// The wording is Lonora's own (identical on Web and Mobile); the Dart ports in this folder
// read it from here.
// ignore_for_file: non_constant_identifier_names, constant_identifier_names

import 'text.dart';
`;
  return `${header}\n${tables.map(dartTable).join("\n")}`;
}

// ---------------------------------------------------------------------------------------------
// 3. Fixtures: the TS functions' own outputs
// ---------------------------------------------------------------------------------------------

const COUNTS = [0, 1, 2, 3, 4, 10, 11, 12, 99, 100, 101, 102, 103, 110, 111, 1000];
const LOCALES = ["ar", "en"];

/** Copied from network-strip.tsx:32-45 (inline in the component); guarded below. */
function networkWaitingText(locale, queued) {
  return queued > 0
    ? locale === "ar"
      ? queued === 1
        ? "رسالة واحدة تنتظر"
        : queued === 2
          ? "رسالتان تنتظران"
          : queued <= 10
            ? `${queued} رسائل تنتظر`
            : `${queued} رسالة تنتظر`
      : queued === 1
        ? "one message waiting"
        : `${queued} messages waiting`
    : "";
}

function pluralFixtures(mod) {
  guard(
    MOBILE.networkStrip,
    '"رسالة واحدة تنتظر"',
    '"رسالتان تنتظران"',
    "`${queued} رسائل تنتظر`",
    "`${queued} رسالة تنتظر`",
    '"one message waiting"',
    "`${queued} messages waiting`",
  );
  const cases = [];
  const add = (fn, args, out) => cases.push({ fn, args, out });
  for (const locale of LOCALES)
    for (const n of COUNTS) {
      add("chatsWord", [locale, n], mod.i18n.chatsWord(locale, n));
      add("waitingSentText", [locale, n], mod.i18n.waitingSentText(locale, n));
      add("agentsWord", [locale, n], mod.i18n.agentsWord(locale, n));
      add("networkWaitingText", [locale, n], networkWaitingText(locale, n));
      add("uncertainLine", [n, locale], mod.agentStatus.uncertainLine(n, locale));
      for (const mode of [null, "ask", "full"])
        add("tradingSubLine", [n, mode, locale], mod.ownerActions.tradingSubLine(n, mode, locale));
      add(
        "modeChangeLine",
        ["Atlas", "full", n, locale],
        mod.ownerActions.modeChangeLine("Atlas", "full", n, locale),
      );
      add(
        "tradingReadinessLine",
        [{ state: "uncertain", params: { count: n, symbol: "XAUUSD" } }, locale, NOW, {}],
        mod.tradingReadiness.tradingReadinessLine(
          { state: "uncertain", params: { count: n, symbol: "XAUUSD" } },
          locale,
          new Date(NOW),
        ),
      );
    }
  for (const n of [...COUNTS, -1, -3, 2.7, 1003, 1011]) {
    add("arCount", [n], mod.genuiFunctions.arCount(n));
    add(
      "plural",
      [n, "one", "two", "few", "many", "zero"],
      mod.genuiFunctions.FUNCTIONS.Plural({}, n, "one", "two", "few", "many", "zero"),
    );
    add(
      "plural",
      [n, "one", "two", "few", "many", ""],
      mod.genuiFunctions.FUNCTIONS.Plural({}, n, "one", "two", "few", "many", ""),
    );
  }
  return cases;
}

function fillFixtures(mod) {
  const fill = mod.i18n.fill;
  const cases = [];
  const positional = [
    ["{0} chats", [3]],
    ["{0} / {1}", ["a", "b"]],
    ["{1} then {0} then {1}", ["x", "y"]],
    ["{0} and {2}", ["only"]],
    ["{0}", [1.5]],
    ["{0}", [2.0]],
    ["{0}", [-0.25]],
    ["{0}", [1e21]],
    ["{0}", [0]],
    ["no placeholders", ["unused"]],
    ["{name} stays {0}", ["filled"]],
    ["{10}", ["a", "b"]],
    ["{0} {1}", []],
    ["{0}", [null]],
  ];
  for (const [template, values] of positional)
    cases.push({ template, mode: "positional", values, out: fill(template, ...values) });
  const named = [
    ["{count} unread", { count: 4 }],
    ["{provider} rejected", { provider: "OpenAI" }],
    ["{a}{b}{a}", { a: "1", b: "2" }],
    ["{missing} here", {}],
    ["{0} in named mode", { name: "x" }],
    ["{n} ok", { n: 0 }],
    ["{x}", { x: 3.0 }],
  ];
  for (const [template, values] of named)
    cases.push({ template, mode: "named", values, out: fill(template, values) });
  return cases;
}

// Fixed clocks: local wall-clock strings (no zone) read the same in Node and in Dart.
const NOW = "2026-11-27T16:30:00";
const SAME_DAY = "2026-11-27T09:05:00";
const OTHER_DAY = "2026-11-25T21:40:00";
const LAST_YEAR = "2025-03-02T07:15:00";

function coreFixtures(mod) {
  const cases = [];
  const add = (fn, args, out) => cases.push({ fn, args, out: out === undefined ? null : out });
  const now = new Date(NOW);
  const fb = mod.financialBoundary;
  const oa = mod.ownerActions;
  const op = mod.ownerProfile;
  const cg = mod.chatgptPlan;
  const as = mod.agentStatus;
  const cap = mod.capabilities;
  const tr = mod.tradingReadiness;
  const ta = mod.turnActivity;
  const am = mod.agentModel;

  for (const locale of LOCALES) {
    // agent-permission-errors
    for (const code of [...Object.keys(mod.agentPermissionErrors.__categories), "nope", "toString"])
      add("agentPermissionError", [code, locale], mod.agentPermissionErrors.agentPermissionError(code, locale));
    // financial-boundary
    for (const code of [...Object.keys(fb.__messages), "nope", "toString", null])
      add("financialBoundaryError", [code, locale], fb.financialBoundaryError(code, locale));
    for (const status of ["ambiguous", "failed", "confirmed"])
      for (const code of [
        ...Object.keys(fb.__uncertainMessages),
        "broker_state_changed",
        "nope",
        null,
      ])
        add("financialResultReason", [status, code, locale], fb.financialResultReason(status, code, locale));
    for (const [status, details] of [
      ["reserved", null],
      ["submitted", {}],
      ["confirmed", { verification: { status: "pending" } }],
      ["confirmed", { verification: { status: "unverified" } }],
      ["confirmed", { verification: { status: "verified" } }],
      ["confirmed", null],
      ["failed", { send_state: "not_sent" }],
      ["failed", { send_state: "sent" }],
      ["ambiguous", null],
      ["resolved", { resolution: { source: "owner" } }],
      ["resolved", { resolution: { basis: "target_closed" } }],
      ["resolved", { resolution: { basis: "target_no_longer_pending" } }],
      ["resolved", { resolution: { basis: "target_changed" } }],
      ["resolved", { resolution: {} }],
      ["resolved", null],
      ["mystery", null],
    ]) {
      if (locale === "ar") add("operationStatusKey", [status, details], fb.operationStatusKey(status, details));
      add("operationStatusText", [status, details, locale], fb.operationStatusText(status, details, locale));
    }
    for (const status of [...Object.keys(fb.__approvalTexts), "nope"])
      add("approvalStatusText", [status, locale], fb.approvalStatusText(status, locale));
    add("brokerTicketLabel", [locale], fb.brokerTicketLabel(locale));
    add("brokerPriceLabel", ["price", locale], fb.brokerPriceLabel("price", locale));
    add("brokerPriceLabel", ["execution_price", locale], fb.brokerPriceLabel("execution_price", locale));
    add("failedResultFallback", [locale], fb.failedResultFallback(locale));
    add("brokerWordsLabel", [locale], fb.brokerWordsLabel(locale));
    for (const status of [...Object.keys(fb.__runTexts), "nope"])
      add("runStatusText", [status, locale], fb.runStatusText(status, locale));

    // owner-actions
    for (const code of [...Object.keys(oa.__errors), ...Object.keys(cg.__errors), "nope", null])
      add("ownerActionError", [code, locale], oa.ownerActionError(code, locale));
    for (const mode of ["full", "ask", null, "other"])
      add("mandateLine", [mode, locale], oa.mandateLine(mode, locale));
    for (const withdrawn of [0, 1, 2, 5, 1.5])
      for (const mode of ["full", "ask"])
        add("modeChangeLine", ["Atlas", mode, withdrawn, locale], oa.modeChangeLine("Atlas", mode, withdrawn, locale));
    for (const status of ["pending", "confirmed", "cancelled", "expired", "superseded"])
      add("ownerActionStatus", [{ status }, locale], oa.ownerActionStatus({ status }, locale));
    for (const card of ownerActionCards())
      add("ownerActionCard", [card, locale, NOW], oa.ownerActionCard(card, locale, now));

    // owner-profile
    for (const code of [...Object.keys(op.__errors), "nope"])
      add("ownerProfileError", [code, locale], op.ownerProfileError(code, locale));
    for (const key of op.ownerProfileLabelKeys)
      add("ownerProfileLabel", [key, locale], op.ownerProfileLabel(key, locale));
    for (const channel of op.reachMeChannels) {
      add("reachMeLabel", [channel, locale], op.reachMeLabel(channel, locale));
      add("reachMeHint", [channel, locale], op.reachMeHint(channel, locale));
    }
    for (const language of op.replyLanguages)
      add("replyLanguageLabel", [language, locale], op.replyLanguageLabel(language, locale));
    for (const field of [...Object.keys(op.__fields), "nope"])
      add("preferenceFieldLabel", [field, locale], op.preferenceFieldLabel(field, locale));
    for (const [field, value] of [
      ["quiet_hours", "22-07"],
      ["quiet_hours", ""],
      ["quiet_hours", null],
      ["name", null],
      ["name", ""],
      ["name", "Sara"],
      ["opportunity_calls", true],
      ["opportunity_calls", false],
      ["reach_me", "notify"],
      ["reach_me", "message"],
      ["reach_me", "call"],
      ["reach_me", "activity"],
      ["reach_me", "pigeon"],
      ["reply_language", "auto"],
      ["reply_language", "ar"],
      ["reply_language", "en"],
      ["timezone", "Asia/Riyadh"],
      ["timezone", 3],
    ])
      add("preferenceValueText", [field, value, locale], op.preferenceValueText(field, value, locale));

    // chatgpt-plan
    for (const code of [...Object.keys(cg.__errors), "nope", null])
      add("chatgptError", [code, locale], cg.chatgptError(code, locale));
    for (const account of ["owner@example.com", null, ""])
      add("continuingAsLine", [account, locale], cg.continuingAsLine(account, locale));
    for (const status of [
      null,
      { email: null, plan: true, sign_in_again: false, signed_in: true },
      { email: null, plan: false, sign_in_again: true, signed_in: true },
      { email: null, plan: false, sign_in_again: false, signed_in: true },
      { email: null, plan: false, sign_in_again: false },
    ])
      add("chatgptRow", [status, locale], cg.chatgptRow(status, locale));
    for (const revoked of [true, false])
      add("signOutLine", [{ signed_out: true, revoked }, locale], cg.signOutLine({ signed_out: true, revoked }, locale));

    // agent-status
    for (const watch of watches()) {
      add("watchCondition", [watch, locale], as.watchCondition(watch, locale));
      add("watchUntil", [watch, locale, NOW], as.watchUntil(watch, locale, now));
    }
    for (const state of liveStates())
      add("agentStatusLine", [state, locale, NOW], as.agentStatusLine(state, locale, now));

    // agent-model
    for (const value of [0, 5, 999, 1000, 1500, 12345, 99950, 123456, 999999, 1234567, 1e9, 2.5e12])
      add("tokenCount", [value, locale], am.tokenCount(value, locale));
    for (const [usage, days] of [
      [{ input_tokens: 0, output_tokens: 0, requests: 0 }, 30],
      [{ input_tokens: 12345, output_tokens: 678, requests: 42 }, 30],
      [{ input_tokens: 1234567, output_tokens: 1500, requests: 1234 }, 7],
    ])
      add("usageLine", [usage, days, locale], am.usageLine(usage, days, locale));
    for (const summary of modelSummaries())
      add("agentModelLines", [summary, locale], am.agentModelLines(summary, locale));

    // capabilities
    for (const source of trustedSources())
      add("sourceLine", [source, locale], cap.sourceLine(source, locale));
    for (const skill of capabilitySkills())
      add("skillLine", [skill, locale], cap.skillLine(skill, locale));
    for (const server of capabilityServers())
      add("serverLine", [server, locale], cap.serverLine(server, locale));
    for (const item of integrations())
      add("integrationLine", [item, locale], cap.integrationLine(item, locale));
    for (const capability of [
      "web_search",
      "web_fetch",
      "web_browse",
      "news_feeds",
      "economic_calendar",
      "workspace_files",
      "workspace_execution",
      "chart_images",
      "mcp_tools",
    ])
      for (const state of ["ready", "not_connected"])
        add("builtInLine", [{ capability, state, via: null }, locale], cap.builtInLine({ capability, state, via: null }, locale));

    // trading-readiness
    for (const iso of [SAME_DAY, OTHER_DAY, LAST_YEAR])
      add("readinessTime", [iso, locale, NOW], tr.readinessTime(iso, locale, now));
    const names = { "acc-1": "Main ICMarkets" };
    for (const readiness of readinessStates())
      add(
        "tradingReadinessLine",
        [readiness, locale, NOW, names],
        tr.tradingReadinessLine(readiness, locale, now, (id) => names[id] ?? null),
      );
    add("listSeparator", [locale], tr.listSeparator(locale));

    // turn-activity
    const toolsets = [...Object.keys(ta.__callLabels), "unknown_set", undefined];
    for (const toolset of toolsets)
      for (const effect of ["read", "change", "financial", undefined])
        add("activityCallLabel", [{ toolset, effect }, locale], ta.activityCallLabel({ toolset, effect }, locale));
    for (const name of [...Object.keys(ta.__toolLabels), "toString", "market_quote"])
      add("activityCallLabel", [{ toolset: "market", effect: "read", name }, locale], ta.activityCallLabel({ toolset: "market", effect: "read", name }, locale));

    // order-line
    for (const state of Object.keys(mod.orderLine.orderLineLabels.en))
      add("orderLineText", [state, locale], mod.orderLine.orderLineText(state, locale));
    for (const request of [
      { action: "buy", volume: "0.10" },
      { action: "sell", volume: 2 },
      { action: "buy_limit", volume: "1" },
      { action: "sell_stop", volume: "x" },
      { action: "close_position", volume: "0.5" },
      { action: "modify_position", volume: "0.5" },
      { action: "cancel_order" },
      { action: "mystery", volume: "1" },
      {},
    ])
      add("orderLineAction", [request, locale], mod.orderLine.orderLineAction(request, locale));

    // time-separators
    for (const iso of [
      SAME_DAY,
      "2026-11-26T23:59:00",
      "2026-11-24T10:00:00",
      "2026-11-21T10:00:00",
      "2026-11-20T10:00:00",
      "2026-01-05T08:00:00",
      LAST_YEAR,
      "not a date",
    ])
      add(
        "formatTimeSeparator",
        [iso, locale, { today: "TODAY", yesterday: "YESTERDAY" }, NOW],
        mod.timeSeparators.formatTimeSeparator(iso, locale, { today: "TODAY", yesterday: "YESTERDAY" }, now),
      );

    // apps/mobile/lib/artifacts.ts formatFileSize
    for (const size of [0, 1, 1023, 1024, 1536, 1048576, 1572864, 20971520, 5e9, 5e12, -5, Number.NaN])
      add("formatFileSize", [Number.isNaN(size) ? null : size, locale], mod.artifacts.formatFileSize(Number.isNaN(size) ? null : size, locale));
  }

  // Locale-free helpers.
  for (const [current, previous] of [
    [SAME_DAY, undefined],
    [SAME_DAY, "2026-11-27T08:51:00"],
    [SAME_DAY, "2026-11-27T08:50:00"],
    ["2026-11-27T00:05:00", "2026-11-26T23:59:00"],
    [SAME_DAY, "garbage"],
    ["garbage", SAME_DAY],
  ])
    add("needsTimeSeparator", [current, previous ?? null], mod.timeSeparators.needsTimeSeparator(current, previous));
  for (const value of ["XAUUSD", "12.5", "a\u2069b\u202ec", "", "\u2066x\u2067"])
    add("isolate", [value], tr.isolate(value));
  for (const text of [
    "مرحبا",
    "Hello",
    "123 + 4",
    "Hello مرحبا",
    "٣٤٥",
    "،؛؟",
    "שלום",
    "Привет",
    "Ελλάδα",
    "",
    "  ",
    "×÷",
    "🙂",
    "ﷺ",
  ])
    add("textDirection", [text], mod.plainLine.textDirection(text) ?? null);
  for (const size of [undefined, 0, 20 * 1024 * 1024, 20 * 1024 * 1024 + 1])
    add("attachmentTooLarge", [size ?? null], mod.attachments.attachmentTooLarge(size));
  for (const iso of [SAME_DAY, "2026-11-27T00:00:00", "2026-11-27T23:59:00", OTHER_DAY])
    add("clockTime", [iso], mod.threadRow.clockTime(iso));
  for (const readiness of readinessStates())
    add("tradingReadinessTone", [readiness], tr.tradingReadinessTone(readiness));
  for (const state of [null, ...liveStates()])
    add("liveAvatarState", [state], as.liveAvatarState(state));
  for (const failure of [
    null,
    { family: "quota", provider: "openai_chatgpt" },
    { family: "quota", provider: "openai" },
    { family: "auth", provider: "openai_chatgpt" },
  ])
    add("planLimitReached", [failure], cg.planLimitReached(failure));
  for (const row of [
    { status: "approved", results: [] },
    { status: "drifted", results: [] },
    { status: "rejected", results: [] },
    { status: "completed", results: [] },
    { status: "completed", results: [{ status: "confirmed" }, { status: "confirmed" }] },
    { status: "completed", results: [{ status: "confirmed" }, { status: "ambiguous" }] },
    { status: "completed", results: [{ status: "failed" }] },
  ])
    add("approvalEndTone", [row], fb.approvalEndTone(row));
  for (const label of [null, { name: "GPT-5", model: "gpt-5" }, { name: null, model: "o4" }, { name: null, model: null }])
    add("modelName", [label], am.modelName(label));
  for (const summary of modelSummaries()) {
    add("offersDefaultModel", [summary], am.offersDefaultModel(summary));
    add("usesChatGptPlan", [summary], am.usesChatGptPlan(summary));
  }
  for (const [titles, name] of [
    [{ read: "Read a file" }, "read"],
    [{ read: "Read a file" }, "write"],
    [{}, "toString"],
    [{ toString: "Own title" }, "toString"],
  ])
    add("toolTitle", [titles, name], cap.toolTitle(titles, name) ?? null);
  for (const [run, events] of activityRuns())
    add("turnActivity", [run, events], ta.turnActivity(run, events));
  return cases;
}

// --- Inputs for the fixtures (shaped like @lonora/contracts) ---------------------------------

function watches() {
  const base = {
    id: "w1",
    kind: "price",
    account_id: null,
    symbol: "XAUUSD",
    condition: "above",
    level: "2100",
    indicator: null,
    timeframe: null,
    metric: null,
    expires_at: null,
    lifecycle: "active",
  };
  return [
    base,
    { ...base, condition: "cross_below", level: "0", expires_at: SAME_DAY },
    { ...base, level: null, condition: null, expires_at: OTHER_DAY },
    { ...base, kind: "calendar", symbol: null },
    { ...base, kind: "account", symbol: null, metric: "equity", condition: "below", level: "900" },
    { ...base, kind: "account", symbol: null, metric: "nonsense", condition: "changed", level: null },
    { ...base, kind: "position", metric: "profit", condition: "above", level: "50" },
    { ...base, kind: "position", metric: null, condition: "closed", level: null },
    { ...base, kind: "indicator", indicator: "rsi", timeframe: "1h", condition: "cross_above", level: "70" },
    { ...base, kind: "indicator", indicator: null, timeframe: null, symbol: null, condition: "due" },
    { ...base, kind: "dynamic", condition: null, level: null },
    { ...base, kind: "dynamic", symbol: null },
  ];
}

function liveStates() {
  const base = {
    agent_id: "a1",
    observed_at: NOW,
    state: "idle",
    phase: "idle",
    reason_code: null,
    pending_approval_count: 0,
    watch_count: 0,
    tasks: [],
    health: [],
  };
  const watch = watches()[0];
  return [
    base,
    { ...base, state: "paused" },
    { ...base, phase: "uncertain" },
    { ...base, phase: "uncertain", trading_readiness: { state: "uncertain", params: { count: 4 } } },
    { ...base, phase: "uncertain", trading_readiness: { state: "uncertain", params: { count: 12 } } },
    { ...base, phase: "uncertain", trading_readiness: { state: "ask_me", params: {} } },
    { ...base, pending_card_id: "c1" },
    { ...base, current_work: { kind: "waiting_owner", text: "", until: null, run_id: null } },
    { ...base, pending_approval_count: 2 },
    { ...base, pending_authorization_count: 1 },
    { ...base, phase: "awaiting_broker" },
    { ...base, current_work: { kind: "broker", text: "", until: null, run_id: null } },
    { ...base, current_work: { kind: "analysing", text: "x", until: null, run_id: null } },
    { ...base, current_work: { kind: "searching", text: "x", until: null, run_id: null } },
    { ...base, state: "action_required" },
    { ...base, state: "working" },
    { ...base, state: "waiting" },
    { ...base, state: "degraded" },
    { ...base, phase: "monitoring", watches: [], watch_count: 0 },
    { ...base, phase: "monitoring", watches: [watch], watch_count: 1 },
    { ...base, phase: "monitoring", watches: [{ ...watch, expires_at: SAME_DAY }], watch_count: 3 },
    { ...base, phase: "monitoring", watches: [{ ...watch, expires_at: OTHER_DAY }], watch_count: 2 },
    {
      ...base,
      phase: "monitoring",
      watches: [{ ...watches()[3], expires_at: OTHER_DAY }],
      watch_count: 12,
    },
    { ...base, state: "working", phase: "monitoring", watches: [watch], watch_count: 1 },
  ];
}

function readinessStates() {
  const base = {
    presentation_only: true,
    observed_at: NOW,
    params: {},
    trading_mode: "ask",
    level: "supervised",
    grants: [],
    unresolved_operations: [],
  };
  return [
    { ...base, state: "no_trading" },
    { ...base, state: "agent_paused" },
    { ...base, state: "uncertain", params: {} },
    { ...base, state: "uncertain", params: { count: 3 } },
    { ...base, state: "uncertain", params: { count: 1, symbol: "EURUSD" } },
    { ...base, state: "ask_me" },
    { ...base, state: "on_its_own", trading_mode: "full" },
    { ...base, state: "on_its_own", params: { account_count: 3 } },
    { ...base, state: "on_its_own", params: { full_delegation: true } },
    { ...base, state: "on_its_own", params: { symbol_scope: "account", valid_until: SAME_DAY } },
    {
      ...base,
      state: "on_its_own",
      params: { symbols: ["XAUUSD", "EURUSD"], valid_until: OTHER_DAY, account_id: "acc-1" },
    },
    { ...base, state: "on_its_own", params: { symbols: [], account_id: "acc-unknown" } },
    { ...base, state: "on_its_own", params: { symbols: ["BTCUSD"], account_count: 1 } },
  ];
}

function trustedSources() {
  const base = {
    id: "s1",
    kind: "github",
    identifier: "github.com",
    label: null,
    effect_tier: "read",
    tools: [],
    write_tools: [],
    blocked_tools: [],
    needs_review: false,
    added_via: "default",
    added_by_agent_name: null,
    active: true,
    created_at: OTHER_DAY,
    updated_at: OTHER_DAY,
    last_used_at: null,
    revoked_at: null,
  };
  return [
    base,
    { ...base, kind: "github_owner", label: "anthropics", added_via: "owner_ui", last_used_at: OTHER_DAY },
    { ...base, kind: "github_repo", label: null, added_via: "owner_message", active: false },
    { ...base, kind: "feed_domain", label: "reuters.com", added_via: "owner_card", last_used_at: "garbage" },
    {
      ...base,
      kind: "mcp_server",
      label: "Docs",
      added_via: "operator",
      tools: ["a", "b", "c"],
      write_tools: ["c"],
      last_used_at: LAST_YEAR,
    },
    { ...base, kind: "mcp_server", label: "Writer", effect_tier: "write_nonfinancial", tools: ["a"], write_tools: ["a"] },
    { ...base, kind: "mcp_server", label: "Old", needs_review: true, tools: ["a"] },
  ];
}

function capabilitySkills() {
  const base = {
    resource_id: "r1",
    agent_id: null,
    agent_name: null,
    skill_id: "chart-reading",
    title: null,
    version: null,
    provenance: "bundled",
    repository: null,
    commit: null,
    enabled: true,
    undone: false,
    can_undo: false,
    installed_at: OTHER_DAY,
    updated_at: OTHER_DAY,
  };
  return [
    base,
    { ...base, title: "Chart reading", version: "1.2.0", agent_name: "Atlas", provenance: "owner", enabled: false },
    { ...base, provenance: "external", repository: "acme/skills" },
    { ...base, provenance: "external" },
    { ...base, provenance: "agent_authored", undone: true },
    { ...base, provenance: "unverified" },
  ];
}

function capabilityServers() {
  const base = {
    connection_id: "m1",
    name: "Docs",
    enabled: true,
    credentials_configured: true,
    trusted_tier: null,
    trusted_tools: [],
    tool_titles: {},
    tool_titles_kept: false,
    write_tools: [],
    blocked_tools: [],
    operator_declared: 0,
    trust_source_id: null,
    last_used_at: null,
  };
  return [
    base,
    { ...base, name: null, operator_declared: 2, enabled: false },
    { ...base, trusted_tier: "read", trusted_tools: ["a", "b"], write_tools: ["b"], blocked_tools: ["x"], last_used_at: OTHER_DAY },
    { ...base, trusted_tier: "write_nonfinancial", trusted_tools: ["a"], write_tools: ["a"] },
  ];
}

function integrations() {
  const base = {
    id: "i1",
    type: "news_feed",
    name: null,
    enabled: true,
    configured: true,
    domain: null,
    deliver_to_agent_name: null,
  };
  return [
    base,
    { ...base, type: "brave_search", enabled: false },
    { ...base, type: "economic_calendar", name: "FF" },
    { ...base, type: "telegram", name: "Ops", deliver_to_agent_name: "Atlas" },
    { ...base, type: "webhook", domain: "hooks.example.com" },
  ];
}

function modelSummaries() {
  const base = {
    record: { preference: { primary: null }, chosen_by: null },
    current: { provider: "openai", model: "gpt-5", name: "GPT-5" },
    available: [],
    connected_providers: [],
    usage: { requests: 0, input_tokens: 0, output_tokens: 0, cached_tokens: 0, models: [], days: 30 },
  };
  return [
    base,
    { ...base, current: { provider: null, model: null, name: null } },
    {
      ...base,
      record: { preference: { primary: { provider: "openai_chatgpt", model: "gpt-5" } }, chosen_by: "owner" },
      current: { provider: "openai_chatgpt", model: "gpt-5", name: null },
      usage: { ...base.usage, requests: 12, input_tokens: 45000, output_tokens: 1200 },
    },
    {
      ...base,
      record: { preference: { primary: { provider: "anthropic", model: "x" } }, chosen_by: "creation" },
      usage: { ...base.usage, requests: 1, input_tokens: 999, output_tokens: 1, days: 7 },
    },
  ];
}

function ownerActionCards() {
  const base = {
    id: "card-1",
    kind: "trading_mode",
    status: "pending",
    status_reason: null,
    superseded_by: null,
    source: "agent",
    agent_id: "a1",
    thread_id: "t1",
    run_id: null,
    timeline_seq: null,
    facts: { several_accounts: false },
    requires_passkey: false,
    result: {},
    expires_at: NOW,
    decided_at: null,
    decided_via: null,
    created_at: OTHER_DAY,
    updated_at: OTHER_DAY,
  };
  const card = (kind, facts, extra = {}) => ({
    ...base,
    kind,
    facts: { several_accounts: false, ...facts },
    ...extra,
  });
  const account = { id: "acc-1", label: "ICMarkets 5512", provider: "metaapi" };
  const mandate = { agent: { exists: true, id: "a1", name: "Atlas" }, trading_mode: "ask" };
  const operation = {
    operation_id: "op1",
    action: "buy",
    symbol: "XAUUSD",
    volume: "0.10",
    price: null,
    has_ticket: false,
    status: "ambiguous",
    submitted_at: SAME_DAY,
    by_agent_name: "Atlas",
    by_owner: false,
  };
  const supervision = {
    supervisor_name: "Lonora",
    supervised_names: ["Atlas"],
    active: true,
    target: "routine",
    target_label: "Morning scan",
  };
  const field = (key, extra = {}) => ({ key, label: null, secret: true, ...extra });
  const secret = (extra) => ({
    label: null,
    fields: [field("TOKEN", { label: "API token" })],
    destination: "workspace",
    agent_name: "Atlas",
    ...extra,
  });
  return [
    // Mandate card
    card("trading_mode", mandate),
    card("trading_mode", { ...mandate, trading_mode: "full", active_grant: true }),
    card("trading_mode", { ...mandate, agent: { exists: true, name: null } }),
    card("trading_mode", { agent: { exists: false, name: null } }),
    card("trading_mode", {
      ...mandate,
      several_accounts: true,
      previous_grants: [
        { full_delegation: false, symbol_scope: "selected", symbols: ["XAUUSD", "EURUSD"], account },
      ],
    }),
    card("trading_mode", {
      ...mandate,
      several_accounts: true,
      previous_grants: [
        { full_delegation: true, symbol_scope: "account", symbols: [], account },
        { full_delegation: false, symbol_scope: "account", symbols: [], account: { id: "b", label: null, provider: "simulation" } },
      ],
    }),
    card("trading_mode", { ...mandate, previous_grants: [{ full_delegation: false, symbol_scope: "selected", symbols: ["BTCUSD"], account }] }, { status: "confirmed" }),
    card("trading_mode", { agent: { exists: true, name: "Atlas" } }, { status: "confirmed" }),
    // Settle an unconfirmed operation
    card("settle_operation", { operation }),
    card("settle_operation", { operation: { ...operation, by_owner: true, submitted_at: OTHER_DAY }, several_accounts: true, account }),
    card("settle_operation", {
      operation: { ...operation, action: "close_position", volume: null, symbol: null, submitted_at: null, by_agent_name: null },
      several_accounts: true,
      account: { id: "x", label: null, provider: null },
    }),
    card("settle_operation", { operation: { ...operation, action: "weird_action" } }, { result: { outcome: "unknown" } }),
    card("settle_operation", {}, { status: "confirmed", result: { outcome: "executed" } }),
    card("settle_operation", {}, { status: "confirmed", result: { outcome: "not_executed" } }),
    card("settle_operation", {}, { status: "confirmed", result: { outcome: "unknown" } }),
    // Paused work
    card("supervision_paused", { supervision }),
    card("supervision_paused", { supervision: { ...supervision, supervisor_name: null, from_owner_message: true, owner_holds: true, target: "agent", target_label: null } }),
    card("supervision_paused", { supervision: { ...supervision, owner_holds: true, target: "watch" } }),
    card("supervision_paused", { supervision: { ...supervision, active: false, supervised_names: [], target: "task" } }),
    card("supervision_paused", {}),
    card("supervision_paused", { supervision }, { status: "confirmed" }),
    card("supervision_paused", { supervision }, { status: "cancelled" }),
    // Secret cards
    card("secret", { secret: secret({ label: "Exchange key", saves_as: ["TOKEN"], replaces: ["TOKEN"] }) }),
    card("secret", { secret: secret({ fields: [field("A", { label: "Key A", required: false }), field("B", { label: "Key B", secret: false })], agent_name: null }) }),
    card("secret", {
      secret: secret({
        connect: "mcp_server",
        details: { name: "Docs" },
        fields: [field("url", { role: "server_url", secret: false }), field("token", { role: "token" })],
        saves_as: ["MCP_DOCS_URL", "MCP_DOCS_TOKEN"],
      }),
    }),
    card("secret", { secret: secret({ connect: "mcp_server", service: "x", fields: [field("url", { role: "server_url", secret: false })] }) }),
    card("secret", { secret: secret({ connect: "news_feed", fields: [field("feed", { role: "feed_url", secret: false })] }) }),
    card("secret", { secret: secret({ connect: "brave_search", details: { name: "Brave" }, fields: [field("key", { role: "api_key" })] }) }),
    card("secret", { secret: secret({ connect: "economic_calendar", fields: [field("k")] }) }),
    card("secret", { secret: secret({ connect: "broker", destination: "broker", fields: [field("password", { label: "Password" })] }) }),
    card("secret", {
      secret: secret({
        connect: "model_provider",
        details: { name: "OpenRouter", provider: "openrouter" },
        fields: [field("key", { role: "api_key" }), field("url", { role: "server_url", secret: false })],
        saves_as: ["OPENROUTER_API_KEY"],
        replaces: ["OPENROUTER_API_KEY"],
      }),
    }),
    card("secret", { secret: secret({ connect: "model_provider", fields: [field("key", { role: "api_key" })] }) }),
    card("secret", { secret: secret({ connect: "model_provider", details: { provider: "openai_chatgpt" }, fields: [] }) }),
    card("secret", { secret: secret({ connect: "model_provider", details: { provider: "openai_chatgpt" }, fields: [], agent_name: null }) }, { status: "confirmed", result: { account: "owner@example.com" } }),
    card("secret", { secret: secret({ connect: "model_provider", details: { provider: "openai_chatgpt" }, fields: [] }) }, { status: "confirmed", result: {} }),
    ...["connect", "rotate_password", "replace_token", undefined].map((purpose) =>
      card("secret", {
        secret: secret({
          destination: "broker",
          purpose,
          account: { login: "5512", server: "ICMarkets-Live", platform: "mt5" },
          server_from: purpose === "rotate_password" ? "ICMarkets-Demo" : undefined,
          fields: [field("PASSWORD"), field("METAAPI_TOKEN")],
        }),
      }),
    ),
    ...[undefined, "pending", "connected", "linked", "failed"].flatMap((provisioning) =>
      ["connect", "rotate_password"].map((purpose) =>
        card(
          "secret",
          {
            secret: secret({
              destination: "broker",
              purpose,
              account: { login: "5512", server: "ICMarkets-Live", platform: "mt4" },
              fields: [field("PASSWORD")],
            }),
          },
          { status: "confirmed", result: { provisioning } },
        ),
      ),
    ),
    card("secret", { secret: secret({ connect: "news_feed" }) }, { status: "confirmed" }),
    card("secret", { secret: secret({}) }, { status: "confirmed" }),
    // Ended cards
    ...[
      "operation_already_settled",
      "done_by_another_card",
      "same_choice_on_another_card",
      "grant_already_active",
      "agent_already_removed",
      "broker_connection_changed",
      "supervision_pause_ended",
      "watch_expired",
      "credential_already_configured",
      "secret_name_in_use",
      "expired",
      "something_else",
      null,
    ].map((status_reason) => card("secret", { secret: secret({}) }, { status: "superseded", status_reason })),
    card("secret", { secret: secret({}) }, { status: "expired" }),
    card("secret", { secret: secret({}) }, { status: "cancelled" }),
    card("trading_mode", mandate, { status: "expired", requires_passkey: true }),
    card("trading_mode", mandate, { requires_passkey: true }),
  ];
}

function activityRuns() {
  const run = (extra = {}) => ({
    id: "r1",
    thread_id: "t1",
    agent_id: "a1",
    status: "running",
    trigger: "message",
    model_metadata: {},
    created_at: "2026-11-27T09:00:00",
    updated_at: "2026-11-27T09:00:01",
    ...extra,
  });
  let cursor = 0;
  const event = (kind, payload = {}, created_at = "2026-11-27T09:00:05", run_id = "r1") => ({
    id: `e${++cursor}`,
    cursor,
    kind,
    run_id,
    thread_id: "t1",
    agent_id: "a1",
    payload,
    created_at,
  });
  return [
    [run(), []],
    [run({ status: "queued" }), []],
    [run({ stream: { phase: "streaming", text: "hi" } }), []],
    [run({ stream: { phase: "streaming", text: "" } }), []],
    [run({ model_metadata: { activity: { kind: "run.reply_started", observed_at: "2026-11-27T09:00:03" } } }), []],
    [run({ model_metadata: { activity: { kind: "tool.started", name: "web_search", toolset: "research", observed_at: "2026-11-27T09:00:03" } } }), []],
    [
      run({ model_metadata: { activity: { kind: "run.delta", observed_at: "2026-11-27T09:00:09" } } }),
      [event("run.context_started", {}, "2026-11-27T09:00:05")],
    ],
    [run(), [event("run.context_started"), event("run.reply_started", {}, "2026-11-27T09:00:06")]],
    [
      run(),
      [
        event("tool.started", { call_id: "c1", name: "market_quote", toolset: "market", effect: "read" }, "2026-11-27T09:00:06"),
        event("tool.started", { call_id: "c2", name: "trade_place", toolset: "trading", effect: "financial" }, "2026-11-27T09:00:07"),
      ],
    ],
    [
      run(),
      [
        event("tool.started", { call_id: "c1", name: "memory_save", toolset: "memory", effect: "change" }, "2026-11-27T09:00:06"),
        event("tool.completed", { call_id: "c1", ok: true }, "2026-11-27T09:00:07"),
        event("tool.started", { call_id: "c2", name: "files_write", toolset: "files", effect: "change" }, "2026-11-27T09:00:08"),
        event("tool.failed", { call_id: "c2" }, "2026-11-27T09:00:09"),
        event("tool.started", { call_id: "c3", name: "chart_draw", toolset: "charts", effect: "change" }, "2026-11-27T09:00:10"),
        event("tool.completed", { call_id: "c3", ok: false }, "2026-11-27T09:00:11"),
        event("tool.started", { call_id: "c4", name: "agent_message", toolset: "collaboration", effect: "change" }, "2026-11-27T09:00:12"),
        event("tool.cancelled", { call_id: "c4" }, "2026-11-27T09:00:13"),
        event("run.delta", {}, "2026-11-27T09:00:14"),
      ],
    ],
    [
      run({ status: "completed" }),
      [
        event("tool.started", { call_id: "c1", name: "account_read", toolset: "account" }, "2026-11-27T09:00:06"),
        event("tool.started", { call_id: "c2", name: "notes", toolset: "intelligence", effect: "bogus" }, "2026-11-27T09:00:07"),
      ],
    ],
    [run({ status: "waiting_input" }), [event("tool.started", { call_id: "c1", name: "x", toolset: "memory", effect: "read" })]],
    [run({ status: "waiting_takeover" }), []],
    [run({ status: "failed" }), []],
    [run({ status: "cancelled" }), [event("tool.started", { call_id: "c9", name: "x", toolset: "files", effect: "change" })]],
    [
      run(),
      [
        event("tool.started", { call_id: "c1", name: "  ", toolset: "market" }),
        event("tool.started", { call_id: "", name: "x" }),
        event("tool.started", { call_id: "c3", name: "other_run" }, "2026-11-27T09:00:05", "r2"),
        event("run.reply_started", {}, "2026-11-27T08:59:00"),
      ],
    ],
    [
      run({ model_metadata: { activity: { kind: "run.delta", observed_at: "2026-11-27T09:00:20" } } }),
      [event("run.reply_started", {}, "2026-11-27T09:00:10")],
    ],
    [run({ model_metadata: { activity: { kind: "run.delta", observed_at: "garbage" } } }), []],
    [
      run(),
      Array.from({ length: 30 }, (_, i) =>
        event("tool.started", { call_id: `k${i}`, name: `tool_${i}`, toolset: "research" }, `2026-11-27T09:01:${String(i).padStart(2, "0")}`),
      ),
    ],
  ];
}

// ---------------------------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------------------------

function dartFormat(paths) {
  const candidates = [process.env.DART, "dart", "/opt/flutter/bin/dart"].filter(Boolean);
  for (const dart of candidates) {
    try {
      execFileSync(dart, ["format", ...paths], { stdio: "pipe" });
      return;
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
  }
  console.warn("  warning: dart not found; run `dart format lib/l10n` before committing.");
}

async function main() {
  console.log("Porting Lonora's words to apps/android …");
  const mod = await loadSources();

  const { ar, en, manifest } = buildCatalogs(mod);
  write(join(app, "assets/l10n/ar.json"), json(ar));
  write(join(app, "assets/l10n/en.json"), json(en));

  const tables = join(app, "lib/l10n/core/core_tables.g.dart");
  write(tables, buildCoreTables(mod));
  dartFormat([tables]);

  const fixtures = join(app, "test/l10n/fixtures");
  manifest.core = Object.fromEntries(
    Object.keys(CORE).map((name) => [coreFile(name), sha256(coreFile(name))]),
  );
  write(join(fixtures, "catalog_manifest.json"), json(manifest));
  write(join(fixtures, "plurals.json"), lines(pluralFixtures(mod)));
  write(join(fixtures, "fill.json"), lines(fillFixtures(mod)));
  write(join(fixtures, "core_cases.json"), lines(coreFixtures(mod)));
  console.log(
    `Done: ${manifest.total} keys per locale (` +
      Object.entries(manifest.sources)
        .map(([path, s]) => `${path.split("/").pop()} ${s.keys}`)
        .join(", ") +
      ").",
  );
}

main().catch((error) => {
  console.error(error.message ?? error);
  process.exit(1);
});
