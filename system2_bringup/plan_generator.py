"""plan_generator.py — 자연어 명령 → HighLevelPlan 생성."""
import json
import re

from pydantic import BaseModel
from pydantic import ValidationError

from .llm_client import LLMClient
from .plan_models import HighLevelPlan


class SchemaInvalidError(Exception):
    """모델 출력이 HighLevelPlan 스키마를 만족하지 못할 때 발생."""


class CommandFeasibility(BaseModel):
    """명령 접수 단계의 실행 가능성 판정."""

    feasible: bool
    reason: str = ""
    report_status: str = ""


SYSTEM_PROMPT = """\
너는 Social Navigation 모바일 로봇의 고수준 미션 플래너(System2)이다.

[명령 접수 메타데이터]
- mission_id: {mission_id}
- 위 값은 호출측이 발급한 고정 식별자이다. 새로 생성하거나 변경하지 마라.

[역할]
- 사용자의 자연어 명령과 현재 로봇 상태를 입력으로 HighLevelPlan JSON을 생성한다.
- 이 계획은 System1(Nav2)이 순차적으로 실행하는 Unit Action 시퀀스이다.

[사용 가능한 Unit Action]
- go_to(location): 시맨틱 위치로 이동
- patrol(area, duration): 사전 정의된 순찰 루트 실행 (duration: 초 단위)
- wait(seconds): 지정 시간 대기
- report(status): 상태 보고

[허용된 시맨틱 위치]
{locations}

[허용된 순찰 루트 ID]
{patrol_routes}

[출력 형식]
응답은 아래 JSON 형식만 허용한다. 다른 텍스트는 포함하지 마라.
{{
  "version": "1.0.0",
  "mission_id": "{mission_id}",
  "intent": "미션 의도 요약",
  "constraints": [],
  "steps": [
    {{"task": "go_to", "params": {{"location": "meeting_room"}}, "retry": 1}}
  ],
  "replan_rules": {{}}
}}

[안전 규칙]
- 허용된 Unit Action만 사용하라.
- 허용된 시맨틱 위치만 사용하라.
- 허용된 순찰 루트 ID만 사용하라.
- steps는 1-5개로 제한하라.
- mission_id는 제공된 값을 그대로 사용하라.
- 사용자의 명령이 불명확하거나, 무의미한 문자열이거나, 허용된 위치/순찰 루트로 해석할 근거가 부족하면 추측하지 마라.
- 존재하지 않는 장소(예: 우주, 도서관)를 임의의 허용 위치로 치환하지 마라.
- 이해할 수 없거나 수행 불가능한 명령은 `report(status)` 한 단계만 생성하여 재입력을 요청하라.

[불명확/수행 불가 명령 처리 예시]
- 입력: "ㅁㄴㅇㄹㅁㄴㅇㅎ"
  출력: steps=[{{"task": "report", "params": {{"status": "명령을 이해하지 못했습니다. 다시 말씀해 주세요."}}, "retry": 0}}]
- 입력: "우주로 가줘"
  출력: steps=[{{"task": "report", "params": {{"status": "우주 는 현재 허용된 목적지가 아닙니다. 가능한 위치로 다시 말씀해 주세요."}}, "retry": 0}}]
- 입력: "도서관으로 가줘"
  출력: steps=[{{"task": "report", "params": {{"status": "도서관 은 현재 허용된 목적지가 아닙니다. 가능한 위치로 다시 말씀해 주세요."}}, "retry": 0}}]
"""


FEASIBILITY_PROMPT = """\
너는 System2 명령 접수 검증기이다.

[목표]
- 사용자의 자연어 명령이 현재 시스템에서 실행 가능한지 사전에 판정한다.
- 실행 가능하면 feasible=true
- 불명확/무의미/잡음 입력이거나, 현재 허용된 위치/순찰 루트로 해석할 근거가 부족하면 feasible=false
- 존재하지 않는 장소(예: 우주, 도서관)를 임의의 허용 위치로 치환하지 마라.
- 이해 못한 명령을 그럴듯한 허용 위치로 추측하지 마라.

[허용된 시맨틱 위치]
{locations}

[허용된 순찰 루트 ID]
{patrol_routes}

[판정 기준]
- "회의실로 가줘"처럼 허용 위치로 자연스럽게 해석되면 feasible=true
- "회의실 갔다가 충전소로 와"처럼 복합 명령도 해석되면 feasible=true
- "ㅁㄴㅇㄹㅁㄴㅇㅎ" 같은 잡음/오타열은 feasible=false
- "우주로 가줘", "도서관으로 가줘"처럼 현재 시스템 범위를 벗어난 목적지는 feasible=false

[출력 형식]
응답은 아래 JSON 형식만 허용한다.
{{
  "feasible": true,
  "reason": "짧은 판정 이유",
  "report_status": "feasible=false일 때 사용자에게 보낼 짧은 한국어 메시지"
}}
"""


def build_system_prompt(
    locations: list[str],
    patrol_routes: list[str],
    mission_id: str,
) -> str:
    """허용 목록과 mission_id를 주입한 System Prompt를 생성합니다."""
    return SYSTEM_PROMPT.format(
        locations=", ".join(locations),
        patrol_routes=", ".join(patrol_routes),
        mission_id=mission_id,
    )


