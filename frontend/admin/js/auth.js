import { APP_CONFIG } from "./config.js";

export function clearAuthSession() {
  // 실제 인증은 HttpOnly Cookie 기반이므로 JS에서 토큰을 직접 보관하지 않습니다.
  sessionStorage.removeItem("lh_admin_access_token");
  sessionStorage.removeItem("lh_admin_info");
}

export async function loginAdmin(adminId, password) {
  const response = await fetch(`${APP_CONFIG.API_BASE_URL}/admin/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({
      admin_id: adminId,
      password,
    }),
  });

  if (!response.ok) {
    let message = "아이디 또는 비밀번호가 올바르지 않습니다.";
    try {
      const data = await response.json();
      message = data.detail || data.message || message;
    } catch {}
    throw new Error(message);
  }

  // 로그인 API가 반환하는 본문 형식에 의존하지 않고 /me로 최종 확인합니다.
  return getCurrentAdmin();
}

export async function getCurrentAdmin() {
  const response = await fetch(`${APP_CONFIG.API_BASE_URL}/admin/auth/me`, {
    method: "GET",
    credentials: "include",
    headers: { Accept: "application/json" },
  });

  if (response.status === 401) {
    clearAuthSession();
    return null;
  }

  if (!response.ok) {
    throw new Error("관리자 정보를 확인하지 못했습니다.");
  }

  const data = await response.json();
  return {
    ...data,
    name: data.name || data.admin_name || data.login_id || data.admin_id || "관리자",
    role: data.role || "admin",
  };
}

export async function logoutAdmin() {
  try {
    await fetch(`${APP_CONFIG.API_BASE_URL}/admin/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
  } finally {
    clearAuthSession();
  }
}
