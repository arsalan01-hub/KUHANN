import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, getToken, setToken } from '../api/client';
import type { User } from '../api/types';

interface AuthContextValue {
  user: User | null;
  permissions: string[];
  loading: boolean;
  login: (email: string, password: string, totp?: string) => Promise<{ totpRequired: boolean }>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  can: (permission: string | string[]) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api.get<User>('/auth/me');
      setUser(me);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const onUnauthorized = () => setUser(null);
    window.addEventListener('kuhhan:unauthorized', onUnauthorized);
    return () => window.removeEventListener('kuhhan:unauthorized', onUnauthorized);
  }, []);

  const login = useCallback(async (email: string, password: string, totp?: string) => {
    try {
      const response = await api.post<{ access_token: string; user: User }>('/auth/login', {
        email,
        password,
        totp_code: totp || null,
      });
      setToken(response.access_token);
      setUser(response.user);
      return { totpRequired: false };
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Login failed';
      if (message === 'totp_required') return { totpRequired: true };
      throw error;
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout');
    } catch {
      /* token may already be invalid */
    }
    setToken(null);
    setUser(null);
  }, []);

  const permissions = useMemo(() => user?.permission_codes ?? [], [user]);

  const can = useCallback(
    (permission: string | string[]) => {
      if (!user) return false;
      if (permissions.includes('*')) return true;
      const list = Array.isArray(permission) ? permission : [permission];
      return list.some((item) => permissions.includes(item));
    },
    [permissions, user],
  );

  const value = useMemo<AuthContextValue>(
    () => ({ user, permissions, loading, login, logout, refresh, can }),
    [user, permissions, loading, login, logout, refresh, can],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
