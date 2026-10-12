import { Trans } from "@lingui/react/macro";
export function VoiceStatus({connected,busy}:{connected:boolean;busy:boolean}){return <span role="status" className="badge">{connected?<Trans>Listening · speak to interrupt</Trans>:busy?<Trans>Connecting microphone</Trans>:<Trans>Voice disconnected</Trans>}</span>;}
