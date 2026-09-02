from fastapi import FastAPI, BackgroundTasks, HTTPException
from datetime import datetime
import uuid
import asyncio

# 기존에 잘 만들어둔 크롤러 함수를 불러옵니다.
from crawler import crawl_lh_notices

app = FastAPI(title="LH Crawler API")

# 크롤링 작업의 상태와 결과를 저장할 메모리 공간 (DB 대신 사용)
jobs = {}

def run_crawler_task(job_id: str):
    """백그라운드에서 실제 크롤러를 돌리는 함수"""
    try:
        # 기존 crawler.py의 함수 실행 (20분 소요)
        result = crawl_lh_notices()
        
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["result"] = result
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)

@app.post("/v1/crawl-jobs")
async def create_crawl_job(background_tasks: BackgroundTasks):
    """1. 수집 요청 API (전화 끊고 백그라운드 작업 시작)"""
    job_id = f"execution_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    
    jobs[job_id] = {
        "job_id": job_id,
        "status": "running",
        "result": None
    }
    
    # 백그라운드에서 크롤링 시작
    background_tasks.add_task(run_crawler_task, job_id)
    
    return {"job_id": job_id, "status": "running"}

@app.get("/v1/crawl-jobs/{job_id}")
async def get_crawl_job_status(job_id: str):
    """2. 작업 상태 조회 API"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "job_id": job_id,
        "status": jobs[job_id]["status"]
    }

@app.get("/v1/crawl-jobs/{job_id}/result")
async def get_crawl_job_result(job_id: str):
    """3. 완료 및 수집 결과 반환 API"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    if job["status"] != "completed":
        return {"message": "Job is still running or failed", "status": job["status"]}
        
    return {
        "job_id": job_id,
        "status": "completed",
        "result": job["result"]
    }

@app.get("/health")
async def health_check():
    """4. 서버 상태 확인 API"""
    return {"status": "ok"}