import { APP_CONFIG } from "./config.js";

function base64UrlEncode(value) {
  return btoa(unescape(encodeURIComponent(JSON.stringify(value))))
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
}

function base64UrlDecode(value) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
  return JSON.parse(decodeURIComponent(escape(atob(padded))));
}

export function createMockJwt(admin) {
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "none", typ: "JWT" };
  const payload = {
    sub: String(admin.id),
    login_id: admin.loginId,
    name: admin.name,
    role: admin.role,
    type: "access",
    iat: now,
    exp: now + APP_CONFIG.TOKEN_TTL_SECONDS,
  };

  // API 연결 전 화면 흐름 확인용 토큰입니다.
  // 서명되지 않았으므로 실제 인증/보안 수단으로 사용하면 안 됩니다.
  return `${base64UrlEncode(header)}.${base64UrlEncode(payload)}.mock-signature`;
}

export function decodeJwtPayload(token) {
  if (!token || typeof token !== "string") return null;

  const parts = token.split(".");
  if (parts.length !== 3) return null;

  try {
    return base64UrlDecode(parts[1]);
  } catch {
    return null;
  }
}

export function isJwtExpired(token) {
  const payload = decodeJwtPayload(token);
  if (!payload?.exp) return true;
  return Math.floor(Date.now() / 1000) >= payload.exp;
}
