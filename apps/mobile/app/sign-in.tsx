import { brand } from "@lonora/ui-tokens";
import { Redirect } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { Image, KeyboardAvoidingView, Platform, ScrollView, Text, View } from "react-native";
import { Button, colors, ErrorNotice, Field, Header, Loading, Screen } from "../components/ui";
import { useSession } from "../lib/session";

export default function SignIn() {
  const session = useSession();
  const [server, setServer] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // A server with no owner yet gets Web's first-run form instead of sign-in (GET /onboarding).
  const [initialized, setInitialized] = useState(true);
  const [token, setToken] = useState("");
  const address = server ?? session.server;
  const { ready, owner } = session;
  const status = useRef(session.setupStatus);
  status.current = session.setupStatus;
  useEffect(() => {
    if (!ready || owner || !address.trim()) return;
    let live = true;
    const timer = setTimeout(() => {
      status.current(address).then(
        (value) => live && setInitialized(value),
        // Unreachable or not a Lonora server: sign-in stays and its own error says why.
        () => live && setInitialized(true),
      );
    }, 400);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [ready, owner, address]);
  if (!ready) return <Loading />;
  if (owner) return <Redirect href="/" />;
  const setup = !initialized;
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      if (setup) await session.initializeOwner(address, email, password, token);
      else await session.login(address, email, password);
      setPassword("");
      setToken("");
    } catch (reason) {
      setError(session.errorText(reason));
      // The owner may exist now (created, then the sign-in failed): the form follows the server.
      if (setup) status.current(address).then(setInitialized, () => undefined);
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
          <Image
            source={require("../assets/brand/logo.png")}
            accessibilityIgnoresInvertColors
            style={{ width: 64, height: 64, alignSelf: "center" }}
            resizeMode="contain"
          />
          <Text
            style={{
              fontSize: 30,
              fontWeight: "600",
              color: colors.foreground,
              textAlign: session.rtl ? "right" : "left",
            }}
          >
            {session.t(setup ? "setupTitle" : "signIn")}
          </Text>
          <Text
            style={{
              color: colors.secondary,
              lineHeight: 24,
              textAlign: session.rtl ? "right" : "left",
            }}
          >
            {session.t(setup ? "setupHint" : "serverHint")}
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
            label={session.t(setup ? "setupPassword" : "password")}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoComplete={setup ? "new-password" : "current-password"}
            onSubmitEditing={setup ? undefined : () => void submit()}
          />
          {setup ? (
            <Field
              label={session.t("setupToken")}
              value={token}
              onChangeText={setToken}
              secureTextEntry
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete="off"
              onSubmitEditing={() => void submit()}
              style={{ textAlign: "left", writingDirection: "ltr" }}
            />
          ) : null}
          <ErrorNotice text={error} />
          <View>
            <Button
              label={busy ? session.t("connecting") : session.t(setup ? "setupCreate" : "signIn")}
              onPress={() => void submit()}
              disabled={
                busy ||
                !email.trim() ||
                !password ||
                !address.trim() ||
                (setup && (password.length < 12 || !token))
              }
            />
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}
