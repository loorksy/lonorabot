import { type AvatarStateId, avatarState } from "@lonora/core";
import { memo } from "react";
import { cn } from "./lib/utils";
import { TradingAvatar } from "./trading-avatar";
import "./avatar.css";

/** Common cat appearance for saved identities, preserving the verified Super Bot marker. */
export const AgentAvatar = memo(function AgentAvatar({
  name,
  color: _color,
  shape = "orb",
  working = false,
  state,
  quality = "lite",
  superBot = false,
  superBotLabel,
  className,
}: {
  name: string;
  color?: string;
  shape?: string;
  working?: boolean;
  state?: AvatarStateId;
  quality?: "full" | "lite" | "flat";
  superBot?: boolean;
  superBotLabel?: string;
  className?: string;
}) {
  return (
    <span
      className={cn("lonora-agent-avatar", className)}
      data-shape={shape}
      data-working={working}
      data-super-bot={superBot}
      aria-hidden={superBot ? undefined : true}
      role="img"
      aria-label={superBot ? superBotLabel : undefined}
    >
      <TradingAvatar
        state={state ?? avatarState({ working })}
        label={name}
        size="100%"
        quality={quality}
        aria-hidden="true"
      />
      {superBot && (
        <svg className="lonora-super-bot-mark" viewBox="0 0 20 20" aria-hidden="true">
          <circle cx="10" cy="10" r="10" fill="#191717" />
          <path d="M4 7 7 9 10 4 13 9 16 7 14 14H6Z" fill="#f0c866" />
        </svg>
      )}
    </span>
  );
});
