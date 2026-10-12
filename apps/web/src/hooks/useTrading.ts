import { useEffect, useState } from "react";
import type { AccountSummary, Journal, Resource } from "../lib/api";
import { readAccount, readConnections, readJournal } from "../lib/trading";
import { useClient } from "../providers/ClientProvider";
export function useTrading(accountId: string) {
  const { revision } = useClient();
  const [connections, setConnections] = useState<Resource[]>([]);
  const [account, setAccount] = useState<AccountSummary>();
  const [journal, setJournal] = useState<Journal[]>([]);
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void revision;
    void Promise.all([readConnections(), readJournal()])
      .then(([c, j]) => {
        setConnections(c);
        setJournal(j);
      })
      .catch(setError);
  }, [revision]);
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void accountId;
    setAccount(undefined);
  }, [accountId]);
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void revision;
    if (!accountId) return;
    let live = true;
    readAccount(accountId)
      .then((a) => {
        if (live) {
          setAccount(a);
          setError(undefined);
        }
      })
      .catch((e) => {
        if (live) setError(e);
      });
    return () => {
      live = false;
    };
  }, [accountId, revision]);
  return { connections, account, journal, error };
}
