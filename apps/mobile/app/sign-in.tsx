import { brand } from "@lonora/ui-tokens";
import { Redirect } from "expo-router";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, Text, View } from "react-native";
import { Button, colors, ErrorNotice, Field, Header, Loading, Screen } from "../components/ui";
import { useSession } from "../lib/session";

export default function SignIn() {
  const session = useSession();
  const [server, setServer] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!session.ready) return <Loading />;
  if (session.owner) return <Redirect href="/" />;
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await session.login(server ?? session.server, email, password);
      setPassword("");
    } catch (reason) {
      setError(session.errorText(reason));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Screen>
      <Header
        title={brand.name}
        right={
          <Button
            label={session.locale === "ar" ? "English" : "العربية"}
            secondary
            onPress={() => void session.changeLocale(session.locale === "ar" ? "en" : "ar")}
          />
        }
      />
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={{ flex: 1 }}
      >
        <ScrollView
          contentContainerStyle={{
            padding: 24,
            gap: 22,
            maxWidth: 520,
            width: "100%",
            alignSelf: "center",
          }}
          keyboardShouldPersistTaps="handled"
        >
          <Text
            style={{
              fontSize: 30,
              fontWeight: "600",
              color: colors.foreground,
              textAlign: session.rtl ? "right" : "left",
            }}
          >
            {session.t("signIn")}
          </Text>
          <Text
            style={{
              color: colors.secondary,
              lineHeight: 24,
              textAlign: session.rtl ? "right" : "left",
            }}
          >
            {session.t("serverHint")}
          </Text>
          <Field
            label={session.t("server")}
            value={server ?? session.server}
            onChangeText={setServer}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            placeholder="https://lonora.example.com"
            style={{ textAlign: "left", writingDirection: "ltr" }}
          />
          <Field
            label={session.t("email")}
            value={email}
            onChangeText={setEmail}
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="email"
            style={{ textAlign: "left", writingDirection: "ltr" }}
          />
          <Field
            label={session.t("password")}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoComplete="current-password"
            onSubmitEditing={() => void submit()}
          />
          <ErrorNotice text={error} />
          <View>
            <Button
              label={busy ? session.t("connecting") : session.t("signIn")}
              onPress={() => void submit()}
              disabled={busy || !email.trim() || !password || !(server ?? session.server).trim()}
            />
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}
