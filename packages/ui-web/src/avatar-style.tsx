import { createContext,useContext,type ReactNode } from "react";
export type AvatarStyle="orb"|"circle"|"square"|"diamond";
const Context=createContext<AvatarStyle>("orb");
export function AvatarStyleProvider({value,children}:{value:AvatarStyle;children:ReactNode}) { return <Context.Provider value={value}>{children}</Context.Provider>; }
export function useAvatarStyle(){return useContext(Context);}
