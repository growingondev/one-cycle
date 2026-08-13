from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable



PARSER_SCHEMA_VERSION = "1.1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "outputs"

JAR_ENV_VARS = {
    "hwp": "HWP_PARSER_JAR",
    "hwpx": "HWPX_PARSER_JAR",
}

JAR_DIRECTORIES = {
    "hwp": PROJECT_ROOT / "libs" / "hwp",
    "hwpx": PROJECT_ROOT / "libs" / "hwpx",
}

# 같은 형식의 구버전/신버전 JAR가 함께 있을 때 우선 사용할 JAR입니다.
# 파일이 존재하지 않으면 기존 규칙(폴더 내 단일 JAR)을 적용합니다.
PREFERRED_JAR_NAMES = {
    "hwp": "hwplib-1.1.10-custom.jar",
    "hwpx": None,
}


class ParserError(RuntimeError):
    """문서 파서 공통 예외입니다."""


class JarResolutionError(ParserError):
    """파서 JAR 경로를 결정하지 못했을 때 발생합니다."""


def configure_console_utf8() -> None:
    """Windows 콘솔에서도 한글 로그가 깨지지 않도록 설정합니다."""

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(
                encoding="utf-8",
                errors="replace",
            )


def _validate_jar(path: Path, parser_format: str) -> Path:
    path = path.expanduser().resolve()

    if not path.is_file():
        raise FileNotFoundError(
            f"{parser_format.upper()} 파서 JAR 파일을 찾을 수 없습니다: {path}"
        )

    if path.suffix.lower() != ".jar":
        raise JarResolutionError(
            f"JAR 파일이 아닙니다: {path}"
        )

    return path


def resolve_jar_path(
    parser_format: str,
    explicit_path: str | Path | None = None,
) -> Path:
    """
    파서 JAR 경로를 다음 순서로 결정합니다.

    1. 함수/CLI로 전달한 경로
    2. 환경변수(HWP_PARSER_JAR, HWPX_PARSER_JAR)
    3. 프로젝트 libs/<format> 폴더의 단일 JAR

    폴더에 JAR가 여러 개 있으면 임의 선택하지 않고 오류를 발생시킵니다.
    """

    parser_format = parser_format.lower().strip()

    if parser_format not in JAR_DIRECTORIES:
        raise ValueError(f"지원하지 않는 파서 형식입니다: {parser_format}")

    if explicit_path:
        return _validate_jar(Path(explicit_path), parser_format)

    env_var = JAR_ENV_VARS[parser_format]
    env_path = os.getenv(env_var, "").strip()

    if env_path:
        return _validate_jar(Path(env_path), parser_format)

    jar_dir = JAR_DIRECTORIES[parser_format]

    preferred_name = PREFERRED_JAR_NAMES.get(parser_format)
    if preferred_name:
        preferred_path = (jar_dir / preferred_name).resolve()
        if preferred_path.is_file():
            return preferred_path

    candidates = sorted(
        path.resolve()
        for path in jar_dir.glob("*.jar")
        if path.is_file()
    )

    if not candidates:
        raise JarResolutionError(
            f"{parser_format.upper()} 파서 JAR를 찾을 수 없습니다. "
            f"--{parser_format}_jar_path, {env_var}, 또는 {jar_dir}를 확인하세요."
        )

    if len(candidates) > 1:
        candidate_text = "\n".join(f"- {path}" for path in candidates)
        preferred_hint = (
            f"\n우선 JAR 파일명: {preferred_name}"
            if preferred_name
            else ""
        )
        raise JarResolutionError(
            f"{jar_dir}에 JAR 파일이 여러 개 있습니다. 사용할 파일을 명시하세요.\n"
            f"{candidate_text}"
            f"{preferred_hint}"
        )

    return candidates[0]


def discover_parser_jars() -> list[Path]:
    """형식별로 실제 사용할 HWP/HWPX JAR만 탐색합니다."""

    jars: list[Path] = []

    for parser_format in JAR_DIRECTORIES:
        try:
            jars.append(resolve_jar_path(parser_format))
        except JarResolutionError:
            # 해당 형식의 JAR가 없어도 다른 형식 파서는 실행할 수 있습니다.
            continue

    return sorted(set(jars))


