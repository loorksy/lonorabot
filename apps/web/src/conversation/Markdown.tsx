import { t } from "@lingui/core/macro";
import { Icon } from "@lonora/ui-web";
import { Fragment, type ReactNode } from "react";

/* The reference's safe Markdown (md / mdInline / textBody, Desktop-37 5765-5803), built as React
   nodes so nothing in a message can inject markup. Fenced code blocks are explanation with
   «نسخ الكود» (Q36); links open in a new tab, noopener. */

const MD_BLOCK =
  /(^|\n)(```|#{1,3}\s|\s*[-*•]\s+\S|\s*\d+[.)]\s+\S|>\s?|\s*\|.*\|\s*\n\s*\|?\s*:?-{2,})/;
const escapeRe = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** `@name` for the known agent names (longest first) and «@الكل»; an LRM may precede it. */
export function mentionPattern(names: string[]): RegExp | null {
  const all = [...names.filter(Boolean), "الكل", "all"]
    .sort((a, b) => b.length - a.length)
    .map(escapeRe);
  return all.length ? new RegExp(`\\u200e?@(${all.join("|")})(?=$|[\\s.,،!?؟:؛)\\]])`, "g") : null;
}

/** Plain text with mentions marked and bare links clickable (the owner's own words: no
    Markdown, nothing else interpreted). */
export function richText(text: string, mentions: RegExp | null): ReactNode[] {
  const pattern = new RegExp(
    `(https?:\\/\\/[^\\s<]+[^\\s<.,،)])${mentions ? `|${mentions.source}` : ""}`,
    "g",
  );
  const out: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const at = match.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    out.push(
      match[1] ? (
        <a key={`l${at}`} href={match[1]} target="_blank" rel="noopener noreferrer" dir="ltr">
          {match[1]}
        </a>
      ) : (
        <span key={`m${at}`} className="mention" dir="auto">
          @{match[2]}
        </span>
      ),
    );
    last = at + match[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

type Token = { at: number; end: number; node: (key: string) => ReactNode };

/** Inline Markdown: `code`, **bold**, _em_, [text](https://…), bare links, @mentions. */
export function mdInline(text: string, mentions: RegExp | null): ReactNode[] {
  const tokens: Token[] = [];
  const claim = (re: RegExp, node: (m: RegExpMatchArray, key: string) => ReactNode, lead = 0) => {
    for (const m of text.matchAll(re)) {
      const at = (m.index ?? 0) + (lead ? (m[lead]?.length ?? 0) : 0);
      const end = (m.index ?? 0) + m[0].length;
      if (tokens.some((tok) => at < tok.end && end > tok.at)) continue;
      tokens.push({ at, end, node: (key) => node(m, key) });
    }
  };
  claim(/`([^`\n]+)`/g, (m, key) => (
    <code key={key} dir="ltr">
      {m[1]}
    </code>
  ));
  claim(/\*\*([^*\n]+)\*\*/g, (m, key) => <strong key={key}>{m[1]}</strong>);
  claim(/(^|[\s(])_([^_\n]+)_(?=[\s.,،)!?؟]|$)/g, (m, key) => <em key={key}>{m[2]}</em>, 1);
  claim(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, (m, key) => (
    <a key={key} href={m[2]} target="_blank" rel="noopener noreferrer">
      {m[1]}
    </a>
  ));
  claim(
    /(^|[\s(])(https?:\/\/[^\s<]+[^\s<.,،)])/g,
    (m, key) => (
      <a key={key} href={m[2]} target="_blank" rel="noopener noreferrer" dir="ltr">
        {m[2]}
      </a>
    ),
    1,
  );
  if (mentions)
    claim(new RegExp(mentions.source, "g"), (m, key) => (
      <span key={key} className="mention" dir="auto">
        @{m[1]}
      </span>
    ));
  tokens.sort((a, b) => a.at - b.at);
  const out: ReactNode[] = [];
  let last = 0;
  for (const tok of tokens) {
    if (tok.at > last) out.push(text.slice(last, tok.at));
    out.push(tok.node(`i${tok.at}`));
    last = tok.end;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function lines(parts: string[], mentions: RegExp | null) {
  return parts.map((line, index) => (
    // biome-ignore lint/suspicious/noArrayIndexKey: lines of one immutable text
    <Fragment key={index}>
      {index > 0 && <br />}
      {mdInline(line, mentions)}
    </Fragment>
  ));
}

export function CodeBlock({ lang, code }: { lang: string; code: string }) {
  return (
    <div className="code">
      <div className="code-head">
        <span>{lang || "code"}</span>
        <button
          type="button"
          className="code-copy"
          aria-label={t`Copy code`}
          onClick={(event) => {
            const button = event.currentTarget;
            void navigator.clipboard?.writeText(code).then(
              () => button.dispatchEvent(new CustomEvent("lonora:copied", { bubbles: true })),
              () => undefined,
            );
          }}
        >
          <Icon name="copy" />
          <span>{t({ message: "Copy", context: "code" })}</span>
        </button>
      </div>
      <pre dir="ltr">
        <code>{code}</code>
      </pre>
    </div>
  );
}

/** Block Markdown: fenced code, tables, headings, lists, quotes and paragraphs. */
export function md(source: string, mentions: RegExp | null): ReactNode[] {
  const L = String(source).replace(/\r/g, "").split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  const isRow = (l?: string) => /^\s*\|.*\|\s*$/.test(l ?? "");
  const isSep = (l?: string) => /^\s*\|?\s*:?-{2,}/.test(l ?? "");
  const special = (j: number) =>
    /^(```|#{1,3}\s|\s*[-*•]\s+\S|\s*\d+[.)]\s+\S|>\s?)/.test(L[j]) ||
    (isRow(L[j]) && isSep(L[j + 1]));
  const cells = (l: string) =>
    l
      .trim()
      .replace(/^\||\|$/g, "")
      .split("|")
      .map((c) => c.trim());
  while (i < L.length) {
    const l = L[i];
    const key = `b${i}`;
    if (/^```/.test(l)) {
      const lang = l.slice(3).trim();
      const buf: string[] = [];
      i++;
      while (i < L.length && !/^```/.test(L[i])) buf.push(L[i++]);
      i++;
      out.push(<CodeBlock key={key} lang={lang} code={buf.join("\n")} />);
      continue;
    }
    if (isRow(l) && isSep(L[i + 1])) {
      const head = cells(l);
      i += 2;
      const rows: string[][] = [];
      while (i < L.length && isRow(L[i])) rows.push(cells(L[i++]));
      out.push(
        <div key={key} className="md-table">
          <table>
            <thead>
              <tr>
                {head.map((h, n) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: table cells by position
                  <th key={n}>{mdInline(h, mentions)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, r) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: table rows by position
                <tr key={r}>
                  {row.map((c, n) => (
                    // biome-ignore lint/suspicious/noArrayIndexKey: table cells by position
                    <td key={n}>{mdInline(c, mentions)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    const heading = l.match(/^(#{1,3})\s/);
    if (heading) {
      out.push(
        <p key={key} className={`md-h h${heading[1].length}`}>
          {mdInline(l.replace(/^#+\s*/, ""), mentions)}
        </p>,
      );
      i++;
      continue;
    }
    if (/^\s*[-*•]\s+\S/.test(l)) {
      const items: string[] = [];
      while (i < L.length && /^\s*[-*•]\s+\S/.test(L[i]))
        items.push(L[i++].replace(/^\s*[-*•]\s+/, ""));
      out.push(
        <ul key={key}>
          {items.map((x, n) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: list items by position
            <li key={n}>{mdInline(x, mentions)}</li>
          ))}
        </ul>,
      );
      continue;
    }
    if (/^\s*\d+[.)]\s+\S/.test(l)) {
      const items: string[] = [];
      while (i < L.length && /^\s*\d+[.)]\s+\S/.test(L[i]))
        items.push(L[i++].replace(/^\s*\d+[.)]\s+/, ""));
      out.push(
        <ol key={key}>
          {items.map((x, n) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: list items by position
            <li key={n}>{mdInline(x, mentions)}</li>
          ))}
        </ol>,
      );
      continue;
    }
    if (/^>\s?/.test(l)) {
      const q: string[] = [];
      while (i < L.length && /^>\s?/.test(L[i])) q.push(L[i++].replace(/^>\s?/, ""));
      out.push(<blockquote key={key}>{lines(q, mentions)}</blockquote>);
      continue;
    }
    if (!l.trim()) {
      i++;
      continue;
    }
    const buf: string[] = [];
    while (i < L.length && L[i].trim() && !special(i)) buf.push(L[i++]);
    out.push(<p key={key}>{lines(buf, mentions)}</p>);
  }
  return out;
}

/** The text of a bubble: rich blocks when an agent's text has structure, else the inline layout. */
export function TextBody({
  text,
  agent,
  markdown = true,
  mentions,
  caret,
}: {
  text: string;
  agent: boolean;
  markdown?: boolean;
  mentions: RegExp | null;
  caret?: boolean;
}) {
  const end = caret ? <span className="caret" aria-hidden="true" /> : null;
  if (agent && markdown && MD_BLOCK.test(text))
    return (
      <div className="md">
        {md(text, mentions)}
        {end}
      </div>
    );
  return (
    <span className="text">
      {agent && markdown ? mdInline(text, mentions) : richText(text, mentions)}
      {end}
    </span>
  );
}
