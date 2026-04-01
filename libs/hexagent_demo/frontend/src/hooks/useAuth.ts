import { useState, useCallback } from "react";

const AUTH_TOKEN_KEY = "auth_token";
const USER_INFO_KEY = "user_info";
const API_TOKEN_INFO_KEY = "api_token_info";

export interface UserInfo {
  token: string;
  phone?: string;
  [key: string]: unknown;
}

export interface ApiTokenInfo {
  access_token: string;
  expires_in: number;
  scope: string;
  successDate: string;
}

export interface AuthState {
  isAuthenticated: boolean;
  user: UserInfo | null;
  token: string | null;
}

function loadAuthState(): AuthState {
  try {
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    const userRaw = localStorage.getItem(USER_INFO_KEY);
    if (token && userRaw) {
      return {
        isAuthenticated: true,
        user: JSON.parse(userRaw),
        token,
      };
    }
  } catch {
    // ignore
  }
  return { isAuthenticated: false, user: null, token: null };
}

export function useAuth() {
  const [authState, setAuthState] = useState<AuthState>(loadAuthState);

  const login = useCallback((token: string, userData: Record<string, unknown>, expiresIn: number, scope: string) => {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
    localStorage.setItem(USER_INFO_KEY, JSON.stringify(userData));
    localStorage.setItem(API_TOKEN_INFO_KEY, JSON.stringify({
      access_token: token,
      expires_in: expiresIn,
      scope,
      successDate: new Date().toISOString(),
    }));
    setAuthState({
      isAuthenticated: true,
      user: userData as UserInfo,
      token,
    });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    localStorage.removeItem(USER_INFO_KEY);
    localStorage.removeItem(API_TOKEN_INFO_KEY);
    setAuthState({ isAuthenticated: false, user: null, token: null });
  }, []);

  return { ...authState, login, logout };
}
