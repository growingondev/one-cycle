import { APP_CONFIG } from "./config.js";
import { clearAuthSession } from "./auth.js";

export async function apiFetch(path, options = {}) {
  const response = await fetch(`${APP_CONFIG.API_BASE_URL}${path}`, {
    credentials: "include",
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body && !(options.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...(options.headers || {}),
    },
  });

  if (response.status === 401) {
    clearAuthSession();
    window.location.replace(APP_CONFIG.LOGIN_PAGE);
    throw new Error("로그인이 필요하거나 세션이 만료되었습니다.");
  }

  if (!response.ok) {
    let message = `요청을 처리하지 못했습니다. (${response.status})`;
    try {
      const data = await response.json();
      message = data.detail || data.message || message;
    } catch {}
    throw new Error(message);
  }

  if (response.status === 204) return null;

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return response.json();
  return response.text();
}
