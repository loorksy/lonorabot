import { useEffect, useRef, useState } from "react";
import { Text, View } from "react-native";
import type { ChartScene } from "../lib/charts";
import { useSession } from "../lib/session";
import { colors } from "./ui";

/** One hosted vendor distribution. Only validated scene data crosses the bridge. */
export function ChartRenderer({
  scene,
  accountId,
  onEscape,
}: {
  scene: ChartScene;
  accountId: string;
  onEscape?: () => void;
}) {
  const { server, locale, t } = useSession();
  const frame = useRef<HTMLIFrameElement>(null);
  const latest = useRef({ scene, accountId, locale, onEscape });
  latest.current = { scene, accountId, locale, onEscape };
  const [status, setStatus] = useState<"loading" | "ready" | "unavailable">("loading");
  const initialLocale = useRef(locale === "ar" ? "ar" : "en");
  const source = `${server}/charts/render?locale=${initialLocale.current}`;
  const sceneIdentity = `${scene.chart_id}:${scene.scene_version}:${scene.data_revision ?? ""}`;
  const origin = new URL(source, window.location.origin).origin;
  useEffect(() => {
    if (!source || !sceneIdentity) return;
    setStatus("loading");
    const timeout = setTimeout(
      () => setStatus((old) => (old === "ready" ? old : "unavailable")),
      15000,
    );
    const receive = (event: MessageEvent) => {
      if (event.origin !== origin || event.source !== frame.current?.contentWindow) return;
      if (event.data?.type === "lonora.chart.escape") {
        latest.current.onEscape?.();
      } else if (event.data?.type === "lonora.chart.ready") {
        frame.current?.contentWindow?.postMessage(
          {
            type: "lonora.chart.scene",
            scene: latest.current.scene,
            account_id: latest.current.accountId,
            locale: latest.current.locale,
          },
          origin,
        );
      } else if (
        event.data?.type === "lonora.chart.applied" &&
        event.data.chart_id === latest.current.scene.chart_id &&
        event.data.scene_version === latest.current.scene.scene_version &&
        event.data.data_revision === latest.current.scene.data_revision
      ) {
        setStatus("ready");
      }
    };
    window.addEventListener("message", receive);
    return () => {
      clearTimeout(timeout);
      window.removeEventListener("message", receive);
    };
  }, [origin, source, sceneIdentity]);
  useEffect(() => {
    frame.current?.contentWindow?.postMessage(
      { type: "lonora.chart.scene", scene, account_id: accountId, locale },
      origin,
    );
  }, [scene, origin, accountId, locale]);
  return (
    <View style={{ gap: 8 }}>
      <Text accessibilityLiveRegion="polite" style={{ color: colors.secondary }}>
        {t(
          status === "ready"
            ? "chartRendered"
            : status === "unavailable"
              ? "chartRendererUnavailable"
              : "chartInitializing",
        )}
      </Text>
      <iframe
        ref={frame}
        src={source}
        title={`${scene.symbol} · ${scene.timeframe}`}
        style={{ width: "100%", height: 420, border: 0, borderRadius: 12 }}
      />
    </View>
  );
}
