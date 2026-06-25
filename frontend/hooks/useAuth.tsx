'use client';
import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { User } from '@/types';
import { getAccessToken, decodeToken, login as loginRequest, logout } from '@/lib/auth';

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string, mfaCode?: string, recoveryCode?: string) => Promise<{ mfaRequired: boolean }>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  isLoading: true,
  login: async () => ({ mfaRequired: false }),
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  function loadUser() {
    const token = getAccessToken();
    if (token) {
      const payload = decodeToken(token) as {
        sub: string;
        org_id: string;
        role: string;
        email: string;
      } | null;
      if (payload) {
        setUser({
          id: payload.sub,
          org_id: payload.org_id,
          role: payload.role as User['role'],
          email: payload.email,
        });
      }
    }
  }

  useEffect(() => {
    loadUser();
    setIsLoading(false);
  }, []);

  async function login(email: string, password: string, mfaCode?: string, recoveryCode?: string) {
    const result = await loginRequest(email, password, mfaCode, recoveryCode);
    if (result.mfa_required) return { mfaRequired: true };
    loadUser();
    return { mfaRequired: false };
  }

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
