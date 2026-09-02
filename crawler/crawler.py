import hashlib
import json
import os
import shutil
import sys
import time

from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


# 프로젝트 루트를 import 경로에 추가
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))


# ==========================================
# 문서 실제 형식 판별
# ==========================================

try:
    from pipeline.parser.format_detector import (
        detect_actual_document_format,
    )
except ImportError:
    def detect_actual_document_format(path: Path) -> str:
        """
        format_detector를 불러올 수 없는 환경에서의 fallback.
        실제 운영에서는 pipeline.parser.format_detector 사용을 권장한다.
        """
        return path.suffix.lower().replace(".", "")


# ==========================================
# 공통 경로
# ==========================================

def get_crawler_staging_dir() -> Path:
    """
    Crawler 다운로드 결과 저장 루트.

    우선순위:
    1. CRAWLER_STAGING_DIR 환경변수
    2. 프로젝트/test_documents/lh_downloads
    """
    configured = os.getenv(
        "CRAWLER_STAGING_DIR",
        "",
    ).strip()

    if configured:
        return Path(configured).expanduser().resolve()

    return (
        PROJECT_ROOT
        / "test_documents"
        / "lh_downloads"
    ).resolve()


# ==========================================
# 유틸리티
# ==========================================

def calculate_sha256(file_path: str | Path) -> str:
    """파일의 SHA-256 체크섬을 계산한다."""
    sha256_hash = hashlib.sha256()

    with open(file_path, "rb") as file:
        for byte_block in iter(
            lambda: file.read(4096),
            b"",
        ):
            sha256_hash.update(byte_block)

    return sha256_hash.hexdigest()


def click_allow_popup(
    driver,
    timeout: float = 1,
) -> bool:
    """팝업의 허용/수락/닫기 버튼을 처리한다."""
    button_texts = [
        "허용",
        "수락",
        "닫기",
        "Allow",
        "Accept",
    ]

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
            popup_button = WebDriverWait(
                driver,
                timeout,
            ).until(
                EC.element_to_be_clickable(
                    (By.XPATH, xpath)
                )
            )

            driver.execute_script(
                "arguments[0].click();",
                popup_button,
            )

            return True

        except Exception:
            continue

    return False


def close_main_popup(driver) -> None:
    """LH 메인 페이지 팝업을 닫는다."""
    selectors = (
        "#gnrlPopTodayClose, "
        ".btn_today_close, "
        ".pop_close"
    )

    try:
        popup_close_btn = WebDriverWait(
            driver,
            2,
        ).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, selectors)
            )
        )

        driver.execute_script(
            "arguments[0].click();",
            popup_close_btn,
        )

    except Exception:
        pass


def is_partial_download_file(
    file_name: str,
) -> bool:
    """Chrome 임시 다운로드 파일인지 확인한다."""
    return (
        file_name.endswith(".crdownload")
        or file_name.endswith(".tmp")
    )


def wait_for_download_start(
    download_dir: str | Path,
    before_files: set[str],
    timeout: int = 15,
) -> list[str]:
    """새로운 다운로드 파일이 생성될 때까지 기다린다."""
    download_dir = Path(download_dir)

    start_time = time.time()

    while time.time() - start_time < timeout:
        current_files = {
            path.name
            for path in download_dir.iterdir()
            if path.is_file()
        }

        new_files = current_files - before_files

        if new_files:
            return sorted(new_files)

        time.sleep(0.2)

    return []


def wait_for_download_completion(
    download_dir: str | Path,
    temp_name: str,
    timeout: int = 60,
) -> str | None:
    """임시 다운로드 파일이 최종 파일로 변경될 때까지 기다린다."""
    download_dir = Path(download_dir)

    if temp_name.endswith(".crdownload"):
        final_name = temp_name.removesuffix(
            ".crdownload"
        )

    elif temp_name.endswith(".tmp"):
        final_name = temp_name.removesuffix(
            ".tmp"
        )

    else:
        final_name = temp_name

    final_path = download_dir / final_name

    start_time = time.time()

    while time.time() - start_time < timeout:
        if (
            final_path.exists()
            and final_path.is_file()
            and not is_partial_download_file(
                final_path.name
            )
        ):
            return final_name

        time.sleep(0.5)

    return None

