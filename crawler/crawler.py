import os
import time
import hashlib
import json
from datetime import datetime
from urllib.parse import urlparse, parse_qs

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
# 스케줄러 구동을 위한 라이브러리 (pip install apscheduler 필요)
from apscheduler.schedulers.blocking import BlockingScheduler

# 백엔드 파이프라인 연동 준비용
# import requests

def calculate_sha256(file_path):
    """파일의 SHA-256 체크섬을 계산합니다."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def backend_process_document(document):
    """백엔드 연동용 함수 (현재는 패스스루)"""
    return document

def click_allow_popup(driver, timeout=3):
    """팝업창에서 허용/수락 버튼을 자동으로 클릭합니다."""
    button_texts = ["허용", "수락", "Allow", "Accept"]
    try:
        alert = driver.switch_to.alert
        alert.accept()
        return True
    except Exception:
        pass

    for text in button_texts:
        xpath = (
            f"//button[contains(normalize-space(.), '{text}')]"
            f" | //a[contains(normalize-space(.), '{text}')]"
            f" | //input[@type='button' and contains(@value, '{text}')]"
            f" | //input[@type='submit' and contains(@value, '{text}')]"
        )
        try:
            popup_button = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            driver.execute_script("arguments[0].click();", popup_button)
            return True
        except Exception:
            continue
    return False

def is_partial_download_file(file_name):
    return file_name.endswith('.crdownload') or file_name.endswith('.tmp')

def wait_for_download_start(download_dir, before_files, timeout=15):
    """새로운 다운로드 파일이 생길 때까지 대기합니다."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        current_files = set(os.listdir(download_dir))
        new_files = current_files - before_files
        if new_files:
            return list(new_files)
        time.sleep(0.2)
    return []

def wait_for_download_completion(download_dir, temp_name, timeout=60):
    """임시 다운로드 파일이 최종 파일로 완료될 때까지 대기합니다."""
    if temp_name.endswith('.crdownload'):
        final_name = temp_name[:-10]
    elif temp_name.endswith('.tmp'):
        final_name = temp_name[:-4]
    else:
        final_name = temp_name

    final_path = os.path.join(download_dir, final_name)
    start_time = time.time()
    while time.time() - start_time < timeout:
        if os.path.exists(final_path) and not is_partial_download_file(final_name):
            return final_name
        time.sleep(0.5)
    return None

def finalize_pending_downloads(download_dir, pending_downloads):
    """진행 중인 다운로드가 완료되면 대상 폴더로 이동합니다."""
    for pending in pending_downloads:
        temp_name = pending["temp_name"]
        target_file_path = pending["target_file_path"]

        if not is_partial_download_file(temp_name):
            source_path = os.path.join(download_dir, temp_name)
            if os.path.exists(source_path):
                os.replace(source_path, target_file_path)
            continue

        completed_name = wait_for_download_completion(download_dir, temp_name, timeout=60)
        if completed_name:
            completed_path = os.path.join(download_dir, completed_name)
            os.replace(completed_path, target_file_path)
        else:
            print(f"  -> 경고: 다운로드가 완료되지 않았습니다: {temp_name}")

