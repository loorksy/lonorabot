import { t } from "@lingui/core/macro";
import { type ReactNode, useRef, useState } from "react";
import { CheckIcon, CopyIcon } from "./icons";
export function MarkdownTable({ children }: { children: ReactNode }) {
  const table = useRef<HTMLTableElement>(null);
  const [copied, setCopied] = useState(false);
  async function copy() {
    const rows = [...(table.current?.rows ?? [])]
      .map((row) => [...row.cells].map((cell) => cell.textContent ?? "").join("\t"))
      .join("\n");
    await navigator.clipboard.writeText(rows);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }
  return (
    <div className="markdown-table-wrap">
      <button
        type="button"
        onClick={() => void copy()}
        aria-label={copied ? t`Copied` : t`Copy table`}
      >
        {copied ? <CheckIcon /> : <CopyIcon />}
      </button>
      <div className="table-scroll">
        <table ref={table}>{children}</table>
      </div>
    </div>
  );
}
