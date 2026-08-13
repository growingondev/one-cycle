from __future__ import annotations

import argparse
import inspect
import json
import os
import traceback
from typing import Any
from pathlib import Path
from tkinter import Tk, filedialog, messagebox

try:
    from .build_document_step1 import process as process_step1
    from .build_domain_step2 import process as process_step2
    from .build_table_step3 import process as process_step3
    from .finalize_structure import (
        finalize_step2_file,
        finalize_step3_file,
    )
    from .value_normalizer import process as process_value_normalizer
    from .verification import process as process_verification
except ImportError:
    from build_document_step1 import process as process_step1
    from build_domain_step2 import process as process_step2
    from build_table_step3 import process as process_step3
    from finalize_structure import (
        finalize_step2_file,
        finalize_step3_file,
    )
    from value_normalizer import process as process_value_normalizer
    from verification import process as process_verification


FINAL_FILENAMES = (
    "step1-1_items.json",
    "step1-2_heading_scheme.json",
    "step1-3_hierarchy.json",
    "step2-1_normalized_titles.json",
    "step2-2_domain_matches.json",
    "step2-3_domain_tagged.json",
    "step2-4_hierarchy_conflicts.json",
    "step2-5_domain_repaired.json",
    "step3-1_table_headers.json",
    "step3-2_table_mappings.json",
    "step3-3_structured_tables.json",
)


