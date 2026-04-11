function trimTrailingSlash(value) {
  return String(value || "").replace(/\/+$/, "");
}

function isHttpLikeProtocol(protocol) {
  return protocol === "http:" || protocol === "https:";
}

export function getApiBaseUrl() {
  const isProd = Boolean(import.meta.env.PROD);
  const envValue = trimTrailingSlash(import.meta.env.VITE_API_BASE_URL || "");
  if (envValue) {
    if (isProd && !envValue.startsWith("https://")) {
      throw new Error("Production builds require VITE_API_BASE_URL to use HTTPS.");
    }
    return envValue;
  }

  const protocol = window?.location?.protocol || "";
  if (isHttpLikeProtocol(protocol)) {
    // Web mode: keep relative URL so Vite proxy and same-origin backend both work.
    return "";
  }

  if (isProd) {
    throw new Error("Set VITE_API_BASE_URL to an HTTPS endpoint for production builds.");
  }

  // Capacitor/WebView fallback for Android emulator.
  return "http://10.0.2.2:8000";
}
