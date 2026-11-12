/** Card text as web and mobile draw it (docs/genui.md): `**bold**` inline, and for a
 * Markdown node also paragraphs and `-`/`*`/`1.` lists. Never HTML, never a live link: a
 * `[label](url)` shows its label and a bare URL stays text, so a card cannot open anything
 * except through an `open` action the server checked. One parser, so both renderers agree. */

export type CardInline = { text: string; bold: boolean };
export type CardMarkdownBlock = {
  kind: "p" | "ul" | "ol";
  /** One entry per line of a paragraph, or per list item. */
  lines: CardInline[][];
};

/** The reference's inline Markdown in card text: `**bold**` only. */
export function cardInline(text: string): CardInline[] {
  const labelled = text.replace(/\[([^\]\n]+)\]\([^)\s]*\)/g, "$1");
  return labelled
    .split(/(\*\*[^*]+\*\*)/g)
    .filter((piece) => piece !== "")
    .map((piece) =>
      piece.startsWith("**") && piece.endsWith("**") && piece.length > 4
        ? { text: piece.slice(2, -2), bold: true }
        : { text: piece, bold: false },
    );
}

const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBER = /^\s*\d{1,3}[.)]\s+(.*)$/;

export function cardMarkdown(text: string): CardMarkdownBlock[] {
  const blocks: CardMarkdownBlock[] = [];
  let current: CardMarkdownBlock | null = null;
  for (const raw of text.split("\n")) {
    const line = raw.replace(/^\s*#{1,6}\s+/, "").trimEnd();
    if (!line.trim()) {
      current = null;
      continue;
    }
    const bullet = BULLET.exec(line);
    const number = bullet ? null : NUMBER.exec(line);
    const kind = bullet ? "ul" : number ? "ol" : "p";
    const body = bullet?.[1] ?? number?.[1] ?? line.trim();
    if (!current || current.kind !== kind) {
      current = { kind, lines: [] };
      blocks.push(current);
    }
    current.lines.push(cardInline(body));
  }
  return blocks;
}
