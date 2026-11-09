import { Plural, Trans } from "@lingui/react/macro";
import { Icon } from "@lonora/ui-web";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { queuedOutgoingCount, subscribeOutgoing } from "../lib/outgoing-messages";

/* NetworkStrip in the top bar: offline (amber, with the messages waiting) → reconnecting (the
   event stream is not back yet) → back (accent, 1.8s). `connected` is the live event stream. */
export type NetPhase = "on" | "off" | "connecting" | "back";
export function useNetworkPhase(connected: boolean): NetPhase {
  const [online, setOnline] = useState(() => navigator.onLine);
  const [phase, setPhase] = useState<NetPhase>(() => (navigator.onLine ? "on" : "off"));
  const wasConnected = useRef(connected);
  useEffect(() => {
    const changed = () => setOnline(navigator.onLine);
    window.addEventListener("online", changed);
    window.addEventListener("offline", changed);
    return () => {
      window.removeEventListener("online", changed);
      window.removeEventListener("offline", changed);
    };
  }, []);
  useEffect(() => {
    if (!online) {
      setPhase("off");
      wasConnected.current = false;
      return;
    }
    if (!connected) {
      // only a lost connection reconnects; the first connection of a session is silent
      setPhase((current) => (current === "off" || wasConnected.current ? "connecting" : current));
      wasConnected.current = false;
      return;
    }
    wasConnected.current = true;
    setPhase((current) => (current === "on" ? current : "back"));
    const timer = setTimeout(() => setPhase("on"), 1800);
    return () => clearTimeout(timer);
  }, [online, connected]);
  return phase;
}

export function NetworkStrip({ phase, ownerId }: { phase: NetPhase; ownerId: string }) {
  const queued = useSyncExternalStore(subscribeOutgoing, () => queuedOutgoingCount(ownerId));
  if (phase === "on") return null;
  if (phase === "off")
    return (
      <div className="net-strip off" role="status">
        <Icon name="wifiOff" />
        <span>
          <Trans>No internet connection</Trans>
          {queued > 0 && (
            <>
              {" · "}
              <Plural
                value={queued}
                one="one message waiting"
                two="two messages waiting"
                few="# messages waiting"
                many="# messages waiting"
                other="# messages waiting"
              />
            </>
          )}
        </span>
      </div>
    );
  if (phase === "connecting")
    return (
      <div className="net-strip wait" role="status">
        <span className="spin" aria-hidden="true" />
        <span>
          <Trans>Reconnecting…</Trans>
        </span>
      </div>
    );
  return (
    <div className="net-strip back" role="status">
      <Icon name="check" />
      <span>
        <Trans>Connection restored</Trans>
      </span>
    </div>
  );
}
