import { useCallback,useState } from "react";
import { Trans } from "@lingui/react/macro";
import { useVoice } from "../../hooks/useVoice";
import type { Message } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { RealtimeVoice } from "./RealtimeVoice";
import { VoiceStatus } from "./VoiceStatus";
import { Transcript } from "./Transcript";
export function VoiceChatCard({agentId,threadId,messages}:{agentId:string;threadId:string;messages:Message[]}){const voice=useVoice(agentId,threadId);const [connected,setConnected]=useState(false);const [transportError,setTransportError]=useState<unknown>();const onError=useCallback((e:unknown)=>setTransportError(e),[]);return <section className="voice-card">{voice.session?<><VoiceStatus connected={connected} busy={!connected}/><button onClick={()=>void voice.interrupt()}><Trans>Interrupt</Trans></button><button onClick={()=>void voice.stop()}><Trans>End call</Trans></button><RealtimeVoice session={voice.session} onStatus={setConnected} onError={onError}/><Transcript messages={messages}/></>:<button disabled={voice.busy} onClick={()=>void voice.start()}><Trans>Start voice conversation</Trans></button>}{(voice.error??transportError)!=null&&<p role="alert">{userError(voice.error??transportError)}</p>}</section>;}
