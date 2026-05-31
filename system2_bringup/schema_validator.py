"""schema_validator.py — 3단계 Schema Validation (Ch05 확장).

Ch03 대비 변경:
- find/scan/follow의 L3 범위 검증 추가
- assess_scene/resolve_target/follow_query의 L3 범위 검증 추가
- find target_class는 free text (L2 검증 생략)
"""
from .plan_models import HighLevelPlan, ValidationResult


class SchemaValidator:
    """HighLevelPlan의 의미적/안전 검증.

    L1(구조 검증)은 Pydantic model_validate_json()에서 이미 수행됩니다.
    이 클래스는 L2(의미) + L3(안전) 검증을 담당합니다.
    """

    MAX_PATROL_DURATION = 3600  # 1시간
    MAX_WAIT_SECONDS = 300  # 5분
    MAX_FIND_TIMEOUT = 120  # 2분
    MAX_SCAN_DURATION = 120  # 2분
    MAX_FOLLOW_TIME = 180  # 3분
    MAX_ASSESS_TIMEOUT = 120  # 2분
    MAX_RESOLVE_TIMEOUT = 120  # 2분
    MAX_STEP_DURATION = 180  # 3분

    def __init__(self, semantic_locations: list[str], patrol_routes: list[str]):
        self.locations = set(semantic_locations)
        self.patrol_routes = set(patrol_routes)

    def validate(self, plan: HighLevelPlan) -> ValidationResult:
        """L2 + L3 검증을 수행합니다."""
        # ---- L2: 의미 검증 ----
        for i, step in enumerate(plan.steps):
            if step.task == "go_to":
                loc = step.params.location
                if loc not in self.locations:
                    similar = self._find_similar(loc)
                    hint = f" (유사: {similar})" if similar else ""
                    return ValidationResult(
                        ok=False,
                        error=f"steps[{i}]: 알 수 없는 위치 '{loc}'{hint}. "
                        f"허용 목록: {sorted(self.locations)}",
                        level="L2",
                    )

            if step.task == "patrol":
                area = step.params.area
                if area not in self.patrol_routes:
                    return ValidationResult(
                        ok=False,
                        error=f"steps[{i}]: 알 수 없는 순찰 루트 '{area}'. "
                        f"허용 목록: {sorted(self.patrol_routes)}",
                        level="L2",
                    )

        # ---- L3: 안전 범위 검증 ----
        for i, step in enumerate(plan.steps):
            if step.task == "patrol":
                dur = step.params.duration
                if dur > self.MAX_PATROL_DURATION:
                    return ValidationResult(
                        ok=False,
                        error=(
                            f"steps[{i}]: patrol duration {dur}초 > "
                            f"최대 {self.MAX_PATROL_DURATION}초"
                        ),
                        level="L3",
                    )

            if step.task == "wait":
                sec = step.params.seconds
                if sec > self.MAX_WAIT_SECONDS:
                    return ValidationResult(
                        ok=False,
                        error=(
                            f"steps[{i}]: wait {sec}초 > "
                            f"최대 {self.MAX_WAIT_SECONDS}초"
                        ),
                        level="L3",
                    )

            if step.task == "find":
                t = step.params.timeout_sec
                if t > self.MAX_FIND_TIMEOUT:
                    return ValidationResult(
                        ok=False,
                        error=(
                            f"steps[{i}]: find timeout {t}초 > "
                            f"최대 {self.MAX_FIND_TIMEOUT}초"
                        ),
                        level="L3",
                    )

            if step.task == "scan":
                d = step.params.duration_sec
                if d > self.MAX_SCAN_DURATION:
                    return ValidationResult(
                        ok=False,
                        error=(
                            f"steps[{i}]: scan duration {d}초 > "
                            f"최대 {self.MAX_SCAN_DURATION}초"
                        ),
                        level="L3",
                    )

            if step.task == "follow":
                t = step.params.max_time_sec
                if t > self.MAX_FOLLOW_TIME:
                    return ValidationResult(
                        ok=False,
                        error=(
                            f"steps[{i}]: follow max_time {t}초 > "
                            f"최대 {self.MAX_FOLLOW_TIME}초"
                        ),
                        level="L3",
                    )

            if step.task == "assess_scene":
                t = step.params.timeout_sec
                if t > self.MAX_ASSESS_TIMEOUT:
                    return ValidationResult(
                        ok=False,
                        error=(
                            f"steps[{i}]: assess_scene timeout {t}초 > "
                            f"최대 {self.MAX_ASSESS_TIMEOUT}초"
                        ),
                        level="L3",
                    )

            if step.task == "resolve_target":
                t = step.params.timeout_sec
                if t > self.MAX_RESOLVE_TIMEOUT:
                    return ValidationResult(
                        ok=False,
                        error=(
                            f"steps[{i}]: resolve_target timeout {t}초 > "
                            f"최대 {self.MAX_RESOLVE_TIMEOUT}초"
                        ),
                        level="L3",
                    )

            if step.task == "follow_query":
                resolve_t = step.params.resolve_timeout_sec
                follow_t = step.params.max_time_sec
                if resolve_t > self.MAX_RESOLVE_TIMEOUT:
                    return ValidationResult(
                        ok=False,
                        error=(
                            f"steps[{i}]: follow_query resolve_timeout {resolve_t}초 > "
                            f"최대 {self.MAX_RESOLVE_TIMEOUT}초"
                        ),
                        level="L3",
                    )
                if follow_t > self.MAX_FOLLOW_TIME:
                    return ValidationResult(
                        ok=False,
                        error=(
                            f"steps[{i}]: follow_query max_time {follow_t}초 > "
                            f"최대 {self.MAX_FOLLOW_TIME}초"
                        ),
                        level="L3",
                    )

            # max_duration_sec 공통 검증
            md = getattr(step, "max_duration_sec", None)
            if md is not None and md > self.MAX_STEP_DURATION:
                return ValidationResult(
                    ok=False,
                    error=(
                        f"steps[{i}]: max_duration_sec {md}초 > "
                        f"최대 {self.MAX_STEP_DURATION}초"
                    ),
                    level="L3",
                )

        return ValidationResult(ok=True)

    def _find_similar(self, query: str) -> str:
        """간단한 유사 위치 검색 (접두사 매칭)."""
        if not query:
            return ""
        for loc in self.locations:
            if loc.startswith(query[:3]) or query.startswith(loc[:3]):
                return loc
        return ""
