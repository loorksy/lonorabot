import type { CSSProperties } from "react";
import { cn } from "./lib/utils";
export function AgentAvatar({
  name,
  color = "#7c83fd",
  shape = "orb",
  working = false,
  className,
}: {
  name: string;
  color?: string;
  shape?: string;
  working?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn("lonora-agent-avatar", className)}
      data-shape={shape}
      data-working={working}
      style={{ "--agent-color": color } as CSSProperties}
      aria-hidden="true"
    >
      <span>{name.slice(0, 1).toLocaleUpperCase()}</span>
    </span>
  );
}
