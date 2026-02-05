"use client";

import { PropsWithChildren, createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";

type User = {
  id: string;
  username: string;
  role: string;
};

type AuthState = {
  user: User | null;
  csrfToken: string | null;
  loading: boolean;
  refresh: () => Promise<void>;
  login: (params: { username: string; password: string }) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<User | null>(null);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch("/api/auth/me", { method: "GET" });
      if (!res.ok) {
        setUser(null);
        setCsrfToken(null);
        return;
      }
      const data = (await res.json()) as { user: User; csrf_token: string };
      setUser(data.user);
      setCsrfToken(data.csrf_token);
    } finally {
      setLoading(false);
    }
  }, []);

  const login = useCallback(
    async (params: { username: string; password: string }) => {
      const csrfRes = await apiFetch("/api/auth/csrf", { method: "GET" });
      if (!csrfRes.ok) {
        throw new Error("Failed to fetch CSRF token");
      }
      const csrfData = (await csrfRes.json()) as { csrf_token: string };

      const res = await apiFetch("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          username: params.username,
          password: params.password,
          csrf_token: csrfData.csrf_token,
        }),
        headers: { "Content-Type": "application/json" },
      });
      if (!res.ok) {
        const msg = await res.text();
        throw new Error(msg || "Login failed");
      }
      const data = (await res.json()) as { ok: boolean; user: User; csrf_token: string };
      setUser(data.user);
      setCsrfToken(data.csrf_token);
    },
    [],
  );

  const logout = useCallback(async () => {
    if (!csrfToken) {
      setUser(null);
      setCsrfToken(null);
      return;
    }
    await apiFetch("/api/auth/logout", {
      method: "POST",
      headers: { "x-csrf-token": csrfToken },
    });
    setUser(null);
    setCsrfToken(null);
  }, [csrfToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo<AuthState>(
    () => ({
      user,
      csrfToken,
      loading,
      refresh,
      login,
      logout,
    }),
    [csrfToken, loading, login, logout, refresh, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("AuthProvider missing");
  }
  return ctx;
}

