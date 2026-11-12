import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { AuthProvider as OidcAuthProvider, useAuth as useOidcAuth } from "react-oidc-context";
import { WebStorageStateStore } from "oidc-client-ts";
import { api, setAccessToken, setAccessTokenRefresher } from "../api/client";
import { API_BASE, appPublicBaseUrl, withMountPath } from "../lib/mountPath";
import type { SessionUser } from "../types";

export type AuthMode = "loading" | "keycloak" | "legacy";

const BUILTIN_OIDC = {
  authority: import.meta.env.VITE_OIDC_AUTHORITY ?? "",
  client_id: import.meta.env.VITE_OIDC_CLIENT_ID ?? "",
};

const HAS_BUILTIN_OIDC = Boolean(BUILTIN_OIDC.authority && BUILTIN_OIDC.client_id);

const oidcUserStore = new WebStorageStateStore({ store: window.localStorage });

function proxiedTokenEndpoint() {
  return `${window.location.origin}${API_BASE}/auth/oidc/token`;
}

interface AuthContextValue {
  mode: AuthMode;
  user: SessionUser | null;
  checking: boolean;
  refreshUser: () => Promise<SessionUser | null>;
  signIn: () => Promise<void>;
  signUp: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function LegacyAuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [checking, setChecking] = useState(true);

  const refreshUser = useCallback(async () => {
    try {
      const me = await api.auth.me();
      setUser(me);
      setAccessToken(null);
      return me;
    } catch {
      setUser(null);
      setAccessToken(null);
      return null;
    }
  }, []);

  useEffect(() => {
    refreshUser().finally(() => setChecking(false));
  }, [refreshUser]);

  const value = useMemo<AuthContextValue>(
    () => ({
      mode: "legacy",
      user,
      checking,
      refreshUser,
      signIn: async () => undefined,
      signUp: async () => undefined,
      signOut: async () => {
        await api.auth.logout().catch(() => undefined);
        setUser(null);
        setAccessToken(null);
      },
    }),
    [user, checking, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function KeycloakBridge({ children }: { children: ReactNode }) {
  const oidc = useOidcAuth();
  const [user, setUser] = useState<SessionUser | null>(null);
  const [sessionReady, setSessionReady] = useState(false);

  const refreshUser = useCallback(async () => {
    const token = oidc.user?.access_token;
    if (!token) {
      setUser(null);
      setAccessToken(null);
      return null;
    }
    setAccessToken(token);
    try {
      const me = await api.auth.me();
      setUser(me);
      return me;
    } catch {
      setUser(null);
      setAccessToken(null);
      return null;
    }
  }, [oidc.user?.access_token]);

  useEffect(() => {
    setAccessTokenRefresher(async () => {
      try {
        const renewed = await oidc.signinSilent();
        return renewed?.access_token ?? null;
      } catch {
        return null;
      }
    });
    return () => setAccessTokenRefresher(null);
  }, [oidc.signinSilent]);

  useEffect(() => {
    if (oidc.isLoading || oidc.activeNavigator) {
      setSessionReady(false);
      return;
    }
    void refreshUser().finally(() => setSessionReady(true));
  }, [oidc.isLoading, oidc.activeNavigator, refreshUser]);

  const checking = !sessionReady || oidc.isLoading || Boolean(oidc.activeNavigator);

  const value = useMemo<AuthContextValue>(
    () => ({
      mode: "keycloak",
      user,
      checking,
      refreshUser,
      signIn: async () => {
        await oidc.signinRedirect();
      },
      signUp: async () => {
        // OIDC prompt=create → Keycloak registration form (same auth endpoint, not client-registration).
        await oidc.signinRedirect({ extraQueryParams: { prompt: "create" } });
      },
      signOut: async () => {
        setUser(null);
        setAccessToken(null);
        await oidc.signoutRedirect();
      },
    }),
    [user, checking, oidc, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function KeycloakShell({
  authority,
  clientId,
  children,
}: {
  authority: string;
  clientId: string;
  children: ReactNode;
}) {
  return (
    <OidcAuthProvider
      authority={authority}
      client_id={clientId}
      redirect_uri={`${appPublicBaseUrl()}/auth/callback`}
      post_logout_redirect_uri={`${appPublicBaseUrl()}/login`}
      response_type="code"
      scope="openid email profile"
      automaticSilentRenew
      monitorSession={false}
      userStore={oidcUserStore}
      metadataSeed={{
        token_endpoint: proxiedTokenEndpoint(),
      }}
      onSigninCallback={() => {
        window.history.replaceState({}, document.title, withMountPath("/auth/callback"));
      }}
    >
      <KeycloakBridge>{children}</KeycloakBridge>
    </OidcAuthProvider>
  );
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<AuthMode>(HAS_BUILTIN_OIDC ? "keycloak" : "loading");
  const [oidcConfig, setOidcConfig] = useState<{ authority: string; client_id: string } | null>(
    HAS_BUILTIN_OIDC ? BUILTIN_OIDC : null,
  );

  useEffect(() => {
    if (HAS_BUILTIN_OIDC) return;
    api.auth
      .config()
      .then((cfg) => {
        if (cfg.mode === "keycloak" && cfg.authority && cfg.client_id) {
          setOidcConfig({ authority: cfg.authority, client_id: cfg.client_id });
          setMode("keycloak");
        } else {
          setMode("legacy");
        }
      })
      .catch(() => setMode("legacy"));
  }, []);

  if (mode === "loading") {
    return (
      <div className="app-shell flex min-h-dvh items-center justify-center">
        <p className="text-muted">Loading…</p>
      </div>
    );
  }

  if (mode === "keycloak" && oidcConfig) {
    return (
      <KeycloakShell authority={oidcConfig.authority} clientId={oidcConfig.client_id}>
        {children}
      </KeycloakShell>
    );
  }

  return <LegacyAuthProvider>{children}</LegacyAuthProvider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
