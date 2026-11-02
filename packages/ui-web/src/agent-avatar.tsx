import { type AvatarStateId, avatarState, resolveAvatarColor } from "@lonora/core";
import { memo } from "react";
import { cn } from "./lib/utils";
import { TradingAvatar } from "./trading-avatar";
import "./avatar.css";

/** Retains saved identity/colour and the verified Super Bot marker across existing surfaces. */
export const AgentAvatar = memo(function AgentAvatar({
  name,
  color = "#7c83fd",
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
        primaryColor={resolveAvatarColor(name, color).hex}
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