def _save_json(data: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    return output_path


def run_verification(
    input_path: Path,
    output_path: Path,
) -> Path:
    """verification.py의 process()를 실행하고 결과 경로를 반환합니다.

    process()의 출력 매개변수가 output_path 또는 report_path인 경우와,
    반환값이 Path/str/dict/tuple/None인 경우를 모두 처리합니다.
    """
    signature = inspect.signature(process_verification)
    parameters = signature.parameters

    kwargs: dict[str, Any] = {}
    if "input_path" in parameters:
        kwargs["input_path"] = input_path
    elif "input" in parameters:
        kwargs["input"] = input_path
    elif "source_path" in parameters:
        kwargs["source_path"] = input_path

    if "output_path" in parameters:
        kwargs["output_path"] = output_path
    elif "report_path" in parameters:
        kwargs["report_path"] = output_path
    elif "output" in parameters:
        kwargs["output"] = output_path
    elif "report" in parameters:
        kwargs["report"] = output_path

    if kwargs:
        result = process_verification(**kwargs)
    else:
        result = process_verification(input_path, output_path)

    if isinstance(result, dict):
        return _save_json(result, output_path)

    if isinstance(result, (str, Path)):
        result_path = Path(result).expanduser().resolve()
        if not result_path.is_file():
            raise FileNotFoundError(
                "Verification 결과 파일을 찾을 수 없습니다.\n"
                f"{result_path}"
            )
        return result_path

    if isinstance(result, tuple):
        for item in result:
            if isinstance(item, dict):
                return _save_json(item, output_path)
            if isinstance(item, (str, Path)):
                candidate = Path(item).expanduser().resolve()
                if candidate.is_file():
                    return candidate

    # process()가 None을 반환하고 전달받은 경로에 직접 저장하는 구현도 지원합니다.
    if output_path.is_file():
        return output_path

    raise RuntimeError(
        "verification.process()가 검증 결과 파일을 생성하지 않았습니다."
    )


def rename_output(
    source_path: str | Path,
    target_path: Path,
) -> Path:
    source = Path(source_path)

    if not source.exists():
        raise FileNotFoundError(
            "Structure 결과 파일을 찾을 수 없습니다.\n"
            f"{source}"
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)

    if source.resolve() != target_path.resolve():
        os.replace(source, target_path)

    return target_path


def run_structure_pipeline(
    input_path: Path,
    output_dir: Path,
    *,
    run_value_normalization: bool = True,
) -> dict[str, Path]:
    if not input_path.exists():
        raise FileNotFoundError(
            "정규화 JSON을 찾을 수 없습니다.\n"
            f"{input_path}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    print()
    print("=" * 72)
    print("Structure Pipeline 시작")
    print("=" * 72)
    print(f"입력: {input_path}")
    print(f"출력: {output_dir}")

    print()
    print("-" * 72)
    print("[Step 1] 문서 계층 구조화")
    print("-" * 72)

    step1_paths = process_step1(
        str(input_path),
        str(output_dir),
    )
    if len(step1_paths) != 3:
        raise RuntimeError(
            "Step 1 결과 파일 수가 예상과 다릅니다."
        )

    step1_final = Path(step1_paths[2])
    if not step1_final.exists():
        raise FileNotFoundError(
            "Step 1 최종 hierarchy 결과를 찾을 수 없습니다.\n"
            f"{step1_final}"
        )

    print()
    print("-" * 72)
    print("[Step 2] 도메인 태깅 및 계층 보정")
    print("-" * 72)

    step2_paths = process_step2(
        str(step1_final),
        str(output_dir),
    )
    if len(step2_paths) != 5:
        raise RuntimeError(
            "Step 2 결과 파일 수가 예상과 다릅니다."
        )

    step2_final = Path(step2_paths[4])
    if not step2_final.exists():
        raise FileNotFoundError(
            "Step 2 최종 domain repaired 결과를 찾을 수 없습니다.\n"
            f"{step2_final}"
        )

    step2_document = finalize_step2_file(step2_final)
    postprocess_info = (
        step2_document
        .get("domain_tagging_method", {})
        .get("postprocessing", {})
    )
    print(
        "[Step 2 보완] 접근성 도메인 보완:",
        postprocess_info.get("resolved_count", 0),
        "건",
    )

    print()
    print("-" * 72)
    print("[Step 3] 표 세부 구조화")
    print("-" * 72)

    step3_paths = process_step3(
        str(step2_final),
        str(output_dir),
    )
    if len(step3_paths) != 3:
        raise RuntimeError(
            "Step 3 결과 파일 수가 예상과 다릅니다."
        )

    step3_final = Path(step3_paths[2])
    if not step3_final.exists():
        raise FileNotFoundError(
            "Step 3 최종 structured tables 결과를 찾을 수 없습니다.\n"
            f"{step3_final}"
        )

    step3_document = finalize_step3_file(step3_final)
    table_postprocess_info = (
        step3_document
        .get("table_structuring_method", {})
        .get("postprocessing", {})
    )
    print(
        "[Step 3 보완] 추가 구조화 표:",
        table_postprocess_info.get("resolved_table_count", 0),
        "개",
    )
    print(
        "[Step 3 보완] 표 인덱스:",
        table_postprocess_info.get("resolved_table_indexes", []),
    )

    generated_paths = [
        *step1_paths,
        *step2_paths,
        *step3_paths,
    ]

    if len(generated_paths) != len(FINAL_FILENAMES):
        raise RuntimeError(
            "전체 Structure 결과 파일 수가 예상과 일치하지 않습니다."
        )

    final_paths: dict[str, Path] = {}

    for source_path, final_filename in zip(
        generated_paths,
        FINAL_FILENAMES,
    ):
        target_path = output_dir / final_filename
        final_paths[final_filename] = rename_output(
            source_path,
            target_path,
        )

    if run_value_normalization:
        print()
        print("-" * 72)
        print("[Step 4] 값 타입 정규화 및 추가 검증")
        print("-" * 72)

        structured_final = final_paths["step3-3_structured_tables.json"]
        value_output, validation_report = process_value_normalizer(
            input_path=structured_final,
            output_path=output_dir / "step4-1_value_normalized.json",
            report_path=output_dir / "step4-2_value_validation.json",
        )

        final_paths["step4-1_value_normalized.json"] = value_output
        final_paths["step4-2_value_validation.json"] = validation_report

        print("[Step 4 완료] 값 정규화 결과:")
        print(f"  → {value_output}")
        print("[Step 4 완료] 값 정규화 검증 보고서:")
        print(f"  → {validation_report}")

        print()
        print("-" * 72)
        print("[Step 4-3] 최종 Structure 검증")
        print("-" * 72)

        verification_output = run_verification(
            input_path=value_output,
            output_path=output_dir / "step4-3_verification.json",
        )
        final_paths["step4-3_verification.json"] = verification_output

        print("[Step 4-3 완료] 최종 검증 보고서:")
        print(f"  → {verification_output}")

    print()
    print("=" * 72)
    print("Document Structure Pipeline 완료")
    print("=" * 72)

    for filename, path in final_paths.items():
        print(filename)
        print(f"  → {path}")

    print("=" * 72)

    return final_paths


def _select_input_file() -> Path | None:
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askopenfilename(
            parent=root,
            title="정규화 HWP/HWPX JSON 선택",
            filetypes=[
                ("정규화 JSON", "*.json"),
                ("모든 파일", "*.*"),
            ],
        )
        return Path(selected).resolve() if selected else None
    finally:
        root.destroy()


def _select_output_directory(initial: Path | None = None) -> Path | None:
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(
            parent=root,
            title="Structure 결과 저장 폴더 선택",
            initialdir=str(initial) if initial else None,
        )
        return Path(selected).resolve() if selected else None
    finally:
        root.destroy()


def _default_output_dir(input_path: Path) -> Path:
    # outputs/<document_id>/02_normalized/hwp.json
    # -> outputs/<document_id>/03_structured/hwp
    parent = input_path.parent
    if parent.name == "02_normalized":
        return parent.parent / "03_structured" / input_path.stem
    return parent / "03_structured" / input_path.stem


def _validate_normalized_json(input_path: Path) -> None:
    if not input_path.is_file():
        raise FileNotFoundError(f"입력 JSON을 찾을 수 없습니다: {input_path}")

    try:
        with input_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"유효하지 않은 JSON입니다: {input_path} "
            f"(line={error.lineno}, column={error.colno})"
        ) from error

    if not isinstance(data, dict):
        raise ValueError("입력 JSON 최상위 값은 객체여야 합니다.")
    if not isinstance(data.get("sections"), list):
        raise ValueError("정규화 JSON의 sections 배열을 찾을 수 없습니다.")

    stage = str(data.get("stage") or "").strip().lower()
    if stage and stage != "normalized":
        raise ValueError(
            "Structure 입력은 정규화 JSON이어야 합니다. "
            f"현재 stage={stage!r}"
        )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "정규화된 HWP/HWPX JSON을 "
            "Step 1 → Step 2 → Step 3 → Final → Value Normalizer로 처리합니다. "
            "--input을 생략하면 파일 선택 창이 열립니다."
        )
    )
    parser.add_argument("--input", default=None, help="정규화 JSON 경로")
    parser.add_argument("--output-dir", default=None, help="구조화 결과 저장 폴더")
    parser.add_argument(
        "--choose-output",
        action="store_true",
        help="출력 폴더도 마우스로 선택",
    )
    parser.add_argument(
        "--skip-value-normalization",
        action="store_true",
        help=(
            "Structure까지만 실행하고 Step 4 값 타입 정규화는 생략합니다."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    try:
        input_path = (
            Path(args.input).expanduser().resolve()
            if args.input
            else _select_input_file()
        )
        if input_path is None:
            print("입력 파일 선택이 취소되었습니다.")
            return

        _validate_normalized_json(input_path)

        default_output = _default_output_dir(input_path)
        if args.output_dir:
            output_dir = Path(args.output_dir).expanduser().resolve()
        elif args.choose_output:
            output_dir = _select_output_directory(default_output.parent)
            if output_dir is None:
                print("출력 폴더 선택이 취소되었습니다.")
                return
        else:
            output_dir = default_output

        final_paths = run_structure_pipeline(
            input_path,
            output_dir,
            run_value_normalization=(
                not args.skip_value_normalization
            ),
        )

        final_output = (
            final_paths.get("step4-1_value_normalized.json")
            or final_paths["step3-3_structured_tables.json"]
        )

        try:
            root = Tk()
            root.withdraw()
            try:
                messagebox.showinfo(
                    "문서 처리 완료",
                    (
                        "구조화 및 값 정규화가 완료되었습니다.\n\n"
                        f"최종 입력 파일:\n{final_output}\n\n"
                        f"출력 폴더:\n{output_dir}"
                    ),
                    parent=root,
                )
            finally:
                root.destroy()
        except Exception:
            # GUI를 사용할 수 없는 서버/WSL 환경에서도 실행 결과는 유지한다.
            pass

    except Exception as error:
        print()
        print("[ERROR] Structure Pipeline 실패")
        print(error)
        traceback.print_exc()

        try:
            root = Tk()
            root.withdraw()
            messagebox.showerror(
                "Structure 오류",
                str(error),
                parent=root,
            )
            root.destroy()
        except Exception:
            pass
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
