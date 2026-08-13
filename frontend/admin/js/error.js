import {
  mountLayout, badge, renderPagination, toast, openModal,
  normalizeStatus, formatDateTime
} from "./common.js";
import { apiFetch } from "./api.js";

await mountLayout("error");

let page = 1;
const per = 10;
let currentItems = [];

function updateStats(items, total) {
  const statValues = document.querySelectorAll(".stats .stat strong");
  if (statValues.length < 4) return;
  statValues[0].textContent = total ?? items.length;
  statValues[1].textContent = items.filter((e) =>
    ["open", "unresolved"].includes(String(e.status).toLowerCase())
  ).length;
  statValues[2].textContent = items.filter((e) =>
    ["in_progress", "processing"].includes(String(e.status).toLowerCase())
  ).length;
  statValues[3].textContent = items.filter((e) =>
    ["resolved", "closed"].includes(String(e.status).toLowerCase())
  ).length;
}

function qs() {
  const params = new URLSearchParams({
    page: String(page),
    size: String(per),
  });
  const search = document.querySelector("#keyword").value.trim();
  const type = document.querySelector("#type").value.trim();
  const status = document.querySelector("#status").value.trim();

  if (search) params.set("search", search);
  if (type) params.set("error_type", type);
  if (status) params.set("status", status);
  return params.toString();
}

function targetLabel(e) {
  return e.announcement_title || e.target || e.document_name || "-";
}

async function load() {
  const tbody = document.querySelector("#tbody");
  tbody.innerHTML = `<tr><td colspan="8" class="empty">불러오는 중...</td></tr>`;

  try {
    const data = await apiFetch(`/admin/errors?${qs()}`);
    currentItems = data.items || [];
    document.querySelector("#count").textContent = `총 ${data.total ?? currentItems.length}건`;
    updateStats(currentItems, data.total);

    tbody.innerHTML = currentItems.length
      ? currentItems.map((e) => `
        <tr>
          <td>${e.id}</td>
          <td>${formatDateTime(e.occurred_at ?? e.created_at ?? e.time)}</td>
          <td>${e.error_type ?? e.type ?? "-"}</td>
          <td>${e.stage ?? e.step ?? "-"}</td>
          <td>${targetLabel(e)}</td>
          <td class="title-cell">${e.message ?? e.error_message ?? "-"}</td>
          <td>${badge(normalizeStatus(e.status))}</td>
          <td><button class="icon-btn" data-view="${encodeURIComponent(e.id)}">⋯</button></td>
        </tr>`).join("")
      : `<tr><td colspan="8" class="empty">조회된 오류가 없습니다.</td></tr>`;

    renderPagination(
      document.querySelector("#pagination"),
      data.total ?? currentItems.length,
      page,
      (next) => { page = next; load(); },
      per,
    );

    document.querySelectorAll("[data-view]").forEach((button) => {
      button.onclick = async () => {
        const id = decodeURIComponent(button.dataset.view);
        try {
          const e = await apiFetch(`/admin/errors/${encodeURIComponent(id)}`);
          const m = openModal(
            "오류 상세",
            `<p><b>${targetLabel(e)}</b></p>
             <p>오류 유형: ${e.error_type ?? e.type ?? "-"}</p>
             <p>발생 구간: ${e.stage ?? e.step ?? "-"}</p>
             <p>발생 시각: ${formatDateTime(e.occurred_at ?? e.created_at)}</p>
             <div class="card" style="padding:14px;background:#fafbfe">${e.message ?? e.error_message ?? "-"}</div>`,
            `<button class="btn btn-outline" data-close>닫기</button>
             <button class="btn btn-primary" id="retryBtn">재시도</button>`
          );

          m.querySelector("#retryBtn").onclick = async () => {
            try {
              await apiFetch(`/admin/errors/${encodeURIComponent(id)}/retry`, { method: "POST" });
              toast("오류 재시도를 요청했습니다.");
              m.remove();
              await load();
            } catch (error) {
              toast(error.message);
            }
          };
        } catch (error) {
          toast(error.message);
        }
      };
    });
  } catch (error) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty">${error.message}</td></tr>`;
  }
}

document.querySelector("#searchBtn").onclick = () => { page = 1; load(); };
document.querySelector("#downloadBtn").onclick = () => toast("MVP에서는 목록 다운로드를 연결하지 않았습니다.");

await load();
