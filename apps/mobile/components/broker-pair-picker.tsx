import type { Resource } from "@lonora/contracts";
import { useEffect, useState } from "react";
import { AppState, FlatList, Linking, Modal, Pressable, Text, View } from "react-native";
import { api } from "../lib/api";
import { brokerIdentityLabel } from "../lib/broker-identity";
import { useSession } from "../lib/session";
import { SheetHeader } from "./sheet-header";
import { Button, colors, ErrorNotice, Field } from "./ui";
export type BrokerPair = { trading_account_id: string; trading_symbol: string };
export function BrokerPairPicker({
  value,
  onChange,
}: {
  value: BrokerPair;
  onChange: (pair: BrokerPair) => void;
}) {
  const { t, rtl, server, errorText } = useSession();
  const [connections, setConnections] = useState<Resource[]>([]);
  const [symbols, setSymbols] = useState<string[]>([]);
  const [sheet, setSheet] = useState<"account" | "symbol" | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    let live = true;
    const load = () => {
      void api
        .get<Resource[]>("/trading/connections")
        .then((rows) => {
          if (live) setConnections(rows.filter((row) => row.payload.enabled === true));
        })
        .catch((caught) => {
          if (live) setError(errorText(caught));
        });
    };
    load();
    const listener = AppState.addEventListener("change", (state) => {
      if (state === "active") load();
    });
    return () => {
      live = false;
      listener.remove();
    };
  }, [errorText]);
  useEffect(() => {
    setSymbols([]);
    setQuery("");
    setError(undefined);
    if (!value.trading_account_id) return;
    let live = true;
    setLoading(true);
    void api
      .get<string[]>(`/market/symbols?account_id=${encodeURIComponent(value.trading_account_id)}`)
      .then((rows) => {
        if (live) setSymbols(rows);
      })
      .catch((caught) => {
        if (live) setError(errorText(caught));
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [value.trading_account_id, errorText]);
  const account = connections.find((row) => row.id === value.trading_account_id);
  const options =
    sheet === "account"
      ? connections.map((row, index) => ({ id: row.id, label: brokerIdentityLabel(row, index, t) }))
      : symbols
          .filter((symbol) => symbol.toLowerCase().includes(query.toLowerCase()))
          .map((symbol) => ({ id: symbol, label: symbol }));
  return (
    <View style={{ gap: 12 }}>
      <Button
        label={
          account
            ? brokerIdentityLabel(account, connections.indexOf(account), t)
            : t("chooseBrokerAccount")
        }
        secondary
        onPress={() => setSheet("account")}
      />
      <Button
        label={value.trading_symbol || (loading ? t("connecting") : t("chooseTradingPair"))}
        secondary
        disabled={!account || loading}
        onPress={() => setSheet("symbol")}
      />
      <Text style={{ color: colors.secondary, textAlign: rtl ? "right" : "left" }}>
        {t("immutableTradingPair")}
      </Text>
      {!connections.length && (
        <Text style={{ color: colors.secondary }}>{t("connectBrokerFirst")}</Text>
      )}
      {!connections.length && (
        <Button
          label={t("openWebSettings")}
          secondary
          onPress={() => {
            void Linking.openURL(`${server}/app?settings=trading`).catch((caught) =>
              setError(errorText(caught)),
            );
          }}
        />
      )}
      <ErrorNotice text={error} />
      <Modal
        visible={sheet != null}
        transparent
        animationType="slide"
        onRequestClose={() => setSheet(null)}
      >
        <View style={{ flex: 1, backgroundColor: colors.overlay, justifyContent: "flex-end" }}>
          <Pressable
            style={{ flex: 1 }}
            onPress={() => setSheet(null)}
            accessibilityLabel={t("back")}
          />
          <View
            style={{
              backgroundColor: colors.background,
              borderTopLeftRadius: 24,
              borderTopRightRadius: 24,
              padding: 16,
              maxHeight: "75%",
              minHeight: 280,
            }}
          >
            <SheetHeader
              title={sheet === "account" ? t("brokerAccount") : t("chooseTradingPair")}
              onClose={() => setSheet(null)}
            />
            {sheet === "symbol" && (
              <Field
                label={t("searchBrokerSymbols")}
                value={query}
                onChangeText={setQuery}
                autoCapitalize="none"
              />
            )}
            <FlatList
              data={options}
              keyboardShouldPersistTaps="handled"
              keyExtractor={(row) => row.id}
              renderItem={({ item }) => (
                <Pressable
                  testID={`broker-choice-${item.id}`}
                  accessibilityRole="button"
                  accessibilityLabel={item.label}
                  onPress={() => {
                    onChange(
                      sheet === "account"
                        ? { trading_account_id: item.id, trading_symbol: "" }
                        : { ...value, trading_symbol: item.id },
                    );
                    setSheet(null);
                  }}
                  style={{ padding: 16, borderBottomWidth: 1, borderBottomColor: colors.border }}
                >
                  <Text style={{ color: colors.foreground, writingDirection: "ltr" }}>
                    {item.label}
                  </Text>
                </Pressable>
              )}
            />
          </View>
        </View>
      </Modal>
    </View>
  );
}
