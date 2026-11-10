// «وكيل جديد» (owner decision Q9): step 1 is the reference's three templates; step 2 names the agent
// and its role (and the pair for a trading agent). The agent is created through POST /api/agents/create,
// the same input and service as the agent_create tool, so the template is persisted and the ladder
// starts where the template says. Mobile no longer posts POST /api/agents.
import type { Agent, AgentTemplate, Thread } from "@lonora/contracts";
import { DEFAULT_AVATAR_COLOR } from "@lonora/core";
import { Redirect, useRouter } from "expo-router";
import { useState } from "react";
import { ScrollView, Text, TextInput, View } from "react-native";
import { AvatarPicker } from "../components/avatar-picker";
import { type BrokerPair, BrokerPairPicker } from "../components/broker-pair-picker";
import { PageHeader } from "../components/shell/chrome";
import { Icon, type IconName } from "../components/shell/icon";
import { Btn, GroupBox, Row } from "../components/shell/kit";
import { Loading } from "../components/ui";
import { api } from "../lib/api";
import { useSession } from "../lib/session";
import { useShellData } from "../lib/shell-data";
import { useTheme } from "../lib/theme";

type Template = Exclude<AgentTemplate, "supervisor">;

export default function NewAgent() {
  const { ready, owner, t, rtl, errorText } = useSession();
  const { c } = useTheme();
  const router = useRouter();
  const data = useShellData();
  const [template, setTemplate] = useState<Template>("general");
  const [step, setStep] = useState<"template" | "details">("template");
  const [pair, setPair] = useState<BrokerPair>({ trading_account_id: "", trading_symbol: "" });
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [color, setColor] = useState(DEFAULT_AVATAR_COLOR);
  const [avatar, setAvatar] = useState("face-smile");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  const templates: Record<Template, { icon: IconName; label: string; sub: string; code: string }> =
    {
      trading: {
        icon: "trend",
        label: t("sh_tplTrading"),
        sub: t("sh_tplTradingSub"),
        code: t("sh_tplTradingCode"),
      },
      general: {
        icon: "bot",
        label: t("sh_tplGeneral"),
        sub: t("sh_tplGeneralSub"),
        code: t("sh_tplGeneralCode"),
      },
      research: {
        icon: "search",
        label: t("sh_tplResearch"),
        sub: t("sh_tplResearchSub"),
        code: t("sh_tplResearchCode"),
      },
    };
  const trading = template === "trading";
  const create = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const agent = await api.post<Agent>("/agents/create", {
        template,
        name: name.trim(),
        responsibility: role.trim(),
        ...(trading ? { market: pair.trading_symbol, account_id: pair.trading_account_id } : {}),
      });
      // The appearance is the agent's own setting, saved right after; a failed save is not a failed
      // creation (a retry would make a second agent) and stays editable in the agent's settings.
      if (avatar !== agent.avatar || color !== agent.color)
        await api.patch(`/agents/${agent.id}`, { avatar, color }).catch(() => undefined);
      void data.refresh();
      const thread = await api.post<Thread>(
        `/agents/${encodeURIComponent(agent.id)}/conversation`,
        {},
      );
      router.replace({ pathname: "/thread", params: { id: thread.id } });
    } catch (reason) {
      setError(errorText(reason));
      setBusy(false);
    }
  };
  const align = rtl ? "right" : "left";
  const input = {
    minHeight: 48,
    borderRadius: 12,
    backgroundColor: c.fill,
    color: c.text,
    paddingHorizontal: 14,
    fontSize: 16,
    textAlign: align,
    writingDirection: rtl ? "rtl" : "ltr",
  } as const;
  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <PageHeader title={t("sh_newAgent")} />
      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 48, gap: 14 }}
      >
        {step === "template" ? (
          <>
            <Text style={{ color: c.muted, fontSize: 14, textAlign: align }}>
              {t("sh_tplPick")}
            </Text>
            <GroupBox>
              <View accessibilityRole="radiogroup" accessibilityLabel={t("sh_agentTemplate")}>
                {(Object.keys(templates) as Template[]).map((key, index, all) => (
                  <Row
                    key={key}
                    testID={`template-${key}`}
                    role="checkbox"
                    checked={template === key}
                    last={index === all.length - 1}
                    lead={<Icon name={templates[key].icon} size={24} color={c.text} />}
                    title={templates[key].label}
                    sub={`${templates[key].sub}\n${templates[key].code}`}
                    trailing={
                      <View
                        style={{
                          width: 22,
                          height: 22,
                          borderRadius: 11,
                          borderWidth: 2,
                          borderColor: template === key ? c.accent : c["line-strong"],
                          alignItems: "center",
                          justifyContent: "center",
                        }}
                      >
                        {template === key ? (
                          <View
                            style={{
                              width: 10,
                              height: 10,
                              borderRadius: 5,
                              backgroundColor: c.accent,
                            }}
                          />
                        ) : null}
                      </View>
                    }
                    onPress={() => setTemplate(key)}
                  />
                ))}
              </View>
            </GroupBox>
            <Btn full variant="primary" label={t("sh_next")} onPress={() => setStep("details")} />
          </>
        ) : (
          <>
            <AvatarPicker
              name={name}
              color={color}
              avatar={avatar}
              onChange={(shape, value) => {
                setAvatar(shape);
                setColor(value);
              }}
            />
            <View style={{ gap: 8 }}>
              <Text style={{ color: c.muted, fontSize: 14, textAlign: align }}>
                {t("sh_agentName")}
              </Text>
              <TextInput
                accessibilityLabel={t("sh_agentName")}
                value={name}
                onChangeText={setName}
                maxLength={60}
                autoFocus
                style={input}
              />
            </View>
            <View style={{ gap: 8 }}>
              <Text style={{ color: c.muted, fontSize: 14, textAlign: align }}>
                {t("sh_description")}
              </Text>
              <TextInput
                accessibilityLabel={t("sh_description")}
                value={role}
                onChangeText={setRole}
                maxLength={180}
                style={input}
              />
            </View>
            <GroupBox>
              <Row
                last
                title={t("sh_type")}
                trailing={
                  <Text style={{ color: c.muted, fontSize: 14 }}>{templates[template].label}</Text>
                }
              />
            </GroupBox>
            {trading ? <BrokerPairPicker value={pair} onChange={setPair} /> : null}
            <Text style={{ color: c.muted, fontSize: 12, lineHeight: 22, textAlign: align }}>
              {trading
                ? t("sh_tradingNote")
                : template === "research"
                  ? t("sh_researchNote")
                  : t("sh_generalNote")}
            </Text>
            {error ? (
              <Text accessibilityRole="alert" style={{ color: c.red, textAlign: align }}>
                {error}
              </Text>
            ) : null}
            <View style={{ flexDirection: rtl ? "row-reverse" : "row", gap: 10 }}>
              <Btn
                variant="outline"
                full
                label={t("sh_back")}
                onPress={() => setStep("template")}
              />
              <Btn
                variant="primary"
                full
                label={t("sh_createAgentBtn")}
                disabled={
                  busy ||
                  !name.trim() ||
                  !role.trim() ||
                  (trading && (!pair.trading_account_id || !pair.trading_symbol))
                }
                onPress={() => void create()}
              />
            </View>
          </>
        )}
      </ScrollView>
    </View>
  );
}
