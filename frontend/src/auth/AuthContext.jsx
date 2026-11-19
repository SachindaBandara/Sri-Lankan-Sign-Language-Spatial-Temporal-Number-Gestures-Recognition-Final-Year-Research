import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { getCurrentUser, loginStudent, logoutStudent, registerStudent } from "../services/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setUser(await getCurrentUser());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh().catch(() => setUser(null));
  }, [refresh]);

  const signIn = useCallback(async (credentials) => {
    const result = await loginStudent(credentials);
    setUser(result.user);
    return result.user;
  }, []);

  const signUp = useCallback(async (details) => {
    const result = await registerStudent(details);
    setUser(result.user);
    return result.user;
  }, []);

  const signOut = useCallback(async () => {
    await logoutStudent();
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, loading, refresh, signIn, signUp, signOut }), [
    user, loading, refresh, signIn, signUp, signOut,
  ]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider");
  return value;
}
