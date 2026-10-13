// Real persistent market scenes replace the template's computer destination.
import type { Resource } from "@lonora/contracts";
import { Redirect, useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { AppState, ScrollView, Text, View } from "react-native";
import { ActionMenu } from "../components/action-menu";
import { CandlestickChart } from "../components/candlestick-chart";
import { HeaderButton } from "../components/header-button";
import { NativeSymbol } from "../components/native-symbol";
import { SettingsGroup, SettingsRow } from "../components/settings-group";
import { SheetHeader } from "../components/sheet-header";
import { Button, colors, ErrorNotice, Loading, Screen } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { type Chart, type ChartScene, readCharts, readScene, requestRefresh } from "../lib/charts";
import { useSession } from "../lib/session";

type Connection = Resource<{ account_id: string; provider: string; enabled: boolean }>;
export default function Charts() {
  const { threadId, botId } = useLocalSearchParams<{ threadId?: string; botId?: string }>();
  const { ready, owner, rtl, locale, t, errorText } = useSession();
  const router = useRouter();
  const [charts, setCharts] = useState<Chart[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [scene, setScene] = useState<ChartScene | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [account, setAccount] = useState("");
  const [symbols, setSymbols] = useState<string[]>([]);
  const [symbol, setSymbol] = useState("");
  const [timeframe, setTimeframe] = useState("1h");
  const [picker, setPicker] = useState<"account" | "symbol" | "timeframe" | null>(null);
  const load = useCallback(async () => {
    const rows = await readCharts(threadId);
    setCharts(rows);
    setSelected((old) => (old && rows.some((row) => row.id === old) ? old : (rows[0]?.id ?? null)));
    setLoading(false);
  }, [threadId]);
  useFocusEffect(
    useCallback(() => {
      if (!owner) return;
      let live = true;
      let timer: ReturnType<typeof setTimeout>;
      const tick = async () => {
        try {
          if (AppState.currentState === "active") await load();
        } catch (reason) {
          if (live) {
            setError(errorText(reason));
            setLoading(false);
          }
        }
        if (live) timer = setTimeout(() => void tick(), 5000);
      };
      void tick();
      return () => {
        live = false;
        clearTimeout(timer);
      };
    }, [owner, load, errorText]),
  );
  useEffect(() => {
    setScene(null);
    if (!selected || !owner) return;
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const value = await readScene(selected);
        if (live) {
          setScene(value);
          setError(null);
        }
      } catch (reason) {
        if (live)
          setError(
            reason instanceof ApiError && reason.code === "chart_initializing"
              ? t("chartInitializing")
              : errorText(reason),
          );
      }
      if (live) timer = setTimeout(() => void tick(), 5000);
    };
    void tick();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [selected, owner, errorText, t]);
  useEffect(() => {
    if (!creating || !owner) return;
    let live = true;
    void api
      .get<Connection[]>("/trading/connections")
      .then((rows) => {
        if (live) {
          const enabled = rows.filter((row) => row.payload.enabled);
          setConnections(enabled);
          setAccount((old) =>
            enabled.some((row) => row.id === old) ? old : (enabled[0]?.id ?? ""),
          );
        }
      })
      .catch((reason) => {
        if (live) setError(errorText(reason));
      });
    return () => {
      live = false;
    };
  }, [creating, owner, errorText]);
  useEffect(() => {
    setSymbols([]);
    setSymbol("");
    if (!account || !creating) return;
    let live = true;
    void api
      .get<string[]>(`/market/symbols?account_id=${encodeURIComponent(account)}`)
      .then((rows) => {
        if (live) {
          setSymbols(rows);
          setSymbol(rows[0] ?? "");
        }
      })
      .catch((reason) => {
        if (live) setError(errorText(reason));
      });
    return () => {
      live = false;
    };
  }, [account, creating, errorText]);
  const create = async () => {
    if (!account || !symbol || busy) return;
    setBusy(true);
    setError(null);
    try {
      const chart = await api.post<Chart>("/charts", {
        payload: { account_id: account, symbol, timeframe, indicators: [], annotations: [] },
        agent_id: botId ?? null,
        thread_id: threadId ?? null,
      });
      await load();
      setSelected(chart.id);
      setCreating(false);
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  };
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  const current = charts.find((row) => row.id === selected);
  return (
    <Screen>
      <SheetHeader
        title={t("charts")}
        action={creating ? t("save") : undefined}
        onAction={creating ? () => void create() : undefined}
        disabled={busy || !account || !symbol}
        onClose={creating ? () => setCreating(false) : undefined}
      />
      <ErrorNotice text={error} />
      {creating ? (
        <ScrollView contentContainerStyle={{ padding: 20, gap: 20 }}>
          <SettingsGroup>
            <SettingsRow
              title={t("brokerAccount")}
              value={
                connections.find((row) => row.id === account)?.payload.account_id ??
                t("chooseAccount")
              }
              onPress={() => setPicker("account")}
            />
            <SettingsRow
              title={t("symbol")}
              value={symbol || t("chooseSymbol")}
              disabled={!symbols.length}
              onPress={() => setPicker("symbol")}
            />
            <SettingsRow
              title={t("timeframe")}
              value={timeframe}
              onPress={() => setPicker("timeframe")}
            />
          </SettingsGroup>
          {!connections.length ? (
            <Text style={{ color: colors.secondary, textAlign: rtl ? "right" : "left" }}>
              {t("brokerMissing")}
            </Text>
          ) : null}
        </ScrollView>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, gap: 20 }}>
          <View
            style={{ flexDirection: rtl ? "row-reverse" : "row", alignItems: "center", gap: 8 }}
          >
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              style={{ flex: 1 }}
              contentContainerStyle={{ gap: 8 }}
            >
              {charts.map((chart) => (
                <Button
                  key={chart.id}
                  label={`${chart.payload.symbol} · ${chart.payload.timeframe}`}
                  secondary={selected !== chart.id}
                  onPress={() => setSelected(chart.id)}
                />
              ))}
            </ScrollView>
            <HeaderButton label={t("createChart")} onPress={() => setCreating(true)}>
              <NativeSymbol name="plus" />
            </HeaderButton>
          </View>
          {loading ? (
            <Loading />
          ) : current ? (
            <View style={{ gap: 16 }}>
              <View
                style={{
                  flexDirection: rtl ? "row-reverse" : "row",
                  alignItems: "center",
                  gap: 12,
                }}
              >
                <View style={{ flex: 1, gap: 4 }}>
                  <Text
                    style={{
                      color: colors.foreground,
                      fontWeight: "600",
                      fontSize: 24,
                      writingDirection: "ltr",
                    }}
                  >
                    {current.payload.symbol}
                  </Text>
                  <Text style={{ color: colors.secondary, fontSize: 13, writingDirection: "ltr" }}>
                    {current.payload.timeframe}
                  </Text>
                </View>
                <HeaderButton
                  label={t("refresh")}
                  disabled={busy}
                  onPress={() => {
                    setBusy(true);
                    void requestRefresh(current.id)
                      .catch((reason) => setError(errorText(reason)))
                      .finally(() => setBusy(false));
                  }}
                >
                  <NativeSymbol name="refresh" size={19} />
                </HeaderButton>
              </View>
              {scene ? (
                <>
                  <CandlestickChart scene={scene} />
                  {scene.quote ? (
                    <SettingsGroup title={t("quote")}>
                      <SettingsRow title={t("bid")} value={scene.quote.bid} />
                      <SettingsRow title={t("ask")} value={scene.quote.ask} />
                      <SettingsRow title={t("details")} value={scene.quote.source} />
                    </SettingsGroup>
                  ) : null}
                  <Text
                    style={{
                      color: colors.secondary,
                      fontSize: 12,
                      textAlign: rtl ? "right" : "left",
                    }}
                  >
                    {t("chartUpdated")} · {new Date(scene.updated_at).toLocaleString(locale)}
                  </Text>
                </>
              ) : !error ? (
                <Loading />
              ) : null}
              {current.thread_id && current.thread_id !== threadId ? (
                <Button
                  label={t("openConversation")}
                  secondary
                  onPress={() =>
                    router.push({ pathname: "/thread", params: { id: current.thread_id } })
                  }
                />
              ) : null}
            </View>
          ) : (
            <Text
              style={{ color: colors.secondary, padding: 16, textAlign: rtl ? "right" : "left" }}
            >
              {t("chartEmpty")}
            </Text>
          )}
        </ScrollView>
      )}
      <ActionMenu
        visible={picker !== null}
        onClose={() => setPicker(null)}
        actions={
          picker === "account"
            ? connections.map((row) => ({
                label: row.payload.account_id,
                icon: "chart",
                onPress: () => setAccount(row.id),
              }))
            : picker === "symbol"
              ? symbols.map((value) => ({
                  label: value,
                  icon: "chart",
                  onPress: () => setSymbol(value),
                }))
              : ["1m", "5m", "15m", "30m", "1h", "4h", "1d"].map((value) => ({
                  label: value,
                  icon: "clock",
                  onPress: () => setTimeframe(value),
                }))
        }
      />
    </Screen>
  );
}
