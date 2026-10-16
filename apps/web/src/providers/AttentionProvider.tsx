import type { AttentionNotification } from "@lonora/contracts";
import { createContext, type ReactNode, useContext, useEffect, useState } from "react";
import { api } from "../lib/api";

type Attention = {
  items: AttentionNotification[];
  error: unknown;
  seen: (id: string) => Promise<void>;
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
  const [error, setError] = useState<unknown>();
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
    let active = true;
    void api
      .get<AttentionNotification[]>("/attention")
      .then((rows) => {
        if (active) {
          setItems(rows);
          setError(undefined);
        }
      })
      .catch((cause) => {
        if (active) setError(cause);
      });
    return () => {
      active = false;
    };
  }, [revision]);
  return (
    <Context.Provider
      value={{
        items,
        error,
        seen: async (id) => {
          await api.post("/attention/seen", { notification_id: id });
          setItems((rows) => rows.filter((row) => row.id !== id));
        },
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
