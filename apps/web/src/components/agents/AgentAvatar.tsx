import { AgentAvatar as Avatar } from "@lonora/ui-web";
import type { Agent } from "../../lib/api";
export function AgentAvatar({agent,working=false}:{agent:Agent;working?:boolean}){return <Avatar name={agent.name} color={agent.color} shape={agent.avatar} working={working}/>;}
