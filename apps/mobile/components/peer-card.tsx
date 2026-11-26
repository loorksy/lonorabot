import type { Message, Resource, Run } from "@lonora/contracts";
import { type PeerParty, type PeerStatus, peerCard } from "@lonora/core";
import { useRouter } from "expo-router";
import { Text, View } from "react-native";
import type { Label } from "../lib/i18n";
import { useSession } from "../lib/session";
import { useShellColors } from "../lib/theme";
import { Markdown } from "./markdown";
import { NativeSymbol } from "./native-symbol";

const STATUS: Record<PeerStatus, Label> = {
  cancelled: "peerCancelled",
  failed: "peerFailed",
  completed: "peerCompleted",
  limited: "peerLimited",
  working: "peerWorking",
  queued: "peerQueued",
};

/** A persisted request between two agents, or its returned result, in Web's card frame
    (`PeerCard` in Cards.tsx): who asked whom, each name opening that agent's conversation,
    the text and the status. What it shows comes from core `peerCard`, shared with Web. */
export function PeerCard({
  message,
  peer,
  run,
  onChartLink,
}: {
  message: Message;
  peer: Resource;
  run?: Run;
  onChartLink?: (url: string) => boolean;
}) {
  const { rtl, t } = useSession();
  const shell = useShellColors();
  const router = useRouter();
  const card = peerCard(message, peer, run?.status);
  const row = rtl ? "row-reverse" : "row";
  const who = (party: PeerParty) => {
    const name = party.name || t("peerAgent");
    return party.thread ? (
      <Text
        accessibilityRole="link"
        onPress={() => router.push({ pathname: "/thread", params: { id: party.thread } })}
        style={{ color: shell.link, fontSize: 14, fontWeight: "600" }}
      >
        {name}
      </Text>
    ) : (
      <Text style={{ color: shell.foreground, fontSize: 14, fontWeight: "600" }}>{name}</Text>
    );
  };
  return (
    <View
      testID={`peer-card-${peer.id}`}
      {...({ dataSet: { peerKind: card.kind } } as object)}
      style={{ gap: 6 }}
    >
      <View style={{ flexDirection: row, alignItems: "center", gap: 6 }}>
        <NativeSymbol name="group" size={16} color={shell.secondary} />
        <Text style={{ color: shell.secondary, fontSize: 12, fontWeight: "600" }}>
          {t("peerCollaboration")}
        </Text>
      </View>
      <View
        testID="peer-who"
        style={{ flexDirection: row, flexWrap: "wrap", alignItems: "center", gap: 6 }}
      >
        {who(card.from)}
        <NativeSymbol name={rtl ? "back" : "chevron"} size={14} color={shell.secondary} />
        {who(card.to)}
      </View>
      {card.body !== null ? <Markdown content={card.body} onChartLink={onChartLink} /> : null}
      <Text accessibilityLiveRegion="polite" style={{ color: shell.secondary, fontSize: 12 }}>
        {t(STATUS[card.status])}
      </Text>
    </View>
  );
}
