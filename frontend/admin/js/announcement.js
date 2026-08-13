import {
  mountLayout, badge, renderPagination, toast, openModal,
  normalizeStatus
} from "./common.js";
import { apiFetch } from "./api.js";

await mountLayout("announcement");

let page = 1;
const per = 10;
let currentItems = [];

function qs() {
  const params = new URLSearchParams({
    page: String(page),
    size: String(per),
  });
  const search = document.querySelector("#keyword").value.trim();
  const status = document.querySelector("#status").value.trim();
  const collect = document.querySelector("#collect").value.trim();

  if (search) params.set("search", search);
  if (status) params.set("announcement_status", status);
  if (collect) params.set("collection_status", collect);
  return params.toString();
}

async function load() {
  const tbody = document.querySelector("#tbody");
  tbody.innerHTML = `<tr><td colspan="7" class="empty">불러오는 중...</td></tr>`;

  try {
    const data = await apiFetch(`/admin/announcements?${qs()}`);
    currentItems = data.items || [];
    document.querySelector("#count").textContent = `총 ${data.total ?? currentItems.length}건`;

    tbody.innerHTML = currentItems.length
      ? currentItems.map((n) => `
        <tr>
          <td>${n.id}</td>
          <td class="title-cell">${n.title ?? "-"}</td>
          <td>${n.region ?? "-"}</td>
          <td>${n.announcement_date ?? n.announcementDate ?? "-"}</td>
          <td>${badge(normalizeStatus(n.announcement_status ?? n.publication_status))}</td>
          <td>${badge(normalizeStatus(n.collection_status))}</td>
          <td><button class="icon-btn" data-view="${n.id}">⋯</button></td>
        </tr>`).join("")
      : `<tr><td colspan="7" class="empty">조회된 공고가 없습니다.</td></tr>`;

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
          const n = await apiFetch(`/admin/announcements/${button.dataset.view}`);
          openModal(
            "공고 상세",
            `<p><b>${n.title ?? "-"}</b></p>
             <p>지역: ${n.region ?? "-"}</p>
             <p>공고일: ${n.announcement_date ?? "-"}</p>
             <p>신청 시작: ${n.application_start ?? "-"}</p>
             <p>신청 종료: ${n.application_end ?? "-"}</p>
             <p>공고 상태: ${normalizeStatus(n.announcement_status)}</p>
             <p>수집 상태: ${normalizeStatus(n.collection_status)}</p>`
          );
        } catch (error) {
          toast(error.message);
        }
      };
    });
  } catch (error) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty">${error.message}</td></tr>`;
  }
}

document.querySelector("#searchBtn").onclick = () => { page = 1; load(); };
document.querySelector("#resetBtn").onclick = () => {
  document.querySelectorAll(".filters input,.filters select").forEach((el) => el.value = "");
  page = 1;
  load();
};
document.querySelector("#collectBtn").onclick = async () => {
  try {
    await apiFetch("/admin/announcements/collect", { method: "POST" });
    toast("공고 수집 작업을 요청했습니다.");
    await load();
  } catch (error) {
    toast(error.message);
  }
};

await load();
