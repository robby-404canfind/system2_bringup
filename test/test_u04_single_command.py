"""test_u04_single_command.py — 단일 명령 E2E 테스트."""
import sys

from system2_bringup.action_dispatcher import ActionDispatcher
from system2_bringup.llm_client import LLMClient, LLMClientError
from system2_bringup.plan_generator import SchemaInvalidError, generate_plan
from system2_bringup.schema_validator import SchemaValidator

LOCATIONS = [
    "meeting_room",
    "charging_station",
    "lobby",
    "office_desk_1",
    "corridor_a",
]
PATROL_ROUTES = ["office_loop", "lobby_loop"]


def main() -> int:
    client = LLMClient(backend="ollama", model="qwen2.5:7b")
    validator = SchemaValidator(
        semantic_locations=LOCATIONS,
        patrol_routes=PATROL_ROUTES,
    )
    dispatcher = ActionDispatcher(nav2_navigator=None)

    command = "회의실로 가줘"
    print(f"[입력] {command}")

    try:
        plan = generate_plan(
            client,
            command,
            LOCATIONS,
            PATROL_ROUTES,
            mission_id="e2e-001",
        )
        print(f"[Plan] intent={plan.intent}, steps={len(plan.steps)}")
        print(f"       {plan.model_dump_json(indent=2)}")

        result = validator.validate(plan)
        assert result.ok, f"Validation 실패: {result.error}"
        print("[Validation] OK")

        for i, step in enumerate(plan.steps):
            action_result = dispatcher.dispatch(step)
            print(
                f"[Step {i}] {step.task}: {action_result.message} "
                f"({action_result.elapsed_sec:.1f}s)"
            )
            assert action_result.success, f"Step {i} 실패: {action_result.message}"

        print("[결과] E2E 테스트 성공 ✓")
        return 0

    except LLMClientError as e:
        print(f"[에러] LLM 에러: {e}")
    except SchemaInvalidError as e:
        print(f"[에러] 스키마 오류: {e}")
    except Exception as e:
        print(f"[에러] 예상치 못한 에러: {e}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
