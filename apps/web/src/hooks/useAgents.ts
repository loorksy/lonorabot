import { useEffect,useState } from "react";
import { api,type Agent } from "../lib/api";
import { useClient } from "../providers/ClientProvider";
export function useAgents(){const {revision,refresh}=useClient();const [agents,setAgents]=useState<Agent[]>([]);const [error,setError]=useState<unknown>();
useEffect(()=>{let live=true;api.get<Agent[]>("/agents").then(v=>{if(live){setAgents(v);setError(undefined);}}).catch(e=>{if(live)setError(e);});return()=>{live=false;};},[revision]);
return {agents,error,create:async(name:string,avatar:string,color:string)=>{const agent=await api.post<Agent>("/agents",{name,avatar,color});refresh();return agent;},update:async(id:string,body:Partial<Agent>)=>{await api.patch(`/agents/${id}`,body);refresh();},remove:async(id:string)=>{await api.delete(`/agents/${id}`);refresh();}};
}