def crawl_lh_notices():
    execution_id = f"execution_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    base_staging_dir = os.path.abspath(r"C:\one-cycle\test_documents\lh_downloads")
    execution_staging_dir = os.path.join(base_staging_dir, execution_id)
    temp_download_dir = os.path.join(execution_staging_dir, "_temp_download")

    os.makedirs(temp_download_dir, exist_ok=True)

    chrome_options = Options()
    prefs = {
        "download.default_directory": temp_download_dir,
        "download.prompt_for_download": False,
        "safebrowsing.enabled": True,
        "profile.default_content_setting_values.automatic_downloads": 1,
        "profile.default_content_setting_values.notifications": 2,
    }
    chrome_options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    all_notice_results = []
    success_count = 0
    failed_count = 0
    total_count = 0
    pending_downloads = []

    try:
        print(f"[{execution_id}] LH 청약플러스 접속 중...")
        driver.get("https://apply.lh.or.kr/")

        click_allow_popup(driver)
        try:
            popup_close_btn = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#gnrlPopTodayClose"))
            )
            popup_close_btn.click()
        except Exception:
            pass

        # 메뉴 이동 ('청약' -> '임대주택' -> '모집공고')
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '.apply a'))
        ).click()
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a[data-target='#sbrlink1']"))
        ).click()
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn .col1"))
        ).click()

        notices = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".mVw.bbs_tit a.wrtancInfoBtn"))
        )
        total_count = len(notices)
        print(f"\n총 {total_count}개의 공고문을 수집합니다.")

        for i in range(total_count):
            notices = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".mVw.bbs_tit a.wrtancInfoBtn"))
            )
            notice_elem = notices[i]
            title = notice_elem.text.strip()

            # --- 테이블 컬럼 데이터 추출 (image_f0757b.png 기준) ---
            notice_number = ""
            notice_type = ""
            region = "미상"
            post_date = ""
            deadline_date = ""
            publication_status = "상태없음"

            try:
                parent_tr = notice_elem.find_element(By.XPATH, "./ancestor::tr")
                cols = parent_tr.find_elements(By.TAG_NAME, "td")
                
                if len(cols) >= 8:
                    notice_number = cols[0].text.strip()         # 번호
                    notice_type = cols[1].text.strip()           # 유형
                    # cols[2]는 공고명 (title 변수로 획득 완료)
                    region = cols[3].text.strip()                # 지역
                    # cols[4]는 첨부파일 아이콘 영역
                    post_date = cols[5].text.strip()             # 게시일
                    deadline_date = cols[6].text.strip()         # 마감일
                    publication_status = cols[7].text.strip()    # 상태
            except Exception as e:
                print(f"  -> 메타데이터 추출 실패: {e}")

            print(f"\n[{i+1}/{total_count}] 공고 진입: [{notice_type}] {title}")

            # 상세 페이지 진입
            notice_elem.click()
            time.sleep(1)

            detail_url = driver.current_url
            parsed_url = urlparse(detail_url)
            query_params = parse_qs(parsed_url.query)
            source_announcement_id = query_params.get("panId", [None])[0] or \
                                     query_params.get("wrtancNo", [None])[0] or \
                                     f"LH_{hashlib.md5(detail_url.encode()).hexdigest()[:10]}"

            notice_storage_dir = os.path.join(execution_staging_dir, source_announcement_id)
            os.makedirs(notice_storage_dir, exist_ok=True)

            documents = []
            notice_success = True

            try:
                attachments = WebDriverWait(driver, 5).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".bbsV_link.file a"))
                )
                file_count = len(attachments)
                
                for j in range(file_count):
                    current_attachments = driver.find_elements(By.CSS_SELECTOR, ".bbsV_link.file a")
                    file_link = current_attachments[j]
                    file_name = file_link.text.strip()
                    file_ext = os.path.splitext(file_name)[1].lower().replace('.', '')

                    if file_ext in ["hwp", "hwpx"]:
                        before_files = set(os.listdir(temp_download_dir))
                        print(f"  -> 파일 다운로드 시도 [{j+1}/{file_count}]: {file_name}")
                        driver.execute_script("arguments[0].click();", file_link)
                        click_allow_popup(driver, timeout=2)

                        new_files = wait_for_download_start(temp_download_dir, before_files)

                        if new_files:
                            downloaded_temp_name = new_files[0]
                            temp_file_path = os.path.join(temp_download_dir, downloaded_temp_name)
                            target_file_path = os.path.join(notice_storage_dir, file_name)

                            if is_partial_download_file(downloaded_temp_name):
                                pending_downloads.append({
                                    "temp_name": downloaded_temp_name,
                                    "target_file_path": target_file_path,
                                })
                                time.sleep(1)
                            else:
                                time.sleep(0.5)
                                os.rename(temp_file_path, target_file_path)
                                file_size = os.path.getsize(target_file_path)
                                checksum = calculate_sha256(target_file_path)

                                document = {
                                    "file_name": file_name,
                                    "file_format": file_ext,
                                    "storage_path": target_file_path,
                                    "file_size_bytes": file_size,
                                    "checksum_sha256": checksum,
                                    "download_status": "completed",
                                    "error_message": None
                                }
                                documents.append(document)
                        else:
                            notice_success = False

            except Exception as e:
                print(f"  -> 첨부파일 처리 중 에러 발생: {e}")

            # 새롭게 추출한 데이터 필드들을 JSON 객체에 매핑
            all_notice_results.append({
                "source_announcement_id": source_announcement_id,
                "notice_number": notice_number,
                "notice_type": notice_type,
                "title": title,
                "region": region,
                "post_date": post_date,
                "deadline_date": deadline_date,
                "publication_status": publication_status,
                "detail_url": detail_url,
                "documents": documents
            })

            if notice_success:
                success_count += 1
            else:
                failed_count += 1

            driver.back()
            time.sleep(1)

    except Exception as e:
        print(f"크롤링 중 오류 발생: {e}")

    finally:
        driver.quit()
        if pending_downloads:
            finalize_pending_downloads(temp_download_dir, pending_downloads)
        if os.path.exists(temp_download_dir):
            try:
                os.rmdir(temp_download_dir)
            except Exception:
                pass

    overall_status = "success" if failed_count == 0 and success_count > 0 else "partial" if success_count > 0 else "failed"

    return {
        "execution_id": execution_id,
        "execution_status": overall_status,
        "total_count": total_count,
        "success_count": success_count,
        "failed_count": failed_count,
        "data": all_notice_results
    }


if __name__ == "__main__":
    # ----------------------------------------------------
    # 단일 실행 (테스트용)
    # ----------------------------------------------------
    result = crawl_lh_notices()
    print("\n================ [크롤링 최종 반환 데이터] ================")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # ----------------------------------------------------
    # 매일 새벽 2시 자동 실행 스케줄러 (APScheduler)
    # ----------------------------------------------------
    # scheduler = BlockingScheduler()
    # scheduler.add_job(crawl_lh_notices, 'cron', hour=2, minute=0)
    # print("스케줄러가 시작되었습니다. 매일 새벽 2시에 크롤링이 실행됩니다.")
    # scheduler.start()