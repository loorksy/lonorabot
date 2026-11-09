import type { AgentLiveState } from "@lonora/contracts";
import { useCallback, useEffect, useState } from "react";
import { useClient } from "../providers/ClientProvider";
import { api } from "./api";

// One read per agent and runtime revision, however many views show the state.
const reads = new Map<string, Promise<AgentLiveState>>();

function read(agentId: string, revision: number, force = false): Promise<AgentLiveState> {
  const key = `${agentId}:${revision}`;
  const cached = reads.get(key);
  if (cached && !force) return cached;
  const request = api.get<AgentLiveState>(`/agents/${encodeURIComponent(agentId)}/state`);
  reads.set(key, request);
  request.catch(() => reads.delete(key));
  // Keep the map small: older revisions are never read again.
  if (reads.size > 32) reads.delete(reads.keys().next().value as string);
  return request;
}

/** The agent's live state (lonora_db.agent_state), refreshed by every runtime revision. */
export function useAgentLiveState(agentId: string | null | undefined) {
  const { revision } = useClient();
  const [state, setState] = useState<AgentLiveState | null>(null);
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    if (!agentId) return;
    let live = true;
    void read(agentId, revision)
      .then((next) => {
        if (live) {
          setState(next);
          setError(undefined);
        }
      })
      .catch((caught: unknown) => {
        if (live) setError(caught);
      });
    return () => {
      live = false;
    };
  }, [agentId, revision]);
  const reload = useCallback(async () => {
    if (!agentId) return;
    try {
      setState(await read(agentId, revision, true));
      setError(undefined);
    } catch (caught) {
      setError(caught);
    }
  }, [agentId, revision]);
  return {
    state: state && agentId && state.agent_id === agentId ? state : null,
    error,
    reload,
  };
}
