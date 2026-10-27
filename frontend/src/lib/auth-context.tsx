"use client";

import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from "react";
import { authApi, UserResponse } from "@/lib/api";

interface AuthContextValue {
  user: UserResponse | null;
  token: string | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  register: (email: string, password: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Restore session from localStorage on mount
  useEffect(() => {
    // Check if dev preview user is active
    const previewUser = localStorage.getItem("preview_dev_user");
    if (previewUser) {
      try {
        setUser(JSON.parse(previewUser));
        setToken("dev_preview_token");
        setIsLoading(false);
        return;
      } catch {
        // Fallback to normal flow
      }
    }

    const storedToken = localStorage.getItem("access_token");
    if (storedToken) {
      setToken(storedToken);
      authApi.me()
        .then(setUser)
        .catch(() => {
          localStorage.removeItem("access_token");
          setToken(null);
        })
        .finally(() => setIsLoading(false));
    } else {
      setIsLoading(false);
    }
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const resp = await authApi.login({ email, password });
    localStorage.removeItem("preview_dev_user");
    localStorage.setItem("access_token", resp.access_token);
    setToken(resp.access_token);
    const me = await authApi.me();
    setUser(me);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("preview_dev_user");
    localStorage.removeItem("access_token");
    setToken(null);
    setUser(null);
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    await authApi.register({ email, password });
    await login(email, password);
  }, [login]);

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, logout, register }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

