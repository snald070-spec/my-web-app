import { createContext, useContext, useEffect, useState, useRef } from "react";
import api from "../api";
import { requestAndSubscribe, isSubscribed } from "../services/notificationService";

const AuthCtx = createContext(null);

const REFRESH_MARGIN_MS = 5 * 60 * 1000; // refresh 5 min before expiry

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
  const refreshTimerRef = useRef(null);

  function _scheduleRefresh(expiresAt) {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    const delay = Math.max(0, expiresAt - Date.now() - REFRESH_MARGIN_MS);
    if (delay > 0) {
      refreshTimerRef.current = setTimeout(_proactiveRefresh, delay);
    }
  }

  async function _proactiveRefresh() {
    try {
      const { data } = await api.post("/api/auth/refresh");
      localStorage.setItem("token", data.access_token);
      const newExpiresAt = Date.now() + (data.expires_in || 7200) * 1000;
      localStorage.setItem("tokenExpiresAt", String(newExpiresAt));
      setUser((prev) => {
        if (!prev) return prev;
        const next = { ...prev, ...data };
        localStorage.setItem("user", JSON.stringify(next));
        return next;
      });
      _scheduleRefresh(newExpiresAt);
    } catch {
      // api.js interceptor handles logout on failure
    }
  }

  // On mount: validate token, schedule refresh, retry on transient errors
  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) return;

    const expiresAtStr = localStorage.getItem("tokenExpiresAt");
    if (expiresAtStr) {
      _scheduleRefresh(Number(expiresAtStr));
    }

    let retries = 0;
    function fetchMe() {
      api.get("/api/auth/me").then(({ data }) => {
        setUser((prev) => {
          if (!prev) return prev;
          const next = { ...prev, ...data };
          localStorage.setItem("user", JSON.stringify(next));
          return next;
        });
      }).catch((err) => {
        const status = err.response?.status;
        if (status === 401 || status === 403) return; // interceptor handles logout
        if (retries < 3) {
          retries++;
          setTimeout(fetchMe, 2000 * retries); // 2s, 4s, 6s back-off
        }
      });
    }
    fetchMe();

    return () => {
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    };
  }, []);

  function _subscribeAfterLogin() {
    // 로그인 후 알림 권한이 아직 없으면 요청. 이미 구독된 경우는 스킵.
    if (!isSubscribed()) {
      setTimeout(() => requestAndSubscribe(), 1500);
    }
  }

  async function login(nameId, password) {
    const form = new URLSearchParams({ username: nameId, password });
    const { data } = await api.post("/api/auth/login", form);
    localStorage.setItem("token", data.access_token);
    if (data.expires_in) {
      const expiresAt = Date.now() + data.expires_in * 1000;
      localStorage.setItem("tokenExpiresAt", String(expiresAt));
      _scheduleRefresh(expiresAt);
    }
    localStorage.setItem("user", JSON.stringify(data));
    setUser(data);
    _subscribeAfterLogin();
    return data;
  }

  async function loginWithGoogle(accessToken) {
    const { data } = await api.post("/api/auth/google", { access_token: accessToken });
    localStorage.setItem("token", data.access_token);
    if (data.expires_in) {
      const expiresAt = Date.now() + data.expires_in * 1000;
      localStorage.setItem("tokenExpiresAt", String(expiresAt));
      _scheduleRefresh(expiresAt);
    }
    localStorage.setItem("user", JSON.stringify(data));
    setUser(data);
    _subscribeAfterLogin();
    return data;
  }

  function updateUser(updates) {
    setUser((prev) => {
      const next = { ...prev, ...updates };
      localStorage.setItem("user", JSON.stringify(next));
      return next;
    });
  }

  function logout() {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    localStorage.clear();
    sessionStorage.clear();
    setUser(null);
  }

  return (
    <AuthCtx.Provider value={{ user, login, loginWithGoogle, logout, updateUser }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
