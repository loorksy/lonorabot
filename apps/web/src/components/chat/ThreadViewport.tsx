import { useEffect,useState } from "react";
import { Trans } from "@lingui/react/macro";
import type { Agent,Message,Resource } from "../../lib/api";
import { api } from "../../lib/api";
import { useThreads } from "../../hooks/useThreads";
import { useClient } from "../../providers/ClientProvider";
import { userError } from "../../lib/user_error";
import { ThreadMessages } from "./ThreadMessages";
import { Composer } from "./Composer";
import { WorkingIndicator } from "./WorkingIndicator";
import { ToolActivity } from "./ToolActivity";
import { AgentActivity } from "./AgentActivity";
import { SubagentTasks } from "./SubagentTasks";
import { RecoveryNotice } from "./RecoveryNotice";
import { VoiceChatCard } from "../voice/VoiceChatCard";
import { FilePreviewPanel } from "../common/FilePreviewPanel";
export function ThreadViewport({threadId,agentId,agents}:{threadId:string;agentId:string;agents:Agent[]}){const thread=useThreads(undefined,threadId);const {events,revision}=useClient();const [reply,setReply]=useState<Message|null>(null);const [artifacts,setArtifacts]=useState<Resource[]>([]);const [preview,setPreview]=useState<Resource|null>(null);useEffect(()=>{void api.get<Resource[]>(`/artifacts?thread_id=${threadId}`).then(setArtifacts);},[threadId,revision]);const local=events.filter(e=>e.thread_id===threadId);const active=thread.runs.find(r=>["queued","leased","running","waiting_input","waiting_takeover"].includes(r.status));const working=!!active&&["queued","leased","running"].includes(active.status);
return <section className="thread-view"><div className="thread-status"><WorkingIndicator run={active??thread.runs[0]}/>{active?.status==="waiting_takeover"&&<button onClick={()=>void thread.resume(active.id)}><Trans>Resume</Trans></button>}</div><RecoveryNotice events={local}/>{thread.error!=null&&<p role="alert">{userError(thread.error)}</p>}<ThreadMessages messages={thread.messages} agents={agents} artifacts={artifacts} onReply={setReply} onPreview={setPreview} onOlder={()=>void thread.older()}/><div className="thread-progress"><AgentActivity events={local}/><ToolActivity events={local}/><SubagentTasks runs={thread.runs}/></div>{agentId&&<VoiceChatCard agentId={agentId} threadId={threadId} messages={thread.messages}/>}<Composer threadId={threadId} working={working} reply={reply} onClearReply={()=>setReply(null)} onSend={thread.send} onCancel={()=>{if(active)void thread.cancel(active.id);}}/>{preview&&<FilePreviewPanel artifact={preview} onClose={()=>setPreview(null)}/>}</section>;}