def ensure_jvm(
    required_jars: Iterable[str | Path],
    *,
    required_classes: Iterable[str] = (),
) -> None:
    """
    JVM을 한 번만 시작합니다.

    처음 시작할 때 프로젝트에서 발견된 HWP/HWPX JAR를 함께 classpath에
    올려 동일 프로세스에서도 두 파서를 사용할 수 있게 합니다.
    """

    try:
        import jpype
    except ImportError as error:
        raise ParserError(
            "JPype가 설치되어 있지 않습니다. "
            "python -m pip install JPype1 명령으로 설치하세요."
        ) from error

    required_paths = {
        Path(path).expanduser().resolve()
        for path in required_jars
    }
    all_paths = required_paths | set(discover_parser_jars())

    missing = sorted(path for path in required_paths if not path.is_file())
    if missing:
        raise FileNotFoundError(
            "필수 JAR 파일을 찾을 수 없습니다:\n"
            + "\n".join(f"- {path}" for path in missing)
        )

    if not jpype.isJVMStarted():
        jpype.startJVM(
            jpype.getDefaultJVMPath(),
            classpath=[str(path) for path in sorted(all_paths)],
            convertStrings=True,
        )

    unavailable: list[str] = []
    for class_name in required_classes:
        try:
            jpype.JClass(class_name)
        except Exception:
            unavailable.append(class_name)

    if unavailable:
        raise ParserError(
            "JVM은 실행 중이지만 필요한 Java 클래스를 찾지 못했습니다. "
            "JVM 시작 전에 올바른 JAR가 classpath에 포함되어야 합니다:\n"
            + "\n".join(f"- {name}" for name in unavailable)
        )


def java_class_name(java_object: Any) -> str:
    """JPype Java 객체의 클래스 이름을 안전하게 반환합니다."""

    if java_object is None:
        return ""

    try:
        return str(java_object.getClass().getName())
    except Exception:
        return ""


def validate_document_path(
    file_path: str | Path,
    expected_suffix: str,
) -> Path:
    path = Path(file_path).expanduser().resolve()

    if not path.is_file():
        raise FileNotFoundError(f"문서 파일을 찾을 수 없습니다: {path}")

    if path.suffix.lower() != expected_suffix.lower():
        raise ValueError(
            f"예상 형식은 {expected_suffix}이지만 입력 파일은 {path.suffix}입니다: {path}"
        )

    if path.stat().st_size <= 0:
        raise ParserError(f"빈 문서 파일입니다: {path}")

    return path



def resolve_parser_output_path(
    input_file_path: str | Path,
    document_format: str,
    output_path: str | Path | None = None,
    output_root: str | Path | None = None,
) -> Path:
    """파싱 결과 JSON의 출력 경로를 결정합니다.

    output_path가 지정되면 해당 경로를 사용합니다.
    생략하면 입력 파일의 상위 폴더명을 유지하여 다음 형태로 생성합니다.

    test_documents/announcement_001/file.hwp
    -> outputs/announcement_001/01_parsed/hwp.json
    """

    if output_path is not None:
        return Path(output_path).expanduser().resolve()

    input_path = Path(input_file_path).expanduser().resolve()
    folder_name = input_path.parent.name
    normalized_format = document_format.lower().lstrip(".")

    if normalized_format not in {"hwp", "hwpx"}:
        raise ValueError(
            f"지원하지 않는 문서 형식입니다: {document_format}"
        )

    root = (
        Path(output_root).expanduser().resolve()
        if output_root is not None
        else DEFAULT_OUTPUT_ROOT
    )

    return (
        root
        / folder_name
        / "01_parsed"
        / f"{normalized_format}.json"
    )

def load_json(path: str | Path) -> dict[str, Any]:
    file_path = Path(path).expanduser().resolve()

    if not file_path.is_file():
        raise FileNotFoundError(f"JSON 파일을 찾을 수 없습니다: {file_path}")

    with file_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(f"JSON 최상위 값은 객체여야 합니다: {file_path}")

    return data


def save_json(data: dict[str, Any], path: str | Path) -> Path:
    file_path = Path(path).expanduser().resolve()
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )

    return file_path


