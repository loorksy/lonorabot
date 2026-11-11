import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";
import { useToast } from "../shell/Toast";

/** Per-chat web search (Q33): a thread option on the server that the agent reads each turn. */
export function useThreadOptions(threadId: string) {
  const { revision } = useClient();
  const toast = useToast();
  const [webSearch, setWeb] = useState(false);
  useEffect(() => {
    void revision;
    let live = true;
    void api
      .get<{ options?: { web_search?: boolean } }>(`/threads/${encodeURIComponent(threadId)}`)
      .then((row) => live && setWeb(Boolean(row.options?.web_search)))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [threadId, revision]);
  const setWebSearch = useCallback(
    async (on: boolean) => {
      setWeb(on);
      try {
        const row = await api.put<{ options?: { web_search?: boolean } }>(
          `/threads/${encodeURIComponent(threadId)}/options`,
          { web_search: on },
        );
        setWeb(Boolean(row.options?.web_search));
      } catch (error) {
        setWeb(!on);
        toast(userError(error), { type: "error" });
      }
    },
    [threadId, toast],
  );
  return { webSearch, setWebSearch };
}
