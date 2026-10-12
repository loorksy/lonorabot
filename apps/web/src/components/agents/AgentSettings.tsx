import { useState } from "react";
import { Trans } from "@lingui/react/macro";
import type { Agent } from "../../lib/api";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
export function AgentSettings({agent,onClose}:{agent:Agent;onClose:()=>void}){const {refresh}=useClient();const [instructions,setInstructions]=useState(agent.instructions);const [paused,setPaused]=useState(agent.paused);const [error,setError]=useState<unknown>();const [saving,setSaving]=useState(false);
return <div className="modal-backdrop"><form className="modal" onSubmit={async e=>{e.preventDefault();setSaving(true);try{await api.patch(`/agents/${agent.id}`,{instructions,paused});refresh();onClose();}catch(err){setError(err);}finally{setSaving(false);}}}><h2>{agent.name}</h2><label><Trans>Instructions</Trans><textarea rows={8} value={instructions} onChange={e=>setInstructions(e.target.value)}/></label><label className="check"><input type="checkbox" checked={paused} onChange={e=>setPaused(e.target.checked)}/><Trans>Pause agent and scheduled work</Trans></label>{error!=null&&<p role="alert">{userError(error)}</p>}<div className="actions"><button type="button" onClick={onClose}><Trans>Close</Trans></button><button className="primary" disabled={saving}><Trans>Save</Trans></button></div></form></div>;}
