import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import time
import hashlib
import json
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from pathlib import Path  # 추가: Path 객체 사용

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
# 스케줄러 구동을 위한 라이브러리
from apscheduler.schedulers.blocking import BlockingScheduler

# 추가: 문서 실제 형식 판별 모듈 임포트
from pipeline.parser.format_detector import detect_actual_document_format


def calculate_sha256(file_path):
    """파일의 SHA-256 체크섬을 계산합니다."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def click_allow_popup(driver, timeout=1):
    """팝업창에서 허용/수락 버튼을 자동으로 클릭합니다."""
    button_texts = ["허용", "수락", "닫기", "Allow", "Accept"]
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
    """크롬 임시 다운로드 파일인지 확인합니다."""
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
        # 파일이 존재하고 임시 확장자가 제거되었다면 완료된 것으로 간주
        if os.path.exists(final_path) and not is_partial_download_file(final_name):
            return final_name
        time.sleep(0.5)
    return None

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

            # 메타데이터 추출
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
                    notice_number = cols[0].text.strip()
                    notice_type = cols[1].text.strip()
                    region = cols[3].text.strip()
                    post_date = cols[5].text.strip()
                    deadline_date = cols[6].text.strip()
                    publication_status = cols[7].text.strip()
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

                    # 다운로드 대상 필터링 (hwp, hwpx)
                    if file_ext in ["hwp", "hwpx"]:
                        before_files = set(os.listdir(temp_download_dir))
                        print(f"  -> 파일 다운로드 시도 [{j+1}/{file_count}]: {file_name}")
                        driver.execute_script("arguments[0].click();", file_link)
                        click_allow_popup(driver, timeout=2)

                        new_files = wait_for_download_start(temp_download_dir, before_files)

                        if new_files:
                            downloaded_temp_name = new_files[0]
                            
                            # 수정됨: 다운로드가 완료될 때까지 해당 스텝에서 대기 (pending_downloads 배열 제거)
                            if is_partial_download_file(downloaded_temp_name):
                                completed_name = wait_for_download_completion(temp_download_dir, downloaded_temp_name, timeout=60)
                                if completed_name:
                                    downloaded_name = completed_name
                                else:
                                    print(f"  -> 에러: 다운로드 완료 대기 시간 초과: {downloaded_temp_name}")
                                    notice_success = False
                                    continue
                            else:
                                downloaded_name = downloaded_temp_name

                            temp_file_path = os.path.join(temp_download_dir, downloaded_name)
                            target_file_path = os.path.join(notice_storage_dir, file_name)

                            if os.path.exists(temp_file_path):
                                time.sleep(0.5) # 파일 핸들 락(Lock) 해제를 위한 짧은 대기
                                os.replace(temp_file_path, target_file_path)

                                # 파일 사이즈 및 체크섬 계산
                                file_size = os.path.getsize(target_file_path)
                                checksum = calculate_sha256(target_file_path)
                                
                                # 추가됨: 다운로드된 실제 파일을 바탕으로 형식 판별
                                actual_format = detect_actual_document_format(Path(target_file_path))

                                document = {
                                    "file_name": file_name,
                                    "file_format": actual_format, # 수정됨: 판별된 실제 포맷 사용
                                    "storage_path": target_file_path,
                                    "file_size_bytes": file_size,
                                    "checksum_sha256": checksum,
                                    "download_status": "completed",
                                    "error_message": None
                                }
                                documents.append(document) # 정상적으로 append 됨
                            else:
                                print(f"  -> 에러: 임시 파일을 찾을 수 없습니다: {temp_file_path}")
                                notice_success = False
                        else:
                            notice_success = False

            except Exception as e:
                print(f"  -> 첨부파일 처리 중 에러 발생: {e}")

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
        # 수정됨: 루프 안에서 동기 처리하므로 지연된 다운로드 처리(finalize) 로직 삭제
        if os.path.exists(temp_download_dir):
            try:
                for f in os.listdir(temp_download_dir):
                    os.remove(os.path.join(temp_download_dir, f))
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
    result = crawl_lh_notices()
    print("\n================ [크롤링 최종 반환 데이터] ================")
    print(json.dumps(result, ensure_ascii=False, indent=2))