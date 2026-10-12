import { Component,type ReactNode } from "react";
import { Trans } from "@lingui/react/macro";
export class ErrorBoundary extends Component<{children:ReactNode},{failed:boolean}>{state={failed:false};static getDerivedStateFromError(){return {failed:true};}render(){return this.state.failed?<main className="auth-card"><h1><Trans>The page could not be displayed</Trans></h1><button onClick={()=>location.reload()}><Trans>Reload</Trans></button></main>:this.props.children;}}
