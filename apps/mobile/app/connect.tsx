import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { ScrollView, Text } from "react-native";
import { SheetHeader } from "../components/sheet-header";
import { Button, colors, ErrorNotice, Loading, Screen } from "../components/ui";
import { holdSetupToken, parseConnectLink } from "../lib/connect-link";
import { useSession } from "../lib/session";

// lonora://connect?server=…&token=…: connect this app to the owner's own Lonora after a confirmation.
export default function Connect() {
  const { ready, t, errorText, changeServer } = useSession();
  const params = useLocalSearchParams<{ server?: string; token?: string }>();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Closed before the switch finished («Not now», back): nothing more happens on its behalf.
  const open = useRef(true);
  useEffect(
    () => () => {
      open.current = false;
    },
    [],
  );
  if (!ready) return <Loading />;
  const link = parseConnectLink(params.server, params.token);
  return (
    <Screen>
      <SheetHeader title={t("connectTitle")} />
      <ScrollView contentContainerStyle={{ padding: 20, gap: 20 }}>
        <ErrorNotice text={link ? error : t("connectInvalid")} />
        {link ? (
          <>
            <Text style={{ color: colors.foreground, fontSize: 17, lineHeight: 28 }}>
              {t("connectAsk")}
            </Text>
            <Text
              selectable
              style={{
                color: colors.foreground,
                fontSize: 18,
                fontWeight: "600",
                writingDirection: "ltr",
              }}
            >
              {link.host}
            </Text>
            <Text style={{ color: colors.secondary, lineHeight: 24 }}>{t("connectHint")}</Text>
            <Button
              label={t("connectConfirm")}
              disabled={busy}
              onPress={() => {
                setBusy(true);
                void changeServer(link.server)
                  .then(() => {
                    if (!open.current) return;
                    holdSetupToken(link.server, link.token);
                    router.replace("/sign-in");
                  })
                  .catch((cause) => setError(errorText(cause)))
                  .finally(() => setBusy(false));
              }}
            />
          </>
        ) : null}
        <Button label={t("connectCancel")} onPress={() => router.replace("/")} />
      </ScrollView>
    </Screen>
  );
}
