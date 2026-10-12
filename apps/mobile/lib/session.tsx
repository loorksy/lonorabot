import type { Owner } from "@lonora/contracts";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { Platform } from "react-native";
import { ApiError, api, configureApi, normalizeServer, setCredentials } from "./api";
import { type Label, type Locale, labels, translate } from "./i18n";
import { loadNativeToken, loadSetting, saveNativeToken, saveSetting } from "./storage";

type Session = {
  ready: boolean;
  owner: Owner | null;
  server: string;
  locale: Locale;
  rtl: boolean;
  login: (server: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  changeServer: (server: string) => Promise<void>;
  changeLocale: (locale: Locale) => Promise<void>;
  t: (key: Label) => string;
  errorText: (error: unknown) => string;
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

  const logout = async () => {
    try {
      await api.post("/auth/logout", {});
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error;
    }
    await saveNativeToken(null);
    setCredentials(null);
    setOwner(null);
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
  const errorText = (error: unknown) => {
    if (error instanceof ApiError) {
      return Object.hasOwn(labels, error.code)
        ? translate(locale, error.code as Label)
        : t("request_failed");
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
