import { loginAdmin } from "./auth.js";
import { APP_CONFIG } from "./config.js";
import { redirectAuthenticatedAdmin } from "./guard.js";

await redirectAuthenticatedAdmin();

const form = document.querySelector("#loginForm");
const passwordInput = document.querySelector("#password");
const toggleButton = document.querySelector("#togglePassword");
const errorMessage = document.querySelector("#loginError");
const loginButton = document.querySelector("#loginButton");

toggleButton.addEventListener("click", () => {
  const showPassword = passwordInput.type === "password";
  passwordInput.type = showPassword ? "text" : "password";
  toggleButton.textContent = showPassword ? "숨김" : "보기";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorMessage.textContent = "";

  const adminId = form.adminId.value.trim();
  const password = passwordInput.value;

  if (!adminId || !password) {
    errorMessage.textContent = "아이디와 비밀번호를 모두 입력해 주세요.";
    return;
  }

  loginButton.disabled = true;
  loginButton.textContent = "로그인 중...";

  try {
    await loginAdmin(adminId, password);
    window.location.replace(APP_CONFIG.DEFAULT_ADMIN_PAGE);
  } catch (error) {
    errorMessage.textContent = error.message;
    loginButton.disabled = false;
    loginButton.textContent = "로그인";
  }
});
