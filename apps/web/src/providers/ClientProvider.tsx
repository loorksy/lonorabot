import { createContext,useContext,useEffect,useMemo,useState,type ReactNode } from "react";
import type { Owner } from "../lib/auth";
import { useEvents } from "../hooks/useEvents";
type Client={owner:Owner;events:ReturnType<typeof useEvents>["events"];connected:boolean;revision:number;refresh:()=>void};
const Context=createContext<Client|null>(null);
export function ClientProvider({owner,children}:{owner:Owner;children:ReactNode}){const {events,connected}=useEvents(true);const [manual,setManual]=useState(0);const [tick,setTick]=useState(0);
useEffect(()=>{const timer=setInterval(()=>setTick(v=>v+1),15000);return()=>clearInterval(timer);},[]);
const value=useMemo(()=>({owner,events,connected,revision:manual+tick+(events.at(-1)?.cursor??0),refresh:()=>setManual(v=>v+1)}),[owner,events,connected,manual,tick]);return <Context.Provider value={value}>{children}</Context.Provider>;}
export function useClient(){const value=useContext(Context);if(!value)throw new Error("client_context_missing");return value;}
