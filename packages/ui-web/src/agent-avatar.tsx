import { type AvatarStateId, avatarState, resolveAvatarColor } from "@lonora/core";
import { memo } from "react";
import { cn } from "./lib/utils";
import { TradingAvatar } from "./trading-avatar";
import "./avatar.css";

/** Retains saved identity/colour and the verified "trades on its own" marker across existing surfaces. */
export const AgentAvatar = memo(function AgentAvatar({
  name,
  identity,
  color = "#7c83fd",
  shape = "orb",
  working = false,
  state,
  quality = "lite",
  tradesOnItsOwn = false,
  tradesOnItsOwnLabel,
  className,
}: {
  name: string;
  identity?: string;
  color?: string;
  shape?: string;
  working?: boolean;
  state?: AvatarStateId;
  quality?: "full" | "lite" | "flat";
  tradesOnItsOwn?: boolean;
  tradesOnItsOwnLabel?: string;
  className?: string;
}) {
  return (
    <span
      className={cn("lonora-agent-avatar", className)}
      data-shape={shape}
      data-working={working}
      data-on-its-own={tradesOnItsOwn}
      aria-hidden={tradesOnItsOwn ? undefined : true}
      role="img"
      aria-label={tradesOnItsOwn ? tradesOnItsOwnLabel : undefined}
    >
      <TradingAvatar
        identity={identity || name}
        face={shape}
        state={state ?? avatarState({ working })}
        primaryColor={resolveAvatarColor(name, color).hex}
        size="100%"
        quality={quality}
        aria-hidden="true"
      />
      {tradesOnItsOwn && (
        <svg className="lonora-on-its-own-mark" viewBox="0 0 20 20" aria-hidden="true">
          <circle cx="10" cy="10" r="10" fill="#191717" />
          <path d="M4 7 7 9 10 4 13 9 16 7 14 14H6Z" fill="#f0c866" />
        </svg>
      )}
    </span>
  );
});
