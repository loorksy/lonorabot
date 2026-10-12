import type { Message } from "./api";
const cache=new Map<string,Message[]>();
export function cachedThread(id:string){return cache.get(id)??[];}
export function storeThread(id:string,messages:Message[]){cache.set(id,[...messages].sort((a,b)=>a.seq-b.seq));if(cache.size>50)cache.delete(cache.keys().next().value??"");}
export function clearThreadCache(){cache.clear();}
