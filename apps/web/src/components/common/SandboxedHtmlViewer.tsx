import { t } from "@lingui/core/macro";
export function SandboxedHtmlViewer({url}:{url:string}){return <iframe className="document-preview" title={t`Isolated document preview`} sandbox="" referrerPolicy="no-referrer" src={url}/>;}
