"""HWP/HWPX 문서 Parser 패키지."""

from __future__ import annotations

from typing import Any

__all__ = ["parse_hwp", "parse_hwpx"]


def __getattr__(name: str) -> Any:
    if name == "parse_hwp":
        from .hwp_parser import parse_hwp

        return parse_hwp

    if name == "parse_hwpx":
        from .hwpx_parser import parse_hwpx

        return parse_hwpx

    raise AttributeError(name)
