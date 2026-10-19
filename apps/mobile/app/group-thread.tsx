import { Redirect, useLocalSearchParams } from "expo-router";
import { useEffect, useMemo, useRef, useState } from "react";
import { ErrorNotice, Loading, Screen } from "../components/ui";
import { conversationCache } from "../lib/conversation-cache";
import { groups } from "../lib/groups";
import { useSession } from "../lib/session";
import Conversation from "./thread";

export default function GroupThread() {
  const { groupId } = useLocalSearchParams<{ groupId: string }>();
  const { ready, owner, server, errorText } = useSession();
  const scope = useMemo(
    () => (owner ? conversationCache.activate(server, owner.id) : null),
    [server, owner],
  );
  const reportError = useRef(errorText);
  reportError.current = errorText;
  const [threadId, setThreadId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!owner || !groupId) return;
    let live = true;
    const key = `group:${groupId}`;
    setThreadId(conversationCache.get<string>(scope, key) ?? null);
    void groups
      .get(groupId)
      .then(groups.conversation)
      .then((thread) => {
        if (live && conversationCache.current(scope)) {
          conversationCache.set(scope, key, thread.id);
          setThreadId(thread.id);
          setError(null);
        }
      })
      .catch((reason) => {
        if (live) setError(reportError.current(reason));
      });
    return () => {
      live = false;
    };
  }, [groupId, owner, scope]);
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  if (error)
    return (
      <Screen>
        <ErrorNotice text={error} />
      </Screen>
    );
  return threadId ? <Conversation threadId={threadId} /> : <Loading />;
}
