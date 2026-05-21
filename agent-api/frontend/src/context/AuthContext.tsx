import { ReactNode, createContext, useContext, useMemo, useState } from 'react';

const SESSION_KEY = 'robotersteve.invoice-manager.session';

interface LoginInput {
  email: string;
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
  const [isAuthenticated, setIsAuthenticated] = useState(() => (
    localStorage.getItem(SESSION_KEY) === 'active' || sessionStorage.getItem(SESSION_KEY) === 'active'
  ));

  const value = useMemo<AuthContextValue>(() => ({
    isAuthenticated,
    login: async ({ email, password, remember }) => {
      const isValid = email.trim().length > 0 && password.trim().length > 0;
      if (!isValid) return false;

      const storage = remember ? localStorage : sessionStorage;
      storage.setItem(SESSION_KEY, 'active');
      setIsAuthenticated(true);
      return true;
    },
    logout: () => {
      localStorage.removeItem(SESSION_KEY);
      sessionStorage.removeItem(SESSION_KEY);
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
