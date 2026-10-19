import { useCallback, useEffect, useRef, useState } from "react";
import { Text, TurboModuleRegistry, UIManager, View } from "react-native";
import type { WebView as NativeWebView } from "react-native-webview";
import type { ChartScene } from "../lib/charts";
import { useSession } from "../lib/session";
import { CandlestickChart } from "./candlestick-chart";
import { colors } from "./ui";

/** Check the installed binary before loading a module unavailable in older OTAs. */
export function ChartRenderer({
  scene,
  accountId,
  onEscape,
}: {
  scene: ChartScene;
  accountId: string;
  onEscape?: () => void;
}) {
  const { server, locale, t, rtl } = useSession();
  const frame = useRef<NativeWebView>(null);
  const latest = useRef({ scene, accountId, locale, onEscape });
  latest.current = { scene, accountId, locale, onEscape };
  const [status, setStatus] = useState<"loading" | "ready" | "unavailable">("loading");
  const [WebView] = useState(() => {
    try {
      if (
        !TurboModuleRegistry.get("RNCWebViewModule") ||
        !UIManager.getViewManagerConfig("RNCWebView")
      )
        return null;
      // A static top-level import would crash older installed binaries.
      return (require("react-native-webview") as typeof import("react-native-webview")).WebView;
    } catch {
      return null;
    }
  });
  const initialLocale = useRef(locale === "ar" ? "ar" : "en");
  const source = `${server}/charts/render?locale=${initialLocale.current}`;
  const sceneIdentity = `${scene.chart_id}:${scene.scene_version}:${scene.data_revision ?? ""}`;
  const renderIdentity = `${scene.chart_id}:${scene.revision}`;
  const expected = new URL(source);
  const pendingTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const appliedIdentity = useRef<string | null>(null);
  const clearPending = useCallback(() => {
    if (pendingTimeout.current !== null) clearTimeout(pendingTimeout.current);
    pendingTimeout.current = null;
  }, []);
  const waitForApplied = useCallback(() => {
    // A stream of unacknowledged ticks must not postpone the failure deadline.
    if (pendingTimeout.current !== null) return;
    pendingTimeout.current = setTimeout(() => setStatus("unavailable"), 15000);
  }, []);
  const send = useCallback(() => {
    // This string is JavaScript source; escaping '<' also makes it safe in HTML contexts.
    const message = JSON.stringify({
      type: "lonora.chart.scene",
      scene: latest.current.scene,
      account_id: latest.current.accountId,
      locale: latest.current.locale,
    }).replace(/</g, "\\u003c");
    frame.current?.injectJavaScript(
      `window.postMessage(${message}, window.location.origin); true;`,
    );
  }, []);
  useEffect(() => {
    if (!source || !renderIdentity) return;
    appliedIdentity.current = null;
    setStatus("loading");
    return clearPending;
  }, [source, renderIdentity, clearPending]);
  useEffect(() => {
    if (WebView && source && renderIdentity && scene && accountId && locale) {
      if (appliedIdentity.current !== sceneIdentity) waitForApplied();
      send();
    }
  }, [
    scene,
    sceneIdentity,
    source,
    renderIdentity,
    accountId,
    locale,
    WebView,
    send,
    waitForApplied,
  ]);
  if (!WebView)
    return (
      <View accessibilityRole="summary" style={{ padding: 24, gap: 12 }}>
        <Text style={{ color: colors.secondary, textAlign: rtl ? "right" : "left" }}>
          {t("chartNativeUnavailable")}
        </Text>
        <Text style={{ color: colors.secondary }}>{t("chartSnapshot")}</Text>
        <CandlestickChart scene={scene} />
      </View>
    );
  return (
    <View style={{ height: 450, gap: 8 }}>
      <Text accessibilityLiveRegion="polite" style={{ color: colors.secondary }}>
        {t(
          status === "ready"
            ? "chartRendered"
            : status === "unavailable"
              ? "chartRendererUnavailable"
              : "chartInitializing",
        )}
      </Text>
      <WebView
        ref={frame}
        source={{ uri: source }}
        originWhitelist={[expected.origin]}
        sharedCookiesEnabled={false}
        thirdPartyCookiesEnabled={false}
        javaScriptCanOpenWindowsAutomatically={false}
        setSupportMultipleWindows={false}
        allowFileAccess={false}
        onError={() => setStatus("unavailable")}
        onHttpError={() => setStatus("unavailable")}
        onShouldStartLoadWithRequest={(request) => {
          try {
            const url = new URL(request.url);
            if (request.isTopFrame === false)
              return (
                url.origin === expected.origin ||
                (url.protocol === "blob:" && new URL(url.pathname).origin === expected.origin)
              );
            return url.origin === expected.origin && url.pathname === expected.pathname;
          } catch {
            return false;
          }
        }}
        onMessage={(event) => {
          try {
            if (new URL(event.nativeEvent.url).origin !== expected.origin) return;
            const data = JSON.parse(event.nativeEvent.data);
            if (data.type === "lonora.chart.escape") latest.current.onEscape?.();
            else if (data.type === "lonora.chart.ready") send();
            else if (
              data.type === "lonora.chart.applied" &&
              data.chart_id === latest.current.scene.chart_id &&
              data.scene_version === latest.current.scene.scene_version &&
              data.data_revision === latest.current.scene.data_revision
            ) {
              appliedIdentity.current = `${latest.current.scene.chart_id}:${latest.current.scene.scene_version}:${latest.current.scene.data_revision ?? ""}`;
              clearPending();
              setStatus("ready");
            }
          } catch {
            /* Ignore malformed or unrelated frame messages. */
          }
        }}
      />
    </View>
  );
}
