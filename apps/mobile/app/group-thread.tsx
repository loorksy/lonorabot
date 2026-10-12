import { Redirect, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { ErrorNotice, Loading, Screen } from "../components/ui";
import { groups } from "../lib/groups";
import { useSession } from "../lib/session";
import Conversation from "./thread";

export default function GroupThread() {
  const { groupId } = useLocalSearchParams<{ groupId: string }>();
  const { ready, owner, errorText } = useSession();
  const [threadId, setThreadId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!owner || !groupId) return;
    let live = true;
    setThreadId(null);
    void groups
      .get(groupId)
      .then(groups.conversation)
      .then((thread) => {
        if (live) setThreadId(thread.id);
      })
      .catch((reason) => {
        if (live) setError(errorText(reason));
      });
    return () => {
      live = false;
    };
  }, [groupId, owner, errorText]);
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
