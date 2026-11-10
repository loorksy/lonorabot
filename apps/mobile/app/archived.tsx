// «المؤرشفة»: the archived rows (selection offers إلغاء الأرشفة), the note and the keep-archived setting.
import { archivedRows } from "@lonora/core";
import { Redirect } from "expo-router";
import { useEffect, useMemo } from "react";
import { View } from "react-native";
import { ArchivedContent } from "../components/shell/chat-list";
import { PageHeader, TopBar } from "../components/shell/chrome";
import { SelBar } from "../components/shell/selection";
import { Loading } from "../components/ui";
import { useLists } from "../lib/lists-state";
import { useSession } from "../lib/session";
import { useTheme } from "../lib/theme";

export default function Archived() {
  const { ready, owner, t } = useSession();
  const { c } = useTheme();
  const lists = useLists();
  const { end } = lists;
  useEffect(() => end, [end]);
  const keys = useMemo(() => archivedRows(lists.rows).map((row) => row.key), [lists.rows]);
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      {lists.selected ? (
        <TopBar solid>
          <SelBar visibleKeys={keys} />
        </TopBar>
      ) : (
        <PageHeader title={t("sh_archived")} />
      )}
      <ArchivedContent />
    </View>
  );
}
