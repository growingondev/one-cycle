import { logoutAdmin } from "./auth.js";
import { requireAdminAuth } from "./guard.js";
import { APP_CONFIG } from "./config.js";

export async function mountLayout(page) {
  const admin = await requireAdminAuth();
  if (!admin) return null;

  const [sidebarHtml, headerHtml] = await Promise.all([
    fetch("./components/sidebar.html").then((response) => response.text()),
    fetch("./components/header.html").then((response) => response.text()),
  ]);

  document.querySelector("#sidebarMount").innerHTML = sidebarHtml;
  document.querySelector("#headerMount").innerHTML = headerHtml;

  document.querySelector(`[data-page="${page}"]`)?.classList.add("active");

  const sidebar = document.querySelector("#sidebar");
  const overlay = document.querySelector("#overlay");

  document.querySelector("#menuBtn")?.addEventListener("click", () => {
    sidebar.classList.add("open");
    overlay.classList.add("show");
  });

  overlay?.addEventListener("click", () => {
    sidebar.classList.remove("open");
    overlay.classList.remove("show");
  });

  document.querySelector("[data-admin-name]")?.replaceChildren(admin.name || "관리자");

  document.querySelector("[data-logout]")?.addEventListener("click", async () => {
    await logoutAdmin();
    window.location.replace(APP_CONFIG.LOGIN_PAGE);
  });

  return admin;
}

export function toast(message) {
  const toastElement = document.createElement("div");
  toastElement.className = "toast";
  toastElement.textContent = message;
  document.body.appendChild(toastElement);
  setTimeout(() => toastElement.remove(), 2200);
}

export function openModal(title, html, footer = "") {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <section class="modal" role="dialog" aria-modal="true" aria-label="${title}">
      <div class="modal-head">
        <strong>${title}</strong>
        <button class="icon-btn" type="button" data-close aria-label="닫기">✕</button>
      </div>
      <div class="modal-body">${html}</div>
      ${footer ? `<div class="modal-foot">${footer}</div>` : ""}
    </section>
  `;

  document.body.appendChild(backdrop);

  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop || event.target.closest("[data-close]")) {
      backdrop.remove();
    }
  });

  return backdrop;
}

export function badge(value) {
  let color = "gray";
  if (/완료|공고중|정상|해결완료/.test(value)) color = "green";
  else if (/진행|처리중|분석중|해결중/.test(value)) color = "orange";
  else if (/실패|오류|미해결/.test(value)) color = "red";
  else if (/대기|예정|접수중/.test(value)) color = "blue";

  return `<span class="badge ${color}">${value}</span>`;
}

export function paginate(items, page, perPage = 6) {
  return items.slice((page - 1) * perPage, page * perPage);
}

export function renderPagination(element, total, page, onChange, perPage = 6) {
  const totalPages = Math.max(1, Math.ceil(total / perPage));
  element.innerHTML = Array.from(
    { length: totalPages },
    (_, index) =>
      `<button class="${index + 1 === page ? "active" : ""}" data-page-number="${index + 1}">${index + 1}</button>`,
  ).join("");

  element.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => onChange(Number(button.dataset.pageNumber)));
  });
}

export function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("ko-KR", { hour12: false });
}

export function formatFileSize(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 0) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

export function normalizeStatus(value) {
  const raw = String(value ?? "").toLowerCase();
  const map = {
    completed: "완료",
    succeeded: "완료",
    success: "완료",
    running: "처리중",
    processing: "처리중",
    pending: "대기",
    failed: "실패",
    failure: "실패",
    pass: "분석완료",
    open: "미해결",
    unresolved: "미해결",
    in_progress: "해결중",
    resolved: "해결완료",
    published: "공고중",
    active: "공고중",
    closed: "마감",
  };
  return map[raw] || value || "-";
}
