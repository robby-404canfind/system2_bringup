"""plan_generator.py — 자연어 명령 -> HighLevelPlan 생성 (Ch05 확장).

    Ch03 대비 변경:
    - System Prompt에 find/scan/follow/assess_scene/follow_query 액션 설명 추가
- Social Navigation 판단 규칙 추가
"""
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
- 사용자의 자연어 명령과 현재 로봇 상태를 바탕으로 HighLevelPlan JSON을 생성한다.
- 이 계획은 System1(Nav2)과 Perception Action이 순차적으로 실행하는 Unit Action 시퀀스이다.

[사용 가능한 Unit Action]
- go_to(location): 시맨틱 위치로 이동
- patrol(area, duration): 사전 정의된 순찰 루트 실행 (duration: 초 단위)
- wait(seconds): 지정 시간 대기
- report(status): 상태 보고
- find(target_class, timeout_sec, sweep_deg): 로봇 회전으로 대상 탐색 (YOLO 기반)
- scan(duration_sec, sweep_deg): 주변 환경에서 인지 가능한 모든 객체 스캔 및 관찰
- follow(target_class, target_id, target_distance_m, max_time_sec): 대상 추적
- assess_scene(query, timeout_sec): 현재 snapshot/VLM으로 장면을 평가하고 결과를 저장
- resolve_target(target_query, timeout_sec): 자연어 대상 설명을 person track id로 해석
- follow_query(target_query, target_distance_m, max_time_sec, resolve_timeout_sec): resolve_target 후 기존 follow 실행

[허용된 시맨틱 위치]
{locations}

[허용된 순찰 루트 ID]
{patrol_routes}

[Social Navigation 판단 규칙]
- [Social Navigation] 섹션에 avoid_between_people가 있으면, 허용된 시맨틱 위치를 사용해 우회용 go_to() Step을 삽입하라.
- prefer_side_pass가 있으면, 해당 방향(side)으로 우회할 수 있는 시맨틱 위치를 선택하라.
- slow_down이 있으면, wait(3~5초) 후 원래 목적지로 go_to를 재실행하라.
- clear_path가 있으면, 우회 없이 직진하라.

[Agentic VLA 판단 규칙]
- "수상한 사람", "이상한 사람", "박스 근처 확인" 같은 장면 판단 명령은 assess_scene(query)를 사용하라.
- assess_scene 다음에 사용자에게 결과를 알려야 하면 report(status="latest_assessment")를 사용하라.
- "파란색 옷", "가방 든 사람", "왼쪽 사람"처럼 자연어 대상 설명을 따라가라는 명령은 follow_query(...)를 사용하라.
- resolve_target은 대상 식별만 보고해야 할 때 사용하고, 추적까지 필요하면 follow_query를 우선 사용하라.
- 성별/나이/신원은 primary target key로 사용하지 말고, 옷 색상/소지품/위치/track id를 우선하라.

[출력 형식]
반드시 아래 JSON 형식으로만 응답하라. 다른 텍스트는 포함하지 마라.
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
- 허용된 시맨틱 위치만 사용하라 (go_to의 location).
- 허용된 순찰 루트 ID만 사용하라 (patrol의 area).
- steps는 1-5개로 제한하라.
- mission_id는 제공된 값을 그대로 사용하라.
- find/scan/assess_scene/resolve_target의 timeout은 120초 이하로 설정하라.
- follow/follow_query의 추적 시간은 180초 이하로 설정하라.
- 사용자의 명령이 불명확하거나, 무의미한 문자열이거나, 허용된 위치/순찰 루트/액션으로 해석할 근거가 부족하면 추측하지 마라.
- 존재하지 않는 장소(예: 우주, 도서관)를 임의의 허용 위치로 치환하지 마라.
- 이해할 수 없거나 현재 수행 불가능한 명령은 `report(status)` 한 단계만 생성하여 재입력을 요청하라.
"""


FEASIBILITY_PROMPT = """\
너는 System2 명령 접수 검증기이다.

[목표]
- 사용자의 자연어 명령이 현재 시스템에서 실행 가능한지 먼저 판정한다.
- 실행 가능하면 feasible=true
- 불명확/무의미/잡음 입력이거나, 현재 허용된 위치/순찰 루트/액션으로 해석할 근거가 부족하면 feasible=false
- 존재하지 않는 장소(예: 우주, 도서관)를 임의의 허용 위치로 치환하지 마라.
- 이해 못한 명령을 그럴듯한 허용 액션으로 추측하지 마라.

[사용 가능한 액션]
- go_to, patrol, wait, report, find, scan, follow, assess_scene, resolve_target, follow_query

[허용된 시맨틱 위치]
{locations}

[허용된 순찰 루트 ID]
{patrol_routes}

[판정 기준]
- 허용된 위치/액션으로 자연스럽게 해석 가능하면 feasible=true
- "ㅁㄴㅇㄹㅁㄴㅇㅎ" 같은 잡음/오타열은 feasible=false
- "우주로 가줘", "도서관으로 가줘"처럼 현재 시스템 범위를 벗어난 목적지는 feasible=false
- find/scan/follow/assess_scene/follow_query를 포함한 복합 명령도 현재 액션 집합으로 해석 가능하면 feasible=true

[출력 형식]
반드시 아래 JSON 형식으로만 응답하라.
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
    """사용자 명령 + 컨텍스트 -> User Prompt."""
    prompt = f"[명령] {command}"
    if context:
        prompt += f"\n[현재 상태]\n{context}"
    return prompt


def is_obvious_noise_command(command: str) -> bool:
    """명백한 키보드 잡음/자모열 입력을 감지합니다."""
    text = command.strip()
    if not text:
        return True

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

    판정 실패 시 None을 반환하고, 기존 planning 경로를 계속 사용합니다.
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
                        "status": report_status or "명령을 이해하지 못했거나 현재 수행할 수 없습니다. 다시 말씀해 주세요.",
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
    """자연어 명령 -> HighLevelPlan JSON 생성."""
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
                    or "명령을 이해하지 못했거나 현재 수행할 수 없습니다. 가능한 위치나 행동으로 다시 말씀해 주세요."
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