def create_driver(temp_download_dir: str | Path):
    """다운로드 경로를 지정한 Chrome Driver를 생성한다."""
    temp_download_dir = str(Path(temp_download_dir).resolve())

    chrome_options = Options()

    # 화면이 없는 Linux/AWS 환경에서는 headless Chrome을 사용한다.
    is_headless_linux = (
        sys.platform.startswith("linux")
        and not os.getenv("DISPLAY")
    )

    if is_headless_linux:
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

    prefs = {
        "download.default_directory": temp_download_dir,
        "download.prompt_for_download": False,
        "safebrowsing.enabled": True,
        "profile.default_content_setting_values.automatic_downloads": 1,
        "profile.default_content_setting_values.notifications": 2,
    }

    chrome_options.add_experimental_option("prefs", prefs)

    # service = Service(ChromeDriverManager().install())

    return webdriver.Chrome(options=chrome_options)

def cleanup_temp_directory(
    temp_download_dir: str | Path,
) -> None:
    """임시 다운로드 디렉터리를 정리한다."""
    path = Path(temp_download_dir)

    if path.exists():
        shutil.rmtree(
            path,
            ignore_errors=True,
        )


# ==========================================
# Error 구조
# ==========================================

def build_error(
    *,
    error_type: str,
    stage: str,
    error_code: str,
    message: str,
    source_announcement_id: str | None = None,
    file_name: str | None = None,
) -> dict:
    """
    Backend ErrorLog 연결용 공통 오류 구조.

    error_type:
        collection / download 등 Backend의 큰 오류 분류

    stage:
        실제 실패 단계

    error_code:
        구체적인 오류 식별 코드
    """
    return {
        "error_type": error_type,
        "stage": stage,
        "error_code": error_code,
        "message": message,
        "source_announcement_id":
            source_announcement_id,
        "file_name": file_name,
    }


# ==========================================
# 상세 공고 처리
# ==========================================

