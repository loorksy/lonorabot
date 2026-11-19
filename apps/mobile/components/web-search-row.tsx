// «البحث في الويب» in the «+» sheet, as Web's tools sheet: the chat's own option
// (PUT /threads/{id}/options); on, the agent gathers sources before replying.
import type { Thread, ThreadOptions } from "@lonora/contracts";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { useSession } from "../lib/session";
import { useTheme } from "../lib/theme";
import { Icon } from "./shell/icon";
import { Row, Switch } from "./shell/kit";

export function WebSearchRow({
  threadId,
  initial,
  onChange,
}: {
  threadId: string;
  initial: boolean;
  onChange: (options: ThreadOptions) => void;
}) {
  const { t, errorText } = useSession();
  const { c } = useTheme();
  const [on, setOn] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const touched = useRef(false);
  // As Web: the switch shows the server's value, not the screen's copy that may be older.
  useEffect(() => {
    let live = true;
    api
      .get<Thread>(`/threads/${encodeURIComponent(threadId)}`)
      .then((row) => {
        if (live && !touched.current) setOn(Boolean(row.options?.web_search));
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [threadId]);
  return (
    <Row
      testID="web-search-row"
      lead={<Icon name="search" size={22} color={c.text} />}
      title={t("webSearch")}
      sub={error ?? (on ? t("webSearchOn") : undefined)}
      last
      trailing={
        <Switch
          label={t("webSearch")}
          value={on}
          onChange={(next) => {
            touched.current = true;
            setOn(next);
            setError(null);
            void api
              .put<{ options?: ThreadOptions }>(
                `/threads/${encodeURIComponent(threadId)}/options`,
                { web_search: next },
              )
              .then((row) => {
                const options = { web_search: Boolean(row.options?.web_search) };
                setOn(options.web_search);
                onChange(options);
              })
              .catch((reason) => {
                setOn(!next);
                setError(errorText(reason));
              });
          }}
        />
      }
    />
  );
}
