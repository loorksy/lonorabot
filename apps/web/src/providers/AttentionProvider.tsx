import type { AttentionNotification } from "@lonora/contracts";
import { createContext, type ReactNode, useContext, useEffect, useState } from "react";
import { api } from "../lib/api";

type Attention = {
  items: AttentionNotification[];
  /** The open items have been read from the server at least once. */
  loaded: boolean;
  error: unknown;
  seen: (id: string) => Promise<void>;
  /** Read the open items again (after «تحديد الكل كمقروء»). */
  refresh: () => void;
};
const Context = createContext<Attention | null>(null);
export function AttentionProvider({
  revision,
  children,
}: {
  revision: number;
  children: ReactNode;
}) {
  const [items, setItems] = useState<AttentionNotification[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<unknown>();
  const [manual, setManual] = useState(0);
  useEffect(() => {
    const deadlines = items
      .filter((item) => item.parameters.valid_until)
      .map((item) => new Date(item.parameters.valid_until as string).getTime());
    if (!deadlines.length) return;
    const timer = setTimeout(
      () =>
        setItems((rows) =>
          rows.filter(
            (row) =>
              !row.parameters.valid_until ||
              (row.parameters.valid_until &&
                new Date(row.parameters.valid_until).getTime() > Date.now()),
          ),
        ),
      Math.max(0, Math.min(2_147_483_647, Math.min(...deadlines) - Date.now())),
    );
    return () => clearTimeout(timer);
  }, [items]);
  useEffect(() => {
    void revision;
    void manual;
    let active = true;
    void api
      .get<AttentionNotification[]>("/attention")
      .then((rows) => {
        if (active) {
          setItems(rows);
          setLoaded(true);
          setError(undefined);
        }
      })
      .catch((cause) => {
        if (active) setError(cause);
      });
    return () => {
      active = false;
    };
  }, [revision, manual]);
  return (
    <Context.Provider
      value={{
        items,
        loaded,
        error,
        seen: async (id) => {
          await api.post("/attention/seen", { notification_id: id });
          setItems((rows) => rows.filter((row) => row.id !== id));
        },
        refresh: () => setManual((value) => value + 1),
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useAttention() {
  const value = useContext(Context);
  if (!value) throw new Error("attention_context_missing");
  return value;
}
