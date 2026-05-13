"""schema_validator.py — 3단계 Schema Validation."""
from .plan_models import HighLevelPlan, ValidationResult


class SchemaValidator:
    """HighLevelPlan의 의미적·안전 검증.

    L1(구조 검증)은 Pydantic model_validate_json()에서 이미 수행됩니다.
    이 클래스는 L2(의미) + L3(안전) 검증을 담당합니다.
    """

    MAX_PATROL_DURATION = 3600  # 1시간
    MAX_WAIT_SECONDS = 300  # 5분

    def __init__(self, semantic_locations: list[str], patrol_routes: list[str]):
        self.locations = set(semantic_locations)
        self.patrol_routes = set(patrol_routes)

    def validate(self, plan: HighLevelPlan) -> ValidationResult:
        """L2 + L3 검증을 수행합니다."""
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

        return ValidationResult(ok=True)

    def _find_similar(self, query: str) -> str:
        """간단한 유사 위치 검색 (접두사 매칭)."""
        if not query:
            return ""
        for loc in sorted(self.locations):
            if loc.startswith(query[:3]) or query.startswith(loc[:3]):
                return loc
        return ""