def build_feasibility_prompt(
    locations: list[str],
    patrol_routes: list[str],
) -> str:
    """명령 실행 가능성 판정용 System Prompt."""
    return FEASIBILITY_PROMPT.format(
        locations=", ".join(locations),
        patrol_routes=", ".join(patrol_routes),
    )


def build_user_prompt(command: str, context: str = "") -> str:
    """사용자 명령 + 컨텍스트 → User Prompt."""
    prompt = f"[명령] {command}"
    if context:
        prompt += f"\n[현재 상태]\n{context}"
    return prompt


def is_obvious_noise_command(command: str) -> bool:
    """명백한 키보드 잡음/자모열 입력을 감지합니다."""
    text = command.strip()
    if not text:
        return True

    # 한글 완성형/영문/숫자가 전혀 없고 자모/공백/문장부호 위주면 잡음으로 간주
    has_hangul_syllable = bool(re.search(r"[가-힣]", text))
    has_ascii_word = bool(re.search(r"[A-Za-z0-9]", text))
    non_space = re.sub(r"\s+", "", text)
    jamo_only = re.fullmatch(r"[ㄱ-ㅎㅏ-ㅣ~!@#$%^&*()_+\-=\[\]{};':\",./<>?\\|`]+", non_space)

    return (not has_hangul_syllable) and (not has_ascii_word) and bool(jamo_only)


def classify_command_feasibility(
    client: LLMClient,
    command: str,
    locations: list[str],
    patrol_routes: list[str],
) -> CommandFeasibility | None:
    """Top-level 사용자 명령이 실행 가능한지 사전 판정합니다.

    판정 실패 시 None을 반환하며 기존 planning 경로를 계속 사용합니다.
    """
    messages = [
        {"role": "system", "content": build_feasibility_prompt(locations, patrol_routes)},
        {"role": "user", "content": command},
    ]

    try:
        response = client.chat(
            messages=messages,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        return CommandFeasibility.model_validate(json.loads(raw))
    except Exception:
        return None


def build_reject_plan(mission_id: str, report_status: str, reason: str = "") -> HighLevelPlan:
    """실행 불가/불명확 명령에 대한 report-only plan을 생성합니다."""
    constraints = ["clarification_required"]
    if reason:
        constraints.append(reason)

    return HighLevelPlan.model_validate(
        {
            "version": "1.0.0",
            "mission_id": mission_id,
            "intent": "명령 재입력 요청",
            "constraints": constraints,
            "steps": [
                {
                    "task": "report",
                    "params": {
                        "status": report_status or "명령을 이해하지 못했습니다. 가능한 위치로 다시 말씀해 주세요.",
                    },
                    "retry": 0,
                }
            ],
            "replan_rules": {},
        }
    )


def generate_plan(
    client: LLMClient,
    command: str,
    locations: list[str],
    patrol_routes: list[str],
    mission_id: str,
    context: str = "",
) -> HighLevelPlan:
    """자연어 명령 → HighLevelPlan JSON 생성."""
    system_prompt = build_system_prompt(locations, patrol_routes, mission_id)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": build_user_prompt(command, context)},
    ]

    response = client.chat(
        messages=messages,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content

    try:
        plan = HighLevelPlan.model_validate_json(raw)
    except ValidationError as e:
        raise SchemaInvalidError(f"L1 구조 검증 실패: {e}") from e

    return plan.model_copy(update={"mission_id": mission_id})


def generate_and_validate(
    client: LLMClient,
    command: str,
    locations: list[str],
    patrol_routes: list[str],
    mission_id: str,
    validator,
    context: str = "",
    max_retries: int = 2,
) -> HighLevelPlan:
    """Plan 생성 + L1/L2/L3 검증을 단일 retry budget으로 관리합니다."""
    # Replan context가 아닌 top-level 사용자 명령에만 명령 접수 가능성 검증을 적용합니다.
    if not command.lstrip().startswith("[이전 계획 실패 보고]"):
        if is_obvious_noise_command(command):
            return build_reject_plan(
                mission_id=mission_id,
                report_status="명령을 이해하지 못했습니다. 다시 말씀해 주세요.",
                reason="obvious_noise_command",
            )

        feasibility = classify_command_feasibility(
            client,
            command,
            locations,
            patrol_routes,
        )
        if feasibility is not None and not feasibility.feasible:
            return build_reject_plan(
                mission_id=mission_id,
                report_status=(
                    feasibility.report_status
                    or "명령을 이해하지 못했거나 현재 수행할 수 없습니다. 가능한 위치로 다시 말씀해 주세요."
                ),
                reason=feasibility.reason,
            )

    feedback = ""
    last_error = ""

    for _attempt in range(max_retries + 1):
        try:
            plan = generate_plan(
                client,
                command,
                locations,
                patrol_routes,
                mission_id=mission_id,
                context=context + feedback,
            )
        except SchemaInvalidError as e:
            last_error = str(e)
            feedback = (
                f"\n[이전 출력 오류]\n{last_error}\n"
                "오류를 수정하여 올바른 HighLevelPlan JSON을 다시 생성하세요."
            )
            continue

        result = validator.validate(plan)
        if result.ok:
            return plan

        last_error = result.error
        feedback = f"\n[검증 실패]\n{result.error}\n올바른 값으로 수정하세요."

    raise SchemaInvalidError(
        f"Plan 생성/검증 실패 ({max_retries + 1}회 시도): {last_error}"
    )