def _process_single_notice(
    driver,
    temp_download_dir: str | Path,
    execution_staging_dir: str | Path,
    meta_override: dict | None = None,
    source_announcement_id_override:
        str | None = None,
    detail_url_override:
        str | None = None,
) -> dict:
    """
    현재 상세 페이지의 첨부파일을 처리한다.

    전체 수집:
        현재 URL에서 source_announcement_id를 추출한다.

    개별 재수집:
        Backend가 전달한 source_announcement_id와
        detail_url을 그대로 기준값으로 사용한다.
    """
    temp_download_dir = Path(
        temp_download_dir
    )

    execution_staging_dir = Path(
        execution_staging_dir
    )

    current_detail_url = driver.current_url

    detail_url = (
        detail_url_override
        or current_detail_url
    )

    parsed_url = urlparse(
        current_detail_url
    )

    query_params = parse_qs(
        parsed_url.query
    )

    source_announcement_id = (
        source_announcement_id_override
        or query_params.get(
            "panId",
            [None],
        )[0]
        or query_params.get(
            "wrtancNo",
            [None],
        )[0]
        or (
            "LH_"
            + hashlib.md5(
                current_detail_url.encode()
            ).hexdigest()[:10]
        )
    )

    notice_storage_dir = (
        execution_staging_dir
        / source_announcement_id
    )

    notice_storage_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    documents: list[dict] = []
    errors: list[dict] = []

    notice_success = True

    try:
        attachments = WebDriverWait(
            driver,
            5,
        ).until(
            EC.presence_of_all_elements_located(
                (
                    By.CSS_SELECTOR,
                    ".bbsV_link.file a",
                )
            )
        )

        file_count = len(attachments)

        for index in range(file_count):
            current_attachments = (
                driver.find_elements(
                    By.CSS_SELECTOR,
                    ".bbsV_link.file a",
                )
            )

            file_link = current_attachments[
                index
            ]

            file_name = (
                file_link.text.strip()
            )

            file_ext = (
                Path(file_name)
                .suffix
                .lower()
                .replace(".", "")
            )

            # 파일명 확장자는 다운로드 후보를 정하기 위한 값이다.
            # 저장 여부는 다운로드 후 actual_format으로 다시 판단한다.
            if file_ext not in {
                "hwp",
                "hwpx",
            }:
                continue

            before_files = {
                path.name
                for path in temp_download_dir.iterdir()
                if path.is_file()
            }

            print(
                "  -> 파일 다운로드 시도 "
                f"[{index + 1}/{file_count}]: "
                f"{file_name}"
            )

            driver.execute_script(
                "arguments[0].click();",
                file_link,
            )

            click_allow_popup(
                driver,
                timeout=2,
            )

            new_files = wait_for_download_start(
                temp_download_dir,
                before_files,
            )

            if not new_files:
                err_msg = (
                    "다운로드 시작 대기 실패: "
                    f"{file_name}"
                )

                print(
                    f"  -> 에러: {err_msg}"
                )

                errors.append(
                    build_error(
                        error_type="download",
                        stage="download",
                        error_code=(
                            "DOWNLOAD_START_FAILED"
                        ),
                        message=err_msg,
                        source_announcement_id=(
                            source_announcement_id
                        ),
                        file_name=file_name,
                    )
                )

                notice_success = False
                continue

            downloaded_temp_name = (
                new_files[0]
            )

            if is_partial_download_file(
                downloaded_temp_name
            ):
                completed_name = (
                    wait_for_download_completion(
                        temp_download_dir,
                        downloaded_temp_name,
                        timeout=60,
                    )
                )

                if completed_name is None:
                    err_msg = (
                        "다운로드 완료 대기 시간 "
                        "초과: "
                        f"{downloaded_temp_name}"
                    )

                    print(
                        f"  -> 에러: {err_msg}"
                    )

                    errors.append(
                        build_error(
                            error_type="download",
                            stage="download",
                            error_code=(
                                "DOWNLOAD_TIMEOUT"
                            ),
                            message=err_msg,
                            source_announcement_id=(
                                source_announcement_id
                            ),
                            file_name=file_name,
                        )
                    )

                    notice_success = False
                    continue

                downloaded_name = (
                    completed_name
                )

            else:
                downloaded_name = (
                    downloaded_temp_name
                )

            temp_file_path = (
                temp_download_dir
                / downloaded_name
            )

            target_file_path = (
                notice_storage_dir
                / file_name
            )

            if not temp_file_path.exists():
                err_msg = (
                    "임시 파일을 찾을 수 "
                    "없습니다: "
                    f"{temp_file_path}"
                )

                print(
                    f"  -> 에러: {err_msg}"
                )

                errors.append(
                    build_error(
                        error_type="download",
                        stage="download",
                        error_code="FILE_NOT_FOUND",
                        message=err_msg,
                        source_announcement_id=(
                            source_announcement_id
                        ),
                        file_name=file_name,
                    )
                )

                notice_success = False
                continue

            # Chrome 파일 핸들 해제 대기
            time.sleep(0.5)

            os.replace(
                temp_file_path,
                target_file_path,
            )

            file_size = (
                target_file_path.stat().st_size
            )

            checksum = calculate_sha256(
                target_file_path
            )

            actual_format = (
                detect_actual_document_format(
                    target_file_path
                )
            )

            documents.append(
                {
                    "file_name": file_name,
                    "file_format":
                        actual_format,
                    "storage_path":
                        str(target_file_path),
                    "file_size_bytes":
                        file_size,
                    "checksum_sha256":
                        checksum,
                    "download_status":
                        "completed",
                    "error_message":
                        None,
                }
            )

    except Exception as exc:
        err_msg = (
            "첨부파일 처리 중 에러 발생: "
            f"{exc}"
        )

        print(
            f"  -> {err_msg}"
        )

        errors.append(
            build_error(
                error_type="download",
                stage="attachment",
                error_code=(
                    "ATTACHMENT_PROCESS_ERROR"
                ),
                message=err_msg,
                source_announcement_id=(
                    source_announcement_id
                ),
            )
        )

        notice_success = False

    result = {
        "source_announcement_id":
            source_announcement_id,
        "detail_url":
            detail_url,
        "documents":
            documents,
        "errors":
            errors,
        "is_success":
            notice_success,
    }

    if meta_override:
        result.update(
            meta_override
        )

    return result


# ==========================================
# 전체 공고 수집
# ==========================================