def print_parse_summary(
    result: dict[str, Any],
    output_path: str | Path,
) -> None:
    """파싱 결과 요약을 HWP/HWPX 공통 형식으로 출력합니다."""

    document = result.get("document", {})
    parser_info = result.get("parser", {})
    statistics = result.get("statistics", {})
    warnings = result.get("warnings", [])

    document_format = str(
        document.get("format", "unknown")
    ).upper()
    resolved_output_path = Path(output_path).expanduser().resolve()

    print("=" * 80)
    print(f"{document_format} 파싱 완료")
    print("=" * 80)
    print(f"파일: {document.get('filename', '-')}")
    print(f"형식: {document.get('format', '-')}")
    print(f"엔진: {parser_info.get('engine', '-')}")
    print(f"Section 수: {statistics.get('section_count', 0)}")
    print(
        "표 바깥 일반 문단 수: "
        f"{statistics.get('top_level_paragraph_count', 0)}"
    )
    print(
        "최상위 표 수: "
        f"{statistics.get('top_level_table_count', 0)}"
    )
    print(
        "중첩 표 수: "
        f"{statistics.get('nested_table_count', 0)}"
    )
    print(f"이미지 수: {statistics.get('image_count', 0)}")
    print(f"경고 수: {len(warnings)}")
    print(f"출력: {resolved_output_path}")


@dataclass
class ParseContext:
    """한 문서의 파싱 상태와 통계를 관리합니다."""

    max_nested_depth: int = 10
    strict: bool = False
    next_table_index: int = 0
    top_level_paragraph_count: int = 0
    top_level_table_count: int = 0
    nested_table_count: int = 0
    cell_count: int = 0
    image_count: int = 0
    warnings: list[dict[str, Any]] = field(default_factory=list)
    _active_table_ids: set[int] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        if self.max_nested_depth < 0:
            raise ValueError("max_nested_depth는 0 이상이어야 합니다.")

    def allocate_table_index(self, location: str) -> int:
        table_index = self.next_table_index
        self.next_table_index += 1

        if location == "top_level":
            self.top_level_table_count += 1
        else:
            self.nested_table_count += 1

        return table_index

    def add_paragraph(self) -> None:
        """표 바깥에 존재하는 최상위 일반 문단을 1개 누적합니다."""
        self.top_level_paragraph_count += 1

    def add_cell(self) -> None:
        self.cell_count += 1

    def add_images(self, count: int = 1) -> None:
        """문서에서 발견한 포함 이미지 수를 누적합니다."""

        if count < 0:
            raise ValueError("이미지 수는 0 이상이어야 합니다.")
        self.image_count += count

    def warn(
        self,
        code: str,
        message: str,
        *,
        source: dict[str, Any] | None = None,
        error: Exception | None = None,
        fatal_in_strict: bool = False,
    ) -> None:
        warning: dict[str, Any] = {
            "code": code,
            "message": message,
        }

        if source:
            warning["source"] = source

        if error is not None:
            warning["error_type"] = type(error).__name__
            warning["error"] = str(error)

        self.warnings.append(warning)

        if self.strict and fatal_in_strict:
            raise ParserError(f"[{code}] {message}") from error

    def enter_table(self, table: Any, source: dict[str, Any]) -> bool:
        table_id = id(table)

        if table_id in self._active_table_ids:
            self.warn(
                "CIRCULAR_TABLE_REFERENCE",
                "순환 중첩 표 참조를 발견하여 재귀 처리를 중단했습니다.",
                source=source,
                fatal_in_strict=True,
            )
            return False

        self._active_table_ids.add(table_id)
        return True

    def exit_table(self, table: Any) -> None:
        self._active_table_ids.discard(id(table))

    def statistics(self, section_count: int) -> dict[str, int]:
        total_table_count = (
            self.top_level_table_count
            + self.nested_table_count
        )

        return {
            "section_count": section_count,
            "top_level_paragraph_count": self.top_level_paragraph_count,
            "paragraph_count_scope": "top_level_non_table",
            "top_level_table_count": self.top_level_table_count,
            "nested_table_count": self.nested_table_count,
            "total_table_count": total_table_count,
            # 기존 코드와의 호환용 필드
            "table_count": total_table_count,
            "cell_count": self.cell_count,
            "image_count": self.image_count,
            "warning_count": len(self.warnings),
        }


def build_document_header(
    file_path: Path,
    *,
    document_format: str,
    engine: str,
    jar_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": PARSER_SCHEMA_VERSION,
        "document": {
            "filename": file_path.name,
            "format": document_format,
            "file_size": file_path.stat().st_size,
        },
        "parser": {
            "engine": engine,
            "jar": jar_path.name,
        },
        "sections": [],
    }


configure_console_utf8()
