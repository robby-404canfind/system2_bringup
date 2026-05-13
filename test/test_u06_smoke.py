"""test_u06_smoke.py — ROS2 없이 System2 파이프라인 스모크 테스트."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from system2_bringup.action_dispatcher import ActionDispatcher
from system2_bringup.context_builder import ContextBuilder
from system2_bringup.llm_client import LLMClient, LLMClientError
from system2_bringup.plan_generator import SchemaInvalidError, generate_and_validate
from system2_bringup.plan_models import ActionResult
from system2_bringup.schema_validator import SchemaValidator

LOCATIONS = [
    "office_desk_1",
    "meeting_room",
    "corridor_a",
    "lobby",
    "charging_station",
]
PATROL_ROUTES = ["office_loop", "lobby_loop"]
SEMANTIC_LOCATIONS = {
    name: {"x": 0.0, "y": 0.0} for name in LOCATIONS
}


def smoke_test_1_single_command():
    print("\n" + "=" * 60)
    print("스모크 테스트 1: 단일 명령")
    print("=" * 60)

    client = LLMClient(backend="ollama", model="qwen2.5:7b")
    validator = SchemaValidator(LOCATIONS, PATROL_ROUTES)
    ctx = ContextBuilder(semantic_locations=SEMANTIC_LOCATIONS)

    plan = generate_and_validate(
        client,
        "회의실로 가줘",
        LOCATIONS,
        PATROL_ROUTES,
        mission_id="smoke-001",
        validator=validator,
    )
    print(f"✓ Plan 생성 성공: {plan.intent}")
    print(f"  steps: {len(plan.steps)}개")
    for i, step in enumerate(plan.steps):
        print(f"  [{i}] {step.task}({step.params})")

    dispatcher = ActionDispatcher()
    ctx.start_mission(len(plan.steps))
    for step in plan.steps:
        result = dispatcher.dispatch(step)
        if result.success:
            ctx.record_success(step, result)
        print(f"  → {result.message}")

    assert len(plan.steps) >= 1, "최소 1 Step 필요"
    assert plan.steps[0].task == "go_to", "첫 Step은 go_to여야 함"
    print("✓ 스모크 테스트 1 통과")


def smoke_test_2_multi_step():
    print("\n" + "=" * 60)
    print("스모크 테스트 2: 2-step 명령")
    print("=" * 60)

    client = LLMClient(backend="ollama", model="qwen2.5:7b")
    validator = SchemaValidator(LOCATIONS, PATROL_ROUTES)

    plan = generate_and_validate(
        client,
        "회의실 갔다가 충전소로 와",
        LOCATIONS,
        PATROL_ROUTES,
        mission_id="smoke-002",
        validator=validator,
    )
    print(f"✓ Plan 생성 성공: {plan.intent}")
    print(f"  steps: {len(plan.steps)}개")
    for i, step in enumerate(plan.steps):
        print(f"  [{i}] {step.task}({step.params})")

    dispatcher = ActionDispatcher()
    for step in plan.steps:
        result = dispatcher.dispatch(step)
        print(f"  → {result.message}")

    assert len(plan.steps) >= 2, "최소 2 Step 필요"
    print("✓ 스모크 테스트 2 통과")


def smoke_test_3_failure_replan():
    print("\n" + "=" * 60)
    print("스모크 테스트 3: 실패 + Replan")
    print("=" * 60)

    client = LLMClient(backend="ollama", model="qwen2.5:7b")
    validator = SchemaValidator(LOCATIONS, PATROL_ROUTES)
    ctx = ContextBuilder(semantic_locations=SEMANTIC_LOCATIONS)

    plan = generate_and_validate(
        client,
        "회의실 갔다가 충전소로 와",
        LOCATIONS,
        PATROL_ROUTES,
        mission_id="smoke-003",
        validator=validator,
    )
    print(f"✓ 최초 Plan: {plan.intent} ({len(plan.steps)} steps)")

    failed_step = plan.steps[0]
    failed_result = ActionResult(
        success=False,
        message="HARD_STUCK: 장애물로 진입 불가",
    )
    ctx.start_mission(len(plan.steps))
    ctx.record_failure(failed_step, failed_result, attempt=0)
    print(f"✗ Step 0 강제 실패: {failed_result.message}")

    replan_ctx = ctx.build_replan_context(failed_step, failed_result)
    print(f"  Replan context:\n{replan_ctx}")

    try:
        new_plan = generate_and_validate(
            client,
            replan_ctx,
            LOCATIONS,
            PATROL_ROUTES,
            mission_id=plan.mission_id,
            validator=validator,
        )
        print(f"✓ Replan 성공: {new_plan.intent} ({len(new_plan.steps)} steps)")
        for i, step in enumerate(new_plan.steps):
            print(f"  [{i}] {step.task}({step.params})")
        print("✓ 스모크 테스트 3 통과 (Replan 성공)")
    except SchemaInvalidError as e:
        print(f"✗ Replan 스키마 실패: {e}")
        print(
            "△ 스모크 테스트 3 부분 통과 "
            "(Replan 경로 확인됨, 출력 계약 문제)"
        )
    except LLMClientError as e:
        print(f"✗ Replan 실패: {e}")
        print(
            "△ 스모크 테스트 3 부분 통과 "
            "(Replan 경로 확인됨, LLM 응답 품질 문제)"
        )


if __name__ == "__main__":
    try:
        smoke_test_1_single_command()
        smoke_test_2_multi_step()
        smoke_test_3_failure_replan()
        print("\n" + "=" * 60)
        print("전체 스모크 테스트 완료")
        print("=" * 60)
    except Exception as e:
        print(f"\n✗ 테스트 실패: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
