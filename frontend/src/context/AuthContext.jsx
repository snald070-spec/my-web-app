import { createContext, useContext, useEffect, useState } from "react";
import api from "../api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem("user");
      return stored ? JSON.parse(stored) : null;
    } catch {
      localStorage.clear();
      return null;
    }
  });

  // On mount, refresh user profile from server to pick up any role changes
  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) return;
    api.get("/api/auth/me").then(({ data }) => {
      setUser((prev) => {
        if (!prev) return prev;
        const next = { ...prev, ...data };
        localStorage.setItem("user", JSON.stringify(next));
        return next;
      });
    }).catch(() => {
      // token expired or invalid — log out silently
      localStorage.clear();
      setUser(null);
    });
  }, []);

  async function login(nameId, password) {
    const form = new URLSearchParams({ username: nameId, password });
    const { data } = await api.post("/api/auth/login", form);
    localStorage.setItem("token", data.access_token);
    localStorage.setItem("user",  JSON.stringify(data));
    setUser(data);
    return data;
  }

  function updateUser(updates) {
    setUser(prev => {
      const next = { ...prev, ...updates };
      localStorage.setItem("user", JSON.stringify(next));
      return next;
    });
  }

  function logout() {
    localStorage.clear();
    sessionStorage.clear();
    setUser(null);
  }

  return (
    <AuthCtx.Provider value={{ user, login, logout, updateUser }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
