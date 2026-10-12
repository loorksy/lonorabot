import { useEffect,useState } from "react";
import { Trans } from "@lingui/react/macro";
import { auth,type Owner } from "./lib/auth";
import { onboardingStatus } from "./lib/bootstrap";
import { ApiError } from "./lib/api";
import { userError } from "./lib/user_error";
import { ClientProvider } from "./providers/ClientProvider";
import { Auth } from "./pages/Auth";
import { Onboarding } from "./pages/Onboarding";
import { Shell } from "./pages/Shell";
export default function App(){const [owner,setOwner]=useState<Owner|null>(null);const [initialized,setInitialized]=useState<boolean>();const [error,setError]=useState<unknown>();useEffect(()=>{void onboardingStatus().then(async status=>{setInitialized(status.owner_initialized);if(status.owner_initialized)try{setOwner(await auth.session());}catch(e){if(!(e instanceof ApiError&&e.status===401))setError(e);}}).catch(setError);},[]);if(error!=null)return <main className="auth-card"><p role="alert">{userError(error)}</p><button onClick={()=>location.reload()}><Trans>Retry</Trans></button></main>;if(initialized===undefined)return <main className="auth-card" role="status"><Trans>Opening workspace…</Trans></main>;if(!owner)return initialized?<Auth onLogin={setOwner}/>:<Onboarding onLogin={setOwner}/>;return <ClientProvider owner={owner}><Shell onLogout={()=>setOwner(null)}/></ClientProvider>;}
