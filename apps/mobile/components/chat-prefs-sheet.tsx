// «تجربة المحادثة», as Web's chat preferences page, opened from the conversation's menu (P5:
// no screen outside conversations): the switches a phone's conversation honours.
import { Text, View } from "react-native";
import { type ChatPrefs, setChatPref, useChatPrefs } from "../lib/chat-prefs";
import type { Label } from "../lib/i18n";
import { useSession } from "../lib/session";
import { useTheme } from "../lib/theme";
import { GroupBox, Row, Switch } from "./shell/kit";

const ROWS: { key: keyof ChatPrefs; title: Label; sub: Label }[] = [
  { key: "steps", title: "prefSteps", sub: "prefStepsSub" },
  { key: "stepsOpen", title: "prefStepsOpen", sub: "prefStepsOpenSub" },
  { key: "agentStatus", title: "prefAgentStatus", sub: "prefAgentStatusSub" },
  { key: "assist", title: "prefAssist", sub: "prefAssistSub" },
];

export function ChatPrefsBody() {
  const prefs = useChatPrefs();
  const { t, rtl } = useSession();
  const { c } = useTheme();
  return (
    <View style={{ gap: 12 }}>
      <Text
        style={{ color: c.muted, fontSize: 14, lineHeight: 21, textAlign: rtl ? "right" : "left" }}
      >
        {t("chatPrefsIntro")}
      </Text>
      <GroupBox>
        {ROWS.map((row, index) => (
          <Row
            key={row.key}
            testID={`chat-pref-${row.key}`}
            title={t(row.title)}
            sub={t(row.sub)}
            last={index === ROWS.length - 1}
            trailing={
              <Switch
                label={t(row.title)}
                value={prefs[row.key]}
                // The steps open by themselves only when they are shown at all (as on Web).
                disabled={row.key === "stepsOpen" && !prefs.steps}
                onChange={(value) => setChatPref(row.key, value)}
              />
            }
          />
        ))}
      </GroupBox>
    </View>
  );
}
