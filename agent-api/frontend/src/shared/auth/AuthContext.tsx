import { ReactNode, createContext, useContext, useEffect, useMemo, useState } from 'react';
import { AUTH_EXPIRED_EVENT, api, clearAuthToken, getAuthToken, setAuthToken } from '@shared/api/client';

interface LoginInput {
  username: string;
  password: string;
  remember: boolean;
}

interface AuthContextValue {
  isAuthenticated: boolean;
  login: (input: LoginInput) => Promise<boolean>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(() => Boolean(getAuthToken()));

  useEffect(() => {
    if (!getAuthToken()) return;
    api.me().catch(() => {
      clearAuthToken();
      setIsAuthenticated(false);
    });
  }, []);

  useEffect(() => {
    const onAuthExpired = () => setIsAuthenticated(false);
    window.addEventListener(AUTH_EXPIRED_EVENT, onAuthExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onAuthExpired);
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    isAuthenticated,
    login: async ({ username, password, remember }) => {
      if (!username.trim() || !password.trim()) return false;
      const response = await api.login(username, password);
      setAuthToken(response.access_token, remember);
      setIsAuthenticated(true);
      return true;
    },
    logout: () => {
      clearAuthToken();
      setIsAuthenticated(false);
    },
  }), [isAuthenticated]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider');
  }
  return context;
}
