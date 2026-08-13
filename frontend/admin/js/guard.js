import { APP_CONFIG } from "./config.js";
import { getCurrentAdmin } from "./auth.js";

export async function requireAdminAuth() {
  try {
    const admin = await getCurrentAdmin();
    if (!admin || admin.role !== "admin") {
      window.location.replace(APP_CONFIG.LOGIN_PAGE);
      return null;
    }
    return admin;
  } catch {
    window.location.replace(APP_CONFIG.LOGIN_PAGE);
    return null;
  }
}

export async function redirectAuthenticatedAdmin() {
  try {
    const admin = await getCurrentAdmin();
    if (admin?.role === "admin") {
      window.location.replace(APP_CONFIG.DEFAULT_ADMIN_PAGE);
    }
  } catch {
    // 로그인 화면에서는 API 오류가 있어도 그대로 머뭅니다.
  }
}
