import type { Owner } from "@lonora/contracts";
import {
  agentPermissionError,
  financialBoundaryError,
  ownerActionError,
  ownerProfileError,
} from "@lonora/core";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { AppState, Platform } from "react-native";
import {
  ApiError,
  api,
  cancelBackgroundReads,
  cancelSessionRequests,
  configureApi,
  normalizeServer,
  SessionRequestCancelled,
  setCredentials,
} from "./api";
import { type Label, type Locale, labels, translate } from "./i18n";
import { closeSessionResources } from "./session-lifecycle";
import { loadNativeToken, loadSetting, saveNativeToken, saveSetting } from "./storage";

type Session = {
  ready: boolean;
  owner: Owner | null;
  server: string;
  locale: Locale;
  rtl: boolean;
  login: (server: string, email: string, password: string) => Promise<void>;
  /** First run, as Web's «إعداد Lonora»: create the owner with the setup token, then sign in. */
  initializeOwner: (
    server: string,
    email: string,
    password: string,
    token: string,
  ) => Promise<void>;
  logout: () => Promise<void>;
  changeServer: (server: string) => Promise<void>;
  changeLocale: (locale: Locale) => Promise<void>;
  t: (key: Label) => string;
  /** `fallback`: the text for a code the catalog does not know, instead of the general one. */
  errorText: (error: unknown, fallback?: string) => string;
};
const Context = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [owner, setOwner] = useState<Owner | null>(null);
  const [locale, setLocale] = useState<Locale>("ar");
  const [server, setServer] = useState(
    Platform.OS === "web" && typeof window !== "undefined" ? window.location.origin : "",
  );
  const expire = useCallback(() => {
    setOwner(null);
    setCredentials(null);
    void closeSessionResources().catch(() => undefined);
    void saveNativeToken(null).catch(() => undefined);
  }, []);

  useEffect(() => {
    let live = true;
    const initialize = async () => {
      try {
        const [storedServer, token, storedLocale] = await Promise.all([
          loadSetting("lonora.server"),
          loadNativeToken(),
          loadSetting("lonora.locale"),
        ]);
        if (!live) return;
        if (storedLocale === "en" || storedLocale === "ar") setLocale(storedLocale);
        const nextServer =
          storedServer ??
          (Platform.OS === "web" && typeof window !== "undefined" ? window.location.origin : "");
        setServer(nextServer);
        if (!nextServer) return;
        configureApi(nextServer, token, expire);
        if (Platform.OS !== "web" && !token) return;
        const nextOwner = await api.get<Owner>("/auth/session");
        if (live) setOwner(nextOwner);
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) await saveNativeToken(null);
      } finally {
        if (live) setReady(true);
      }
    };
    void initialize();
    return () => {
      live = false;
    };
  }, [expire]);

  useEffect(() => {
    const subscription = AppState.addEventListener("change", (state) => {
      if (state !== "active") cancelBackgroundReads();
    });
    return () => subscription.remove();
  }, []);

  // In a browser the page says its language, for screen readers and the browser's own text
  // handling. Its direction stays left-to-right: every row here mirrors itself by `rtl` (as
  // on native, where the app does not switch the layout), so a page dir would flip it twice.
  useEffect(() => {
    if (Platform.OS === "web" && typeof document !== "undefined")
      document.documentElement.lang = locale;
  }, [locale]);

  const login = async (value: string, email: string, password: string) => {
    let normalized: string;
    try {
      normalized = normalizeServer(value);
    } catch {
      throw new ApiError("invalid_server", 0);
    }
    configureApi(normalized, null, expire);
    const result = await api.post<{ owner: Owner; token?: string; csrf?: string }>(
      Platform.OS === "web" ? "/auth/login" : "/auth/mobile/login",
      { email: email.trim(), password },
    );
    if (Platform.OS !== "web" && !result.token) throw new ApiError("request_failed", 500);
    await saveNativeToken(result.token ?? null);
    await saveSetting("lonora.server", normalized);
    setCredentials(result.token ?? null, result.csrf ?? "");
    setServer(normalized);
    setOwner(result.owner);
  };

  const initializeOwner = async (value: string, email: string, password: string, token: string) => {
    let normalized: string;
    try {
      normalized = normalizeServer(value);
    } catch {
      throw new ApiError("invalid_server", 0);
    }
    configureApi(normalized, null, expire);
    try {
      await api.post("/onboarding", { email: email.trim(), password, bootstrap_token: token });
    } catch (error) {
      // Created by an earlier attempt whose sign-in failed: signing in is what is left.
      if (!(error instanceof ApiError && error.code === "owner_already_initialized")) throw error;
    }
    await login(value, email, password);
  };

  const logout = async () => {
    cancelSessionRequests();
    try {
      // One broken resource must not prevent server-side session revocation.
      const results = await Promise.allSettled([
        closeSessionResources(),
        api.post("/auth/logout", {}),
      ]);
      const failure = results.find((result) => result.status === "rejected");
      if (failure?.status === "rejected") throw failure.reason;
    } catch (error) {
      if (
        !(error instanceof SessionRequestCancelled) &&
        (!(error instanceof ApiError) || error.status !== 401)
      )
        throw error;
    } finally {
      // A failed server logout must not keep local credentials or old requests alive.
      setCredentials(null);
      setOwner(null);
      await saveNativeToken(null);
    }
  };
  const changeServer = async (value: string) => {
    let normalized: string;
    try {
      normalized = normalizeServer(value);
    } catch {
      throw new ApiError("invalid_server", 0);
    }
    if (owner) await logout();
    else {
      cancelSessionRequests();
      await closeSessionResources();
      await saveNativeToken(null);
      setCredentials(null);
    }
    await saveSetting("lonora.server", normalized);
    configureApi(normalized, null, expire);
    setServer(normalized);
    setOwner(null);
  };
  const changeLocale = async (next: Locale) => {
    await saveSetting("lonora.locale", next);
    setLocale(next);
  };
  const t = (key: Label) => translate(locale, key);
  const errorText = (error: unknown, fallback?: string) => {
    if (error instanceof SessionRequestCancelled) return "";
    if (error instanceof ApiError) {
      const permissionMessage = agentPermissionError(error.code, locale);
      if (permissionMessage) return permissionMessage;
      const boundaryMessage = financialBoundaryError(error.code, locale);
      if (boundaryMessage) return boundaryMessage;
      const cardMessage = ownerActionError(error.code, locale);
      if (cardMessage) return cardMessage;
      // Profile, reach-me and memory errors: the same shared text as the Web.
      const profileMessage = ownerProfileError(error.code, locale);
      if (profileMessage) return profileMessage;
      return Object.hasOwn(labels, error.code)
        ? translate(locale, error.code as Label)
        : (fallback ?? t("request_failed"));
    }
    return t("network");
  };
  return (
    <Context.Provider
      value={{
        ready,
        owner,
        server,
        locale,
        rtl: locale === "ar",
        login,
        initializeOwner,
        logout,
        changeLocale,
        changeServer,
        t,
        errorText,
      }}
    >
      {children}
    </Context.Provider>
  );
}

export function useSession(): Session {
  const value = useContext(Context);
  if (!value) throw new Error("SessionProvider missing");
  return value;
}
