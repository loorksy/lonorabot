import { useVoice } from "../../hooks/useVoice";
import type { Agent } from "../../lib/api";
import { CallCard } from "./CallCard";
/** A view of the globally owned call; navigating or minimizing never closes transport. */
export function VoiceChatCard({
  agents,
  onSettings,
  onOpenConversation,
}: {
  agents: Agent[];
  onSettings: () => void;
  onOpenConversation: () => void;
}) {
  const voice = useVoice();
  const target = voice.target;
  return (
    <CallCard
      onSettings={() => {
        voice.minimize();
        onSettings();
      }}
      onOpenConversation={onOpenConversation}
      onRetry={
        target
          ? () => {
              const agent = agents.find((row) => row.id === target.agentId);
              if (agent) void voice.start(agent, target.threadId || null);
            }
          : undefined
      }
    />
  );
}
