"""Only handle files created by the current recollection; never delete legacy files."""

import hashlib
import re
from pathlib import Path

from backend.app.core.config import settings


def file_matches(path: Path, checksum: str) -> bool:
    if not path.is_file():
        return False
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest() == checksum


def validated_recollection_file(
    *,
    storage_path: str,
    execution_id: str,
    source_id: str,
    file_name: str,
    checksum: str,
) -> Path:
    """Require the current execution/source/file and verify its bytes before reuse."""
    if not re.fullmatch(r"recollect_[A-Za-z0-9_-]+", execution_id):
        raise ValueError("재수집 execution_id가 안전한 실행 폴더 이름이 아닙니다.")
    if not file_name or re.search(r"[\\/]", file_name) or file_name in {".", ".."}:
        raise ValueError("재수집 파일명이 유효하지 않습니다.")
    source_id = str(source_id).strip()
    component = re.sub(r"[^0-9A-Za-z._-]+", "_", source_id).strip("._")
    if not component or component != source_id:
        component = "notice_" + hashlib.sha256(source_id.encode("utf-8")).hexdigest()
    root = Path(settings.crawler_staging_dir).expanduser().resolve()
    expected = root / execution_id / component / file_name
    raw = Path(storage_path)
    candidate = raw.resolve()
    # Comparing to the lexical expected path also rejects symlinked ancestors.
    if raw.is_symlink() or candidate != expected or not candidate.is_relative_to(root):
        raise ValueError("현재 재수집 실행 폴더 외부의 파일은 변경할 수 없습니다.")
    if not file_matches(candidate, checksum):
        raise ValueError("재수집 파일이 없거나 체크섬이 일치하지 않습니다.")
    return candidate