def crawl_lh_notices() -> dict:
    """전체 LH 공고 목록을 순회 수집한다."""
    execution_id = (
        "execution_"
        + datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    base_staging_dir = (
        get_crawler_staging_dir()
    )

    execution_staging_dir = (
        base_staging_dir
        / execution_id
    )

    temp_download_dir = (
        execution_staging_dir
        / "_temp_download"
    )

    temp_download_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    driver = None

    all_notice_results: list[dict] = []
    all_errors: list[dict] = []

    success_count = 0
    failed_count = 0
    total_count = 0

    fatal_error = None

    try:
        driver = create_driver(
            temp_download_dir
        )

        print(
            f"[{execution_id}] "
            "LH 청약플러스 접속 중..."
        )

        driver.get(
            "https://apply.lh.or.kr/"
        )

        close_main_popup(driver)

        click_allow_popup(
            driver,
            timeout=0.5,
        )

        # 청약 → 임대주택 → 모집공고
        WebDriverWait(
            driver,
            10,
        ).until(
            EC.element_to_be_clickable(
                (
                    By.CSS_SELECTOR,
                    ".apply a",
                )
            )
        ).click()

        WebDriverWait(
            driver,
            10,
        ).until(
            EC.element_to_be_clickable(
                (
                    By.CSS_SELECTOR,
                    "a[data-target='#sbrlink1']",
                )
            )
        ).click()

        WebDriverWait(
            driver,
            10,
        ).until(
            EC.element_to_be_clickable(
                (
                    By.CSS_SELECTOR,
                    ".btn .col1",
                )
            )
        ).click()

        notices = WebDriverWait(
            driver,
            10,
        ).until(
            EC.presence_of_all_elements_located(
                (
                    By.CSS_SELECTOR,
                    ".mVw.bbs_tit "
                    "a.wrtancInfoBtn",
                )
            )
        )

        total_count = len(
            notices
        )

        print(
            f"\n총 {total_count}개의 "
            "공고문을 수집합니다."
        )

        for index in range(total_count):
            notices = WebDriverWait(
                driver,
                10,
            ).until(
                EC.visibility_of_all_elements_located(
                    (
                        By.CSS_SELECTOR,
                        ".mVw.bbs_tit "
                        "a.wrtancInfoBtn",
                    )
                )
            )

            notice_elem = notices[index]

            title = (
                notice_elem.text.strip()
            )

            source_announcement_id = (
                notice_elem.get_attribute("data-id1") or ""
            ).strip()

            ccr_cnnt_sys_ds_cd = (
                notice_elem.get_attribute("data-id2") or ""
            ).strip()

            upp_ais_tp_cd = (
                notice_elem.get_attribute("data-id3") or ""
            ).strip()

            ais_tp_cd = (
                notice_elem.get_attribute("data-id4") or ""
            ).strip()

            detail_url = (
                "https://apply.lh.or.kr/"
                "lhapply/apply/wt/wrtanc/selectWrtancInfo.do"
                f"?aisTpCd={ais_tp_cd}"
                f"&ccrCnntSysDsCd={ccr_cnnt_sys_ds_cd}"
                f"&panId={source_announcement_id}"
                f"&uppAisTpCd={upp_ais_tp_cd}"
            )

            meta = {
                "notice_number": "",
                "notice_type": "",
                "title": title,
                "region": "미상",
                "post_date": "",
                "deadline_date": "",
                "publication_status":
                    "상태없음",
            }

            try:
                parent_tr = (
                    notice_elem.find_element(
                        By.XPATH,
                        "./ancestor::tr",
                    )
                )

                cols = (
                    parent_tr.find_elements(
                        By.TAG_NAME,
                        "td",
                    )
                )

                if len(cols) >= 8:
                    meta[
                        "notice_number"
                    ] = cols[0].text.strip()

                    meta[
                        "notice_type"
                    ] = cols[1].text.strip()

                    meta[
                        "region"
                    ] = cols[3].text.strip()

                    meta[
                        "post_date"
                    ] = cols[5].text.strip()

                    meta[
                        "deadline_date"
                    ] = cols[6].text.strip()

                    meta[
                        "publication_status"
                    ] = cols[7].text.strip()

            except Exception as exc:
                print(
                    "  -> 메타데이터 "
                    f"추출 실패: {exc}"
                )

            print(
                f"\n[{index + 1}/"
                f"{total_count}] "
                "공고 진입: "
                f"[{meta['notice_type']}] "
                f"{title}"
            )

            notice_elem.click()

            time.sleep(1)

            notice_result = (
                _process_single_notice(
                    driver,
                    temp_download_dir,
                    execution_staging_dir,
                    meta_override=meta,
                    source_announcement_id_override=(
                        source_announcement_id
                    ),
                    detail_url_override=detail_url,
                )
            )

            # 내부 처리 상태는 최상위 수집 결과로 이동한다.
            notice_errors = (
                notice_result.pop(
                    "errors",
                    [],
                )
            )

            all_errors.extend(
                notice_errors
            )

            is_success = (
                notice_result.pop(
                    "is_success",
                    True,
                )
            )

            if is_success:
                success_count += 1
            else:
                failed_count += 1

            all_notice_results.append(
                notice_result
            )

            driver.back()


    except Exception as exc:
        fatal_error = (
            "크롤링 중 치명적 오류 발생: "
            f"{exc}"
        )

        print(
            fatal_error
        )

        all_errors.append(
            build_error(
                error_type="collection",
                stage="collection",
                error_code=(
                    "CRAWL_FATAL_ERROR"
                ),
                message=fatal_error,
            )
        )

    finally:
        if driver is not None:
            driver.quit()

        cleanup_temp_directory(
            temp_download_dir
        )

    if success_count > 0:
        overall_status = (
            "success"
            if failed_count == 0
            and fatal_error is None
            else "partial"
        )
    else:
        overall_status = "failed"

    return {
        "execution_id":
            execution_id,
        "execution_status":
            overall_status,
        "total_count":
            total_count,
        "success_count":
            success_count,
        "failed_count":
            failed_count,
        "fatal_error":
            fatal_error,
        "data":
            all_notice_results,
        "errors":
            all_errors,
    }


# ==========================================
# 개별 공고 재수집
# ==========================================

def recollect_lh_notice(
    source_announcement_id: str,
    detail_url: str,
) -> dict:
    """
    개별 공고 재수집 공식 callable.

    Backend가 DB에서 다음 값을 조회하여 전달한다.

    - source_announcement_id
    - detail_url

    Crawler는 DB Announcement.id를 알 필요가 없다.
    """
    execution_id = (
        f"recollect_"
        f"{source_announcement_id}_"
        + datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    base_staging_dir = (
        get_crawler_staging_dir()
    )

    execution_staging_dir = (
        base_staging_dir
        / execution_id
    )

    temp_download_dir = (
        execution_staging_dir
        / "_temp_download"
    )

    temp_download_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    driver = None

    errors: list[dict] = []
    data = None

    try:
        if not source_announcement_id:
            raise ValueError(
                "source_announcement_id가 "
                "전달되지 않았습니다."
            )

        if not detail_url:
            raise ValueError(
                "detail_url이 "
                "전달되지 않았습니다."
            )

        print(
            f"[{execution_id}] "
            "개별 공고 재수집 시작: "
            f"{detail_url}"
        )

        driver = create_driver(
            temp_download_dir
        )

        # Backend DB에 저장된 URL을 그대로 사용
        driver.get(
            detail_url
        )

        close_main_popup(driver)

        click_allow_popup(
            driver,
            timeout=0.5,
        )

        notice_result = (
            _process_single_notice(
                driver,
                temp_download_dir,
                execution_staging_dir,
                source_announcement_id_override=(
                    source_announcement_id
                ),
                detail_url_override=(
                    detail_url
                ),
            )
        )

        errors.extend(
            notice_result.get(
                "errors",
                [],
            )
        )

        is_success = (
            notice_result.get(
                "is_success",
                False,
            )
        )

        data = {
            "documents":
                notice_result.get(
                    "documents",
                    [],
                ),
        }

        return {
            "execution_id":
                execution_id,
            "status":
                (
                    "success"
                    if is_success
                    else "failed"
                ),
            "source_announcement_id":
                source_announcement_id,
            "detail_url":
                detail_url,
            "data":
                data,
            "errors":
                errors,
        }

    except Exception as exc:
        err_msg = (
            "개별 공고 재수집 중 "
            "에러 발생: "
            f"{exc}"
        )

        print(
            f"  -> {err_msg}"
        )

        errors.append(
            build_error(
                error_type="collection",
                stage="recollect",
                error_code="RECOLLECT_ERROR",
                message=err_msg,
                source_announcement_id=(
                    source_announcement_id
                ),
            )
        )

        return {
            "execution_id":
                execution_id,
            "status":
                "failed",
            "source_announcement_id":
                source_announcement_id,
            "detail_url":
                detail_url,
            "data":
                data,
            "errors":
                errors,
        }

    finally:
        if driver is not None:
            driver.quit()

        cleanup_temp_directory(
            temp_download_dir
        )


# ==========================================
# 직접 실행
# ==========================================

if __name__ == "__main__":
    result = crawl_lh_notices()

    print(
        "\n================ "
        "[크롤링 최종 반환 데이터] "
        "================"
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )