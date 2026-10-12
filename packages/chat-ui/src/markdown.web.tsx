import { useRef,useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { t } from "@lingui/core/macro";
import { closeUnterminatedFence,sanitizeMarkdownUrl,type ChatMarkdownProps } from "./markdown";
import { MarkdownTable } from "./markdown-table";
import { CopyIcon,CheckIcon } from "./icons";
import "./markdown.web.css";
import "./markdown-table.css";
export function ChatMarkdown({children,streaming=false}:ChatMarkdownProps){
  const container=useRef<HTMLDivElement>(null);const[copied,setCopied]=useState(false);
  async function copy(){await navigator.clipboard.writeText(children);setCopied(true);window.setTimeout(()=>setCopied(false),1500);}
  return <div ref={container} className="rk-chat-markdown" dir="auto"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml urlTransform={url=>sanitizeMarkdownUrl(url,true)??""} components={{a:({children,href})=><a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,table:({children})=><MarkdownTable>{children}</MarkdownTable>,img:()=>null}}>{streaming?closeUnterminatedFence(children):children}</ReactMarkdown><button type="button" className="message-copy" onClick={()=>void copy()} aria-label={copied?t`Copied`:t`Copy message`}>{copied?<CheckIcon/>:<CopyIcon/>}</button></div>;
}
