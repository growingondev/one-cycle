from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .context_builder import render_context_block
from .intent_router import classify_intents
from .models import PromptPayload, SourceContext


PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _load_json(path: Path) -> dict[str, Any]:
    """
    JSON 프롬프트 파일을 읽는다.
    """
    if not path.exists():
        raise FileNotFoundError(f"프롬프트 파일을 찾을 수 없습니다: {path}")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _render_rules(
    title: str,
    rules: list[str],
) -> str:
    """
    JSON의 rules 배열을 LLM이 읽을 수 있는 프롬프트 문자열로 변환한다.
    """
    lines = [f"[{title}]"]

    for index, rule in enumerate(rules, start=1):
        lines.append(f"{index}. {rule}")

    return "\n".join(lines)


def _build_core_prompt(core_config: dict[str, Any]) -> str:
    """
    core.json의 grounding / accuracy / output 규칙을 문자열로 조립한다.
    """
    rules = core_config.get("rules", {})

    sections = [
        _render_rules(
            "근거 사용",
            rules.get("grounding", []),
        ),
        _render_rules(
            "정보 정확성",
            rules.get("accuracy", []),
        ),
        _render_rules(
            "출력 제한",
            rules.get("output", []),
        ),
    ]

    return "\n\n".join(sections)


def _build_domain_prompt(domain_config: dict[str, Any]) -> str:
    """
    현재 서비스 도메인 규칙을 문자열로 조립한다.
    """
    organization = domain_config.get("organization", "")
    document_scope = domain_config.get("document_scope", [])
    rules = domain_config.get("rules", [])

    scope_text = ", ".join(document_scope)

    sections = [
        "[도메인]",
        f"기관: {organization}",
        f"대상 문서: {scope_text}",
    ]

    if rules:
        sections.append("")
        sections.append(_render_rules("도메인 규칙", rules))

    return "\n".join(sections)


def _build_persona_prompt(persona_config: dict[str, Any]) -> str:
    """
    사용자 Persona에 따른 답변 방식을 문자열로 조립한다.
    """
    description = persona_config.get("description", "")
    rules = persona_config.get("rules", [])

    sections = [
        "[역할 및 답변 방식]",
        f"당신은 {description}를 대상으로 문서 내용을 안내하는 질의응답 도우미입니다.",
    ]

    if rules:
        sections.append("")
        sections.append(_render_rules("답변 방식", rules))

    return "\n".join(sections)


def _build_intent_prompt(intents: list[str]) -> str:
    """
    분류된 Intent에 해당하는 JSON 파일을 읽어
    질문 유형별 지침을 조립한다.
    """
    sections: list[str] = []

    for intent in intents:
        intent_path = PROMPTS_DIR / "intents" / f"{intent}.json"
        intent_config = _load_json(intent_path)

        description = intent_config.get("description", "")
        rules = intent_config.get("rules", [])

        intent_lines = [
            f"[질문 유형: {intent}]",
            description,
        ]

        if rules:
            intent_lines.append("")
            intent_lines.append(_render_rules("질문 유형별 규칙", rules))

        sections.append("\n".join(intent_lines))

    return "\n\n".join(sections)


def build_prompt(
    *,
    query: str,
    announcement_directory: str,
    document_format: str,
    sources: list[SourceContext],
) -> PromptPayload:
    query = query.strip()

    if not query:
        raise ValueError("사용자 질문이 비어 있습니다.")

    # 1. 질문 Intent 분류
    intents = classify_intents(query)

    # 2. JSON 프롬프트 로드
    core_config = _load_json(
        PROMPTS_DIR / "core.json"
    )

    domain_config = _load_json(
        PROMPTS_DIR / "domains" / "lh.json"
    )

    persona_config = _load_json(
        PROMPTS_DIR / "personas" / "public_user.json"
    )

    # 3. System Prompt 조립
    system_prompt = "\n\n".join(
        [
            _build_domain_prompt(domain_config),
            _build_persona_prompt(persona_config),
            _build_core_prompt(core_config),
        ]
    ).strip()

    # 4. Intent Prompt 조립
    intent_prompt = _build_intent_prompt(intents)

    # 5. Retrieval Context 생성
    context_block = render_context_block(sources)

    # 6. User Prompt 조립
    user_prompt = f"""
[질문 유형별 지침]
{intent_prompt}

[선택한 LH 공고]
{announcement_directory}

[문서 형식]
{document_format}

[사용자 질문]
{query}

[LH 공고문 근거]
{context_block}
""".strip()

    return PromptPayload(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        query=query,
        announcement_directory=announcement_directory,
        document_format=document_format,
        sources=sources,
    )