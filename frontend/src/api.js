import axios from "axios";
import { getApiBaseUrl } from "./utils/runtimeConfig";

const api = axios.create({
  baseURL: getApiBaseUrl(),
  timeout: 15000,
});

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

let _isLoggingOut = false;

function _doLogout() {
  if (_isLoggingOut) return;
  _isLoggingOut = true;
  localStorage.removeItem("token");
  localStorage.removeItem("tokenExpiresAt");
  localStorage.removeItem("user");
  sessionStorage.clear();
  window.location.href = "/";
}

// On 401: try token refresh once, then logout if that also fails
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config;
    const status = err.response?.status;

    // Skip refresh loop only for pure auth endpoints (login/google/refresh) to avoid infinite loops
    const isAuthEndpoint =
      original?.url?.includes("/auth/login") ||
      original?.url?.includes("/auth/google") ||
      original?.url?.includes("/auth/refresh");
    if (status === 401 && !original?._retried && !isAuthEndpoint) {
      original._retried = true;
      try {
        const { data } = await api.post("/api/auth/refresh");
        localStorage.setItem("token", data.access_token);
        if (data.expires_in) {
          localStorage.setItem(
            "tokenExpiresAt",
            String(Date.now() + data.expires_in * 1000)
          );
        }
        original.headers = original.headers || {};
        original.headers.Authorization = `Bearer ${data.access_token}`;
        return api(original);
      } catch {
        _doLogout();
        return Promise.reject(err);
      }
    }

    if (status === 401 && !isAuthEndpoint) {
      _doLogout();
    }

    return Promise.reject(err);
  }
);

export default api;
