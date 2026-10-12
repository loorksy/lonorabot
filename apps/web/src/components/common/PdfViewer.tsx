import { t } from "@lingui/core/macro";
export function PdfViewer({url}:{url:string}){return <iframe className="document-preview" title={t`PDF preview`} src={url}/>;}
