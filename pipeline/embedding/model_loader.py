from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import torch


class ModelLoadError(RuntimeError):
    """임베딩 모델을 로드하지 못했을 때 발생하는 오류."""


@dataclass(frozen=True)
class ModelRuntimeInfo:
    """
    현재 임베딩 모델 실행 환경 정보.
    """

    model_name: str
    device: str
    device_name: str
    use_fp16: bool
    cuda_available: bool
    cuda_version: str | None
    torch_version: str
    gpu_memory_gb: float | None


@dataclass(frozen=True)
class LoadedEmbeddingModel:
    """
    로드된 BGE-M3 모델과 실행 환경 정보를 함께 보관한다.
    """

    model: Any
    runtime: ModelRuntimeInfo


def _get_gpu_memory_gb(device_index: int = 0) -> float | None:
    """
    지정한 GPU의 총 메모리를 GB 단위로 반환한다.
    """

    if not torch.cuda.is_available():
        return None

    properties = torch.cuda.get_device_properties(device_index)
    return round(properties.total_memory / (1024 ** 3), 2)


def get_runtime_info(
    *,
    model_name: str,
    use_fp16: bool,
    require_cuda: bool = True,
    device_index: int = 0,
) -> ModelRuntimeInfo:
    """
    PyTorch와 CUDA 실행 환경을 확인한다.

    Args:
        model_name:
            사용할 Hugging Face 모델 ID.

        use_fp16:
            FP16 사용 여부.

        require_cuda:
            True이면 CUDA가 없을 때 오류를 발생시킨다.

        device_index:
            사용할 GPU 번호.

    Returns:
        ModelRuntimeInfo
    """

    cuda_available = torch.cuda.is_available()

    if require_cuda and not cuda_available:
        raise ModelLoadError(
            "CUDA를 사용할 수 없습니다.\n"
            "다음 명령으로 상태를 확인하세요.\n"
            "1. nvidia-smi\n"
            "2. python -c \"import torch; "
            "print(torch.cuda.is_available())\"\n"
            "현재 프로젝트는 AWS GPU 임베딩을 전제로 하므로 "
            "CPU 실행으로 자동 전환하지 않습니다."
        )

    if cuda_available:
        device = f"cuda:{device_index}"
        device_name = torch.cuda.get_device_name(device_index)
        gpu_memory_gb = _get_gpu_memory_gb(device_index)
    else:
        device = "cpu"
        device_name = "CPU"
        gpu_memory_gb = None

    return ModelRuntimeInfo(
        model_name=model_name,
        device=device,
        device_name=device_name,
        use_fp16=use_fp16 and cuda_available,
        cuda_available=cuda_available,
        cuda_version=torch.version.cuda,
        torch_version=torch.__version__,
        gpu_memory_gb=gpu_memory_gb,
    )


def load_bge_m3_model(
    *,
    model_name: str = "BAAI/bge-m3",
    use_fp16: bool = True,
    require_cuda: bool = True,
    device_index: int = 0,
) -> LoadedEmbeddingModel:
    """
    BGE-M3 모델을 로드한다.

    첫 실행 시 Hugging Face에서 모델 파일을 다운로드한다.
    이후에는 Hugging Face 캐시를 재사용한다.

    Args:
        model_name:
            Hugging Face 모델 ID.

        use_fp16:
            GPU 추론 시 FP16 사용 여부.

        require_cuda:
            CUDA가 없을 때 실행을 중단할지 여부.

        device_index:
            사용할 GPU 번호.

    Returns:
        LoadedEmbeddingModel

    Raises:
        ModelLoadError:
            환경 확인 또는 모델 로드에 실패한 경우.
    """

    runtime = get_runtime_info(
        model_name=model_name,
        use_fp16=use_fp16,
        require_cuda=require_cuda,
        device_index=device_index,
    )

    try:
        from FlagEmbedding import BGEM3FlagModel
    except Exception as exc:
        raise ModelLoadError(
            f"""
FlagEmbedding import 실패

실제 오류:
{type(exc).__name__}

{exc}
"""
    ) from exc

    try:
        print("=" * 70)
        print("BGE-M3 모델 로드")
        print("=" * 70)
        print(f"모델          : {runtime.model_name}")
        print(f"장치          : {runtime.device}")
        print(f"장치 이름     : {runtime.device_name}")
        print(f"CUDA 사용     : {runtime.cuda_available}")
        print(f"CUDA 버전     : {runtime.cuda_version}")
        print(f"PyTorch 버전  : {runtime.torch_version}")
        print(f"FP16 사용     : {runtime.use_fp16}")

        if runtime.gpu_memory_gb is not None:
            print(f"GPU 메모리    : {runtime.gpu_memory_gb} GB")

        model = BGEM3FlagModel(
            model_name,
            use_fp16=runtime.use_fp16,
            devices=runtime.device,
        )

    except Exception as exc:
        raise ModelLoadError(
            "BGE-M3 모델을 로드하지 못했습니다.\n"
            f"모델: {model_name}\n"
            f"장치: {runtime.device}\n"
            f"원인: {exc}"
        ) from exc

    return LoadedEmbeddingModel(
        model=model,
        runtime=runtime,
    )


def clear_cuda_cache() -> None:
    """
    사용하지 않는 CUDA 캐시를 정리한다.

    모델을 삭제하는 함수는 아니며,
    PyTorch가 보유한 비사용 캐시만 반환한다.
    """

    if torch.cuda.is_available():
        torch.cuda.empty_cache()