import type { AgentLiveState } from "@lonora/contracts";
import { useFocusEffect } from "expo-router";
import { useCallback, useRef, useState } from "react";
import { AppState } from "react-native";
import { api } from "./api";

/**
 * One poll of an agent's live state for a thread screen, shared by the header's safety
 * pill and the background-activity strip: one request per refresh, not one per view.
 * It runs while the screen is focused and the app is active, every 15 seconds.
 */
export function useAgentLiveState(agentId: string | undefined) {
  const [state, setState] = useState<AgentLiveState | null>(null);
  const [error, setError] = useState<unknown>(null);
  const refreshRef = useRef<() => Promise<void>>(async () => undefined);
  useFocusEffect(
    useCallback(() => {
      if (!agentId) return undefined;
      let live = true;
      let timer: ReturnType<typeof setTimeout> | undefined;
      const refresh = async () => {
        clearTimeout(timer);
        try {
          if (AppState.currentState === "active") {
            const next = await api.get<AgentLiveState>(
              `/agents/${encodeURIComponent(agentId)}/state`,
            );
            if (live) {
              setState(next);
              setError(null);
            }
          }
        } catch (caught) {
          // The last known state stays on screen; the strip shows why it is stale.
          if (live) setError(caught);
        }
        if (live) {
          clearTimeout(timer);
          timer = setTimeout(() => void refresh(), 15000);
        }
      };
      refreshRef.current = refresh;
      void refresh();
      return () => {
        live = false;
        clearTimeout(timer);
        refreshRef.current = async () => undefined;
      };
    }, [agentId]),
  );
  const refresh = useCallback(() => refreshRef.current(), []);
  return {
    // Never show another agent's state while the thread switches agents.
    state: state && state.agent_id === agentId ? state : null,
    error,
    refresh,
  };
}
