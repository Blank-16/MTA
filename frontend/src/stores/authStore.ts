"use client";
import { create } from "zustand";

interface AuthState {
  accessToken: string | null;
  expiresAt: number | null;
  userId: string | null;
  isAuthenticated: boolean;
  setTokens: (accessToken: string, expiresIn: number) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>()((set) => ({
  accessToken: null,
  expiresAt: null,
  userId: null,
  isAuthenticated: false,

  setTokens(accessToken: string, expiresIn: number) {
    const expiresAt = Date.now() + expiresIn * 1000;
    let userId: string | null = null;
    try {
      const payload = JSON.parse(atob(accessToken.split(".")[1]));
      userId = payload.sub ?? null;
    } catch { /* ignore malformed token */ }
    set({ accessToken, expiresAt, userId, isAuthenticated: true });
  },

  clearAuth() {
    set({ accessToken: null, expiresAt: null, userId: null, isAuthenticated: false });
  },
}));

export function isTokenExpiringSoon(expiresAt: number | null): boolean {
  if (expiresAt === null) return true;
  return Date.now() > expiresAt - 60_000;
}

// FIX: single in-flight refresh promise — prevents concurrent token rotations
// that would cause the second request's token to be immediately revoked.
let _refreshPromise: Promise<string | null> | null = null;

export async function refreshAccessToken(): Promise<string | null> {
  if (_refreshPromise) return _refreshPromise;

  _refreshPromise = (async () => {
    try {
      const res = await fetch("/api/auth/refresh", { method: "POST" });
      if (!res.ok) {
        useAuthStore.getState().clearAuth();
        return null;
      }
      const data = await res.json() as { access_token: string; expires_in: number };
      useAuthStore.getState().setTokens(data.access_token, data.expires_in);
      return data.access_token;
    } catch {
      // Network failure — clear auth state so UI shows logged-out correctly.
      // isAuthenticated=true with accessToken=null causes silent 401s on every request.
      useAuthStore.getState().clearAuth();
      return null;
    } finally {
      _refreshPromise = null;
    }
  })();

  return _refreshPromise;
}

export async function getValidToken(): Promise<string | null> {
  const { accessToken, expiresAt } = useAuthStore.getState();
  if (accessToken && !isTokenExpiringSoon(expiresAt)) return accessToken;
  return refreshAccessToken();
}
