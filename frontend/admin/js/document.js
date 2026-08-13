import {
  mountLayout, badge, renderPagination, toast, openModal,
  normalizeStatus, formatFileSize, formatDateTime
} from "./common.js";
import { apiFetch } from "./api.js";

await mountLayout("document");

let page = 1;
const per = 10;
let currentItems = [];

function updateStats(items, total) {
  const statValues = document.querySelectorAll(".stats .stat strong");
  if (statValues.length < 4) return;
  statValues[0].textContent = total ?? items.length;
  statValues[1].textContent = items.filter((d) =>
    ["completed", "succeeded", "success"].includes(String(d.processing_status).toLowerCase())
  ).length;
  statValues[2].textContent = items.filter((d) =>
    ["running", "processing"].includes(String(d.processing_status).toLowerCase())
  ).length;
  statValues[3].textContent = items.filter((d) =>
    String(d.processing_status).toLowerCase() === "failed"
  ).length;
}

function qs() {
  const params = new URLSearchParams({
    page: String(page),
    size: String(per),
  });
  const search = document.querySelector("#keyword").value.trim();
  const type = document.querySelector("#type").value.trim();
  const process = document.querySelector("#process").value.trim();
  const analysis = document.querySelector("#analysis").value.trim();

  if (search) params.set("search", search);
  if (type) params.set("document_type", type);
  if (process) params.set("processing_status", process);
  if (analysis) params.set("analysis_status", analysis);
  return params.toString();
}

async function load() {
  const tbody = document.querySelector("#tbody");
  tbody.innerHTML = `<tr><td colspan="9" class="empty">불러오는 중...</td></tr>`;

  try {
    const data = await apiFetch(`/admin/documents?${qs()}`);
    currentItems = data.items || [];
    document.querySelector("#count").textContent = `총 ${data.total ?? currentItems.length}건`;
    updateStats(currentItems, data.total);

    tbody.innerHTML = currentItems.length
      ? currentItems.map((d) => `
        <tr>
          <td>${d.id}</td>
          <td>${d.announcement_title ?? "-"}</td>
          <td class="title-cell">${d.file_name ?? "-"}</td>
          <td>${d.document_type ?? "-"}</td>
          <td>${formatFileSize(d.file_size)}</td>
          <td>${formatDateTime(d.created_at)}</td>
          <td>${badge(normalizeStatus(d.processing_status ?? d.download_status))}</td>
          <td>${badge(normalizeStatus(d.analysis_status))}</td>
          <td><button class="icon-btn" data-view="${d.id}">⋯</button></td>
        </tr>`).join("")
      : `<tr><td colspan="9" class="empty">조회된 문서가 없습니다.</td></tr>`;

    renderPagination(
      document.querySelector("#pagination"),
      data.total ?? currentItems.length,
      page,
      (next) => { page = next; load(); },
      per,
    );

    document.querySelectorAll("[data-view]").forEach((button) => {
      button.onclick = async () => {
        try {
          const d = await apiFetch(`/admin/documents/${button.dataset.view}`);
          const m = openModal(
            "문서 상세",
            `<p><b>${d.file_name ?? "-"}</b></p>
             <p>연결 공고: ${d.announcement_title ?? "-"}</p>
             <p>문서 유형: ${d.document_type ?? "-"}</p>
             <p>다운로드 상태: ${normalizeStatus(d.download_status)}</p>
             <p>처리 상태: ${normalizeStatus(d.processing_status)}</p>
             <p>분석 상태: ${normalizeStatus(d.analysis_status)}</p>
             <p>Chunk: ${d.chunking?.chunk_count ?? "-"}</p>
             <p>Embedding: ${d.embedding?.completed_count ?? "-"}/${d.embedding?.total_count ?? "-"}</p>`,
            `<button class="btn btn-outline" data-close>닫기</button>
             <button class="btn btn-primary" id="retryBtn">재처리</button>`
          );

          m.querySelector("#retryBtn").onclick = async () => {
            try {
              await apiFetch(`/admin/documents/${d.id}/reprocess`, { method: "POST" });
              toast("문서 재처리를 요청했습니다.");
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
    tbody.innerHTML = `<tr><td colspan="9" class="empty">${error.message}</td></tr>`;
  }
}

document.querySelector("#searchBtn").onclick = () => { page = 1; load(); };
document.querySelector("#refreshBtn").onclick = () => load();

await load();
