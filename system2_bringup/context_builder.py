"""context_builder.py — ROS2 상태 → LLM 컨텍스트 텍스트 변환."""
import math


class ContextBuilder:
    """최소 Context Builder (Ch03).

    수집 항목:
    - 로봇 위치: 가장 가까운 시맨틱 위치
    - 직전 UA 실행 결과: 성공/실패 + 사유
    - 미션 진행 상황: 완료 Step / 전체 Step
    """

    def __init__(self, semantic_locations: dict | None = None):
        """
        Args:
            semantic_locations: {name: {x, y, yaw, ...}} 딕셔너리.
        """
        self.semantic_locations = semantic_locations or {}
        self._history: list[str] = []
        self._completed = 0
        self._total = 0
        self._robot_pose = None  # (x, y) — AMCL 구독 시 업데이트

    def start_mission(self, total_steps: int):
        """새 미션 시작 시 카운터를 초기화합니다."""
        self._history.clear()
        self._completed = 0
        self._total = total_steps

    def reset_mission_state(self):
        """새 top-level 명령 planning 전에 이전 미션의 실행 흔적만 초기화합니다.

        현재 위치(self._robot_pose)는 유지하고,
        실행 이력/진행 카운터만 비웁니다.
        """
        self._history.clear()
        self._completed = 0
        self._total = 0

    def record_success(self, step, result):
        """Step 성공을 기록합니다."""
        self._completed += 1
        self._history.append(
            f"{step.task}({step.params}) → 성공 ({result.elapsed_sec:.1f}초)"
        )

    def record_failure(self, step, result, attempt: int):
        """Step 실패를 기록합니다."""
        self._history.append(
            f"{step.task}({step.params}) → 실패 "
            f"(시도 {attempt + 1}, 사유: {result.message})"
        )

    def build(self) -> str:
        """현재 상태를 텍스트로 반환합니다."""
        parts = []

        # 위치
        location = self._get_nearest_location()
        parts.append(f"위치: {location}")

        # 미션 진행
        if self._total > 0:
            parts.append(
                f"미션 진행: {self._completed}/{self._total} Step 완료"
            )

        # 직전 액션
        if self._history:
            parts.append(f"직전 액션: {self._history[-1]}")

        return "\n".join(parts)

    def build_replan_context(self, failed_step, failed_result) -> str:
        """Replan용 컨텍스트를 생성합니다.

        원래 미션의 완료/실패 정보를 포함하여,
        LLM이 잔여 계획을 생성할 수 있도록 합니다.
        """
        parts = [
            "[이전 계획 실패 보고]",
            f"완료된 Step: {self._completed}/{self._total}",
        ]

        if self._history:
            parts.append("실행 이력:")
            for entry in self._history:
                parts.append(f"  - {entry}")

        parts.append(
            f"실패한 Step: {failed_step.task}({failed_step.params})"
        )
        parts.append(f"실패 사유: {failed_result.message}")
        parts.append(f"현재 위치: {self._get_nearest_location()}")
        parts.append("")
        parts.append("남은 목표를 달성하기 위한 새로운 계획을 생성해 주세요.")

        return "\n".join(parts)

    def _get_nearest_location(self) -> str:
        """AMCL 포즈에서 가장 가까운 시맨틱 위치를 반환합니다.

        Ch03에서는 AMCL 구독을 생략하고 'unknown'을 반환합니다.
        Nav2 연동 시 self._robot_pose를 AMCL 콜백에서 업데이트합니다.
        """
        if self._robot_pose is None or not self.semantic_locations:
            return "unknown (AMCL 미연결)"

        px, py = self._robot_pose
        min_dist = float("inf")
        nearest = "unknown"
        for name, coords in self.semantic_locations.items():
            dist = math.sqrt(
                (px - coords.get("x", 0)) ** 2
                + (py - coords.get("y", 0)) ** 2
            )
            if dist < min_dist:
                min_dist = dist
                nearest = name
        return f"{nearest} 근처 (x={px:.1f}, y={py:.1f})"
