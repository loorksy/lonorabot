import { brand } from "@lonora/ui-tokens";
import { Redirect, useFocusEffect } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Image, KeyboardAvoidingView, Platform, ScrollView, Text, View } from "react-native";
import { Button, colors, ErrorNotice, Field, Header, Loading, Screen } from "../components/ui";
import { onboardingStatus } from "../lib/api";
import { type HeldSetupToken, sameServer, takeSetupToken } from "../lib/connect-link";
import { useSession } from "../lib/session";

export default function SignIn() {
  const session = useSession();
  const [server, setServer] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // A server with no owner yet gets Web's first-run form instead of sign-in (GET /onboarding).
  // The answer belongs to the address it was read for: a changed address is checked again,
  // and nothing is sent until it is.
  const [checked, setChecked] = useState<{ address: string; initialized: boolean } | null>(null);
  const [token, setToken] = useState("");
  // A failed sign-in or setup asks the server again: an unreachable check fell back to sign-in,
  // and an owner created elsewhere meanwhile turns the setup form back into sign-in.
  const [recheck, setRecheck] = useState(0);
  const address = server ?? session.server;
  const { ready, owner } = session;
  // biome-ignore lint/correctness/useExhaustiveDependencies: `recheck` asks the server again
  useEffect(() => {
    if (!ready || owner || !address.trim()) return;
    const controller = new AbortController();
    let live = true;
    // A server that never answers does not hold the form: after 10 s it counts as unreachable.
    const limit = setTimeout(() => controller.abort(), 10_400);
    const timer = setTimeout(() => {
      onboardingStatus(address, controller.signal).then(
        (initialized) => live && setChecked({ address, initialized }),
        // Unreachable or not a Lonora server: an answer already read for this address stays;
        // with none, sign-in it is, and its own error says why.
        () =>
          live &&
          setChecked((known) =>
            known?.address === address ? known : { address, initialized: true },
          ),
      );
    }, 400);
    return () => {
      live = false;
      controller.abort();
      clearTimeout(timer);
      clearTimeout(limit);
    };
  }, [ready, owner, address, recheck]);
  const pending = checked?.address !== address;
  const setup = !pending && checked?.initialized === false;
  // A connect link's setup token (lonora://connect…&token=) fills the setup form once, and only
  // for the server the link named. It is taken each time this screen comes into view: a phone
  // with no owner already waits here when a link is confirmed. That server is the one the owner
  // just confirmed, so an address typed before gives way to it.
  const [linked, setLinked] = useState<HeldSetupToken | null>(null);
  useFocusEffect(
    useCallback(() => {
      const held = takeSetupToken();
      if (!held) return;
      setLinked(held);
      setServer(null);
    }, []),
  );
  // The setup token is kept only while the setup form is shown, and the link's token is filled
  // only into the form of the server it was issued for.
  useEffect(() => {
    if (!setup) setToken("");
    else if (linked && sameServer(linked.server, address)) {
      setToken(linked.token);
      setLinked(null);
    }
  }, [setup, address, linked]);
  if (!ready) return <Loading />;
  if (owner) return <Redirect href="/" />;
  // One rule for the button and for the keyboard's submit key.
  const blocked =
    busy ||
    pending ||
    !email.trim() ||
    !password ||
    !address.trim() ||
    (setup && (password.length < 12 || !token));
  const submit = async () => {
    if (blocked) return;
    // The server's setup token is 24 characters at least: a shorter one is cut short.
    if (setup && token.length < 24) {
      setError(session.t("setupTokenShort"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (setup) await session.initializeOwner(address, email, password, token);
      else await session.login(address, email, password);
      setPassword("");
      setToken("");
    } catch (reason) {
      setError(session.errorText(reason));
      setRecheck((count) => count + 1);
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
              disabled={blocked}
            />
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}
