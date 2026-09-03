import uuid
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

if __package__:
    from .crawler import (
        crawl_lh_notices,
        recollect_lh_notice,
        scan_lh_notice_list,
    )
else:
    from crawler import (
        crawl_lh_notices,
        recollect_lh_notice,
        scan_lh_notice_list,
    )

app = FastAPI(title="LH Crawler API")

# MVP 제약사항: Job 상태는 메모리에 저장되므로 컨테이너 재시작 시 초기화됩니다.
# (완료된 Job 자동 삭제 및 영구 저장은 후속 개선 사항으로 진행)
jobs = {}

# 개별 공고 재수집 API 요청 데이터 모델
class RecollectRequest(BaseModel):
    source_announcement_id: str
    detail_url: str
    target_file_name: str | None = None

def is_crawler_busy() -> bool:
    """동시 크롤링 실행 방지: 이미 실행 중이거나 대기 중인 작업이 있는지 확인"""
    for job in jobs.values():
        if job["status"] in ["queued", "running"]:
            return True
    return False

def run_crawl_task(job_id: str):
    """전체 공고 수집 백그라운드 작업"""
    jobs[job_id]["status"] = "running"
    try:
        result = crawl_lh_notices()
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["result"] = result
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error_code"] = "CRAWLER_EXECUTION_FAILED"
        jobs[job_id]["message"] = f"크롤링 전체 수집 실패: {str(e)}"


def run_scan_task(job_id: str) -> None:
    """공고 목록 메타데이터 스캔 백그라운드 작업"""
    jobs[job_id]["status"] = "running"
    try:
        result = scan_lh_notice_list()
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["result"] = result
    except Exception as exc:  # noqa: BLE001 - 백그라운드 작업 실패를 상태로 보존한다.
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error_code"] = "SCAN_EXECUTION_FAILED"
        jobs[job_id]["message"] = f"공고 목록 스캔 실패: {exc!s}"

def run_recollect_task(
    job_id: str,
    source_announcement_id: str,
    detail_url: str,
    target_file_name: str | None = None,
):
    """개별 공고 재수집 백그라운드 작업"""
    jobs[job_id]["status"] = "running"
    try:
        result = recollect_lh_notice(
            source_announcement_id,
            detail_url,
            target_file_name=target_file_name,
        )
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["result"] = result
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error_code"] = "RECOLLECT_EXECUTION_FAILED"
        jobs[job_id]["message"] = f"개별 공고 재수집 실패: {str(e)}"

@app.post("/v1/crawl-jobs")
async def create_crawl_job(background_tasks: BackgroundTasks):
    """전체 수집 요청 API"""
    if is_crawler_busy():
        raise HTTPException(
            status_code=409, 
            detail={"error_code": "CRAWLER_JOB_ALREADY_RUNNING", "message": "이미 실행 중이거나 대기 중인 크롤링 작업이 있습니다."}
        )
    
    job_id = f"execution_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    jobs[job_id] = {"job_id": job_id, "status": "queued"}
    
    background_tasks.add_task(run_crawl_task, job_id)
    return {"job_id": job_id, "status": "queued"}

@app.post("/v1/recollect-jobs")
async def create_recollect_job(req: RecollectRequest, background_tasks: BackgroundTasks):
    """개별 공고 재수집 요청 API"""
    if is_crawler_busy():
        raise HTTPException(
            status_code=409, 
            detail={"error_code": "CRAWLER_JOB_ALREADY_RUNNING", "message": "이미 실행 중이거나 대기 중인 크롤링 작업이 있습니다."}
        )
    
    job_id = f"recollect_{req.source_announcement_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    jobs[job_id] = {"job_id": job_id, "status": "queued"}
    
    background_tasks.add_task(
        run_recollect_task,
        job_id,
        req.source_announcement_id,
        req.detail_url,
        req.target_file_name,
    )
    return {"job_id": job_id, "status": "queued"}


@app.post("/v1/scan-jobs")
async def create_scan_job(background_tasks: BackgroundTasks):
    """파일 다운로드 없는 공고 목록 스캔 요청 API"""
    if is_crawler_busy():
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "CRAWLER_JOB_ALREADY_RUNNING",
                "message": "이미 실행 중이거나 대기 중인 크롤링 작업이 있습니다.",
            },
        )

    job_id = (
        f"scan_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        f"_{uuid.uuid4().hex[:6]}"
    )
    jobs[job_id] = {"job_id": job_id, "status": "queued"}

    background_tasks.add_task(run_scan_task, job_id)
    return {"job_id": job_id, "status": "queued"}

@app.get("/v1/crawl-jobs/{job_id}")
async def get_crawl_job_status(job_id: str):
    """작업 상태 조회 API (전체/개별 공통)"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    response = {"job_id": job_id, "status": job["status"]}
    
    if job["status"] == "failed":
        response["error_code"] = job.get("error_code")
        response["message"] = job.get("message")
        
    return response

@app.get("/v1/crawl-jobs/{job_id}/result")
async def get_crawl_job_result(job_id: str):
    """작업 결과 반환 API (전체/개별 공통)"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    response = {"job_id": job_id, "status": job["status"]}
    
    if job["status"] == "completed":
        response["result"] = job.get("result")
    elif job["status"] == "failed":
        response["error_code"] = job.get("error_code")
        response["message"] = job.get("message")
        
    return response

@app.get("/health")
async def health_check():
    return {"status": "ok"}
