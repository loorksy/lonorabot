// Real persistent market scenes replace the template's computer destination.
import type { Agent, Resource } from "@lonora/contracts";
import { Redirect, useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { AppState, ScrollView, Text, View } from "react-native";
import { ActionMenu } from "../components/action-menu";
import { ChartRenderer } from "../components/chart-renderer";
import { HeaderButton } from "../components/header-button";
import { NativeSymbol } from "../components/native-symbol";
import { SettingsGroup, SettingsRow } from "../components/settings-group";
import { SheetHeader } from "../components/sheet-header";
import { Button, colors, ErrorNotice, Loading, Screen } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { brokerIdentityLabel } from "../lib/broker-identity";
import {
  CHART_TIMEFRAMES,
  type Chart,
  type ChartScene,
  readCharts,
  readScene,
  requestRefresh,
  subscribeChartEvents,
} from "../lib/charts";
import { useSession } from "../lib/session";

type Connection = Resource<{ account_id: string; provider: string; enabled: boolean }>;
export type ChartWorkspaceProps = {
  threadId?: string;
  botId?: string;
  chartId?: string;
  embedded?: boolean;
  onEscape?: () => void;
};
export default function Charts() {
  const params = useLocalSearchParams<{ threadId?: string; botId?: string; chartId?: string }>();
  return (
    <ChartWorkspace
      key={`${params.threadId ?? ""}:${params.botId ?? ""}:${params.chartId ?? ""}`}
      {...params}
    />
  );
}
export function ChartWorkspace({
  threadId,
  botId,
  chartId,
  embedded = false,
  onEscape,
}: ChartWorkspaceProps) {
  const { ready, owner, server, rtl, locale, t, errorText } = useSession();
  const router = useRouter();
  const labelsRef = useRef({ t, errorText });
  labelsRef.current = { t, errorText };
  const [agent, setAgent] = useState<Agent | null>(null);
  useEffect(() => {
    setAgent(null);
    if (!botId || !owner) return;
    let live = true;
    void api
      .get<Agent>(`/agents/${encodeURIComponent(botId)}`)
      .then((row) => {
        if (live) setAgent(row);
      })
      .catch((reason) => {
        if (live) setError(labelsRef.current.errorText(reason));
      });
    return () => {
      live = false;
    };
  }, [botId, owner]);
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
  const sceneRefresh = useRef<(() => void) | null>(null);
  const connectionRefresh = useRef<(() => void) | null>(null);
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const load = useCallback(async () => {
    const all = await readCharts(threadId);
    const rows =
      botId && !agent
        ? []
        : all.filter(
            (row) =>
              !agent?.trading_account_id ||
              (row.payload.account_id === agent.trading_account_id &&
                row.payload.symbol === agent.trading_symbol &&
                (!row.agent_id || row.agent_id === agent.id)),
          );
    setCharts(rows);
    setSelected((old) =>
      old && rows.some((row) => row.id === old)
        ? old
        : (rows.find((row) => row.id === chartId)?.id ?? rows[0]?.id ?? null),
    );
    setLoading(false);
  }, [threadId, botId, agent, chartId]);
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
            setError(labelsRef.current.errorText(reason));
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
    }, [owner, load]),
  );
  useEffect(() => {
    setScene(null);
    if (!selected || !owner) return;
    let live = true;
    let pending = false;
    let dirty = false;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      dirty = true;
      if (pending || !live || AppState.currentState !== "active") return;
      pending = true;
      dirty = false;
      try {
        const value = await readScene(selected);
        if (live) {
          setScene((old) =>
            old?.chart_id === value.chart_id &&
            (old.revision > value.revision || old.scene_version > value.scene_version)
              ? old
              : value,
          );
          setError(null);
        }
      } catch (reason) {
        if (live)
          setError(
            reason instanceof ApiError && reason.code === "chart_initializing"
              ? labelsRef.current.t("chartInitializing")
              : labelsRef.current.errorText(reason),
          );
      } finally {
        pending = false;
        if (live && dirty) void refresh();
      }
    };
    const request = () => {
      void refresh();
    };
    sceneRefresh.current = request;
    const tick = () => {
      request();
      if (live) timer = setTimeout(tick, 5000);
    };
    const state = AppState.addEventListener("change", (value) => {
      if (value === "active") request();
    });
    tick();
    return () => {
      live = false;
      clearTimeout(timer);
      state.remove();
      if (sceneRefresh.current === request) sceneRefresh.current = null;
    };
  }, [selected, owner]);
  useEffect(() => {
    if (!owner || !server) return;
    return subscribeChartEvents(
      server,
      (event) => {
        if (event.kind === "cloud_charts.scene_updated") {
          if (event.payload.id === selectedRef.current) sceneRefresh.current?.();
        } else if (event.kind.startsWith("cloud_charts.")) {
          void load().catch((reason) => setError(labelsRef.current.errorText(reason)));
        } else if (event.kind === "broker_identity.updated") {
          connectionRefresh.current?.();
        }
      },
      () => {
        sceneRefresh.current?.();
        connectionRefresh.current?.();
        void load().catch((reason) => setError(labelsRef.current.errorText(reason)));
      },
    );
  }, [owner, server, load]);
  useEffect(() => {
    if (!creating || !owner) return;
    let live = true;
    const refresh = () => {
      void api
        .get<Connection[]>("/trading/connections")
        .then((rows) => {
          if (live) {
            const enabled = rows.filter(
              (row) =>
                row.payload.enabled &&
                (!agent?.trading_account_id || row.id === agent.trading_account_id),
            );
            setConnections(enabled);
            setAccount((old) =>
              enabled.some((row) => row.id === old) ? old : (enabled[0]?.id ?? ""),
            );
          }
        })
        .catch((reason) => {
          if (live) setError(labelsRef.current.errorText(reason));
        });
    };
    connectionRefresh.current = refresh;
    refresh();
    return () => {
      live = false;
      if (connectionRefresh.current === refresh) connectionRefresh.current = null;
    };
  }, [creating, owner, agent?.trading_account_id]);
  useEffect(() => {
    setSymbols([]);
    setSymbol("");
    if (!account || !creating) return;
    let live = true;
    void api
      .get<string[]>(`/market/symbols?account_id=${encodeURIComponent(account)}`)
      .then((rows) => {
        if (live) {
          const matching = agent?.trading_symbol
            ? rows.filter((symbol) => symbol === agent.trading_symbol)
            : rows;
          setSymbols(matching);
          setSymbol(matching[0] ?? "");
        }
      })
      .catch((reason) => {
        if (live) setError(labelsRef.current.errorText(reason));
      });
    return () => {
      live = false;
    };
  }, [account, creating, agent?.trading_symbol]);
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
      setError(labelsRef.current.errorText(reason));
    } finally {
      setBusy(false);
    }
  };
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  const Container = embedded ? EmbeddedWorkspace : Screen;
  const current = charts.find((row) => row.id === selected);
  const connectionIndex = connections.findIndex((row) => row.id === account);
  const connection = connections[connectionIndex];
  return (
    <Container>
      {(!embedded || creating) && (
        <SheetHeader
          title={t("charts")}
          action={creating ? t("save") : undefined}
          onAction={creating ? () => void create() : undefined}
          disabled={busy || !account || !symbol || Boolean(botId && !agent)}
          onClose={creating ? () => setCreating(false) : undefined}
        />
      )}
      <ErrorNotice text={error} />
      {creating ? (
        <ScrollView contentContainerStyle={{ padding: 20, gap: 20 }}>
          <SettingsGroup>
            <SettingsRow
              title={t("brokerAccount")}
              value={
                connection
                  ? brokerIdentityLabel(connection, connectionIndex, t)
                  : t("chooseAccount")
              }
              disabled={Boolean(agent?.trading_account_id)}
              onPress={() => setPicker("account")}
            />
            <SettingsRow
              title={t("symbol")}
              value={symbol || t("chooseSymbol")}
              disabled={!symbols.length || Boolean(agent?.trading_symbol)}
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
                      .catch((reason) => setError(labelsRef.current.errorText(reason)))
                      .finally(() => setBusy(false));
                  }}
                >
                  <NativeSymbol name="refresh" size={19} />
                </HeaderButton>
              </View>
              {scene ? (
                <>
                  <ChartRenderer
                    scene={scene}
                    accountId={current.payload.account_id}
                    onEscape={
                      onEscape ?? (() => (router.canGoBack() ? router.back() : router.replace("/")))
                    }
                  />
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
            ? connections.map((row, index) => ({
                label: brokerIdentityLabel(row, index, t),
                icon: "chart",
                onPress: () => setAccount(row.id),
              }))
            : picker === "symbol"
              ? symbols.map((value) => ({
                  label: value,
                  icon: "chart",
                  onPress: () => setSymbol(value),
                }))
              : CHART_TIMEFRAMES.map((value) => ({
                  label: value,
                  icon: "clock",
                  onPress: () => setTimeframe(value),
                }))
        }
      />
    </Container>
  );
}

function EmbeddedWorkspace({ children }: { children: import("react").ReactNode }) {
  return <View style={{ flex: 1 }}>{children}</View>;
}
