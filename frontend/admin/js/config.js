export const APP_CONFIG = Object.freeze({
  // serve_admin.py가 /api 요청을 FastAPI(127.0.0.1:8000)로 프록시합니다.
  API_BASE_URL: "/api",
  USE_MOCK_AUTH: false,
  LOGIN_PAGE: "./login.html",
  DEFAULT_ADMIN_PAGE: "./announcement.html",
});
