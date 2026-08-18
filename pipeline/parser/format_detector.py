from __future__ import annotations

import zipfile
from pathlib import Path


# HWP 5.x OLE/CFBF 파일 시그니처
OLE2_SIGNATURE = bytes.fromhex(
    "D0 CF 11 E0 A1 B1 1A E1"
)


def _looks_like_hwpx_zip(
    file_path: Path,
) -> bool:
    """
    ZIP 컨테이너가 실제 HWPX 구조인지 확인한다.

    단순히 ZIP 파일이라는 이유만으로 HWPX라고 판단하지 않고,
    HWPX에서 사용하는 Contents 영역과 mimetype 등을 확인한다.
    """

    if not zipfile.is_zipfile(file_path):
        return False

    try:
        with zipfile.ZipFile(
            file_path,
            "r",
        ) as archive:
            names = {
                name.replace("\\", "/").lower()
                for name in archive.namelist()
            }

            # HWPX 패키지에서 대표적으로 확인되는 파일
            if "contents/content.hpf" in names:
                return True

            # section0.xml, section1.xml 등의 본문 파일 확인
            if any(
                name.startswith("contents/section")
                and name.endswith(".xml")
                for name in names
            ):
                return True

            # mimetype이 존재하는 경우 추가 확인
            if "mimetype" in names:
                try:
                    mimetype = (
                        archive.read("mimetype")
                        .decode(
                            "utf-8",
                            errors="ignore",
                        )
                        .strip()
                        .lower()
                    )

                    if "hwp" in mimetype:
                        return True

                except KeyError:
                    pass

    except (
        OSError,
        zipfile.BadZipFile,
    ):
        return False

    return False


def detect_actual_document_format(
    file_path: Path,
) -> str:
    """
    확장자가 아니라 파일 내부 형식으로
    HWP/HWPX를 판별한다.

    반환값
    -------
    "hwp"
        HWP 5.x OLE/CFBF 형식

    "hwpx"
        ZIP/XML 기반 HWPX 형식

    "unknown"
        현재 HWP/HWPX parser로
        안전하게 판별할 수 없는 형식
    """

    file_path = Path(file_path)

    try:
        with file_path.open("rb") as file:
            header = file.read(8)

    except OSError:
        return "unknown"

    # HWP 5.x
    if header.startswith(OLE2_SIGNATURE):
        return "hwp"

    # HWPX
    if _looks_like_hwpx_zip(file_path):
        return "hwpx"

    return "unknown"