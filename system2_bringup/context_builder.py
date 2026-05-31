"""context_builder.py — ROS2 상태 -> LLM 컨텍스트 텍스트 변환 (Ch05 확장).

Ch03 대비 변경:
- update_perception(): /perception/context/raw JSON 수신
- _perception_to_text(): YOLO detections + VLM social_hints -> 텍스트
- build()에 [Perception], [Social Navigation] 섹션 추가
"""
import json
import math


class ContextBuilder:
    """Context Builder (Ch05).

    수집 항목:
    - 로봇 위치: AMCL pose -> 시맨틱 위치
    - 직전 UA 실행 결과: 성공/실패 + 사유
    - 미션 진행 상황: 완료 Step / 전체 Step
    - Perception context: YOLO detections + VLM social_hints (Ch05 추가)
    """

    def __init__(self, semantic_locations: dict | None = None):
        self.semantic_locations = semantic_locations or {}
        self._history: list[str] = []
        self._completed = 0
        self._total = 0
        self._robot_pose = None  # (x, y) — AMCL 콜백에서 업데이트
        self._perception_raw: dict | None = None

    # ---- 미션 추적 (Ch03 동일) ----

    def start_mission(self, total_steps: int):
        """새 미션 시작 시 카운터를 초기화합니다."""
        self._history.clear()
        self._completed = 0
        self._total = total_steps

    def reset_mission_state(self):
        """새 top-level 명령 planning 전에 이전 미션의 실행 흔적만 초기화합니다.

        현재 위치(self._robot_pose)와 perception context는 유지하고,
        실행 이력/진행 카운터만 비웁니다.
        """
        self._history.clear()
        self._completed = 0
        self._total = 0

    def record_success(self, step, result):
        """Step 성공을 기록합니다."""
        self._completed += 1
        message = f", 결과: {result.message}" if getattr(result, "message", "") else ""
        self._history.append(
            f"{step.task}({step.params}) -> 성공 ({result.elapsed_sec:.1f}초{message})"
        )

    def record_failure(self, step, result, attempt: int):
        """Step 실패를 기록합니다."""
        self._history.append(
            f"{step.task}({step.params}) -> 실패 "
            f"(시도 {attempt + 1}, 사유: {result.message})"
        )

    # ---- Perception 연동 (Ch05 추가) ----

    def update_perception(self, raw_json: str):
        """System2PlannerNode가 /perception/context/raw 콜백에서 호출합니다."""
        try:
            self._perception_raw = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            self._perception_raw = None

    # ---- 컨텍스트 빌드 ----

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

        # Perception (Ch05 추가)
        if self._perception_raw:
            parts.append(self._perception_to_text())

        # 직전 액션
        if self._history:
            parts.append(f"직전 액션: {self._history[-1]}")

        return "\n".join(parts)

    def build_replan_context(self, failed_step, failed_result) -> str:
        """Replan용 컨텍스트를 생성합니다."""
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

        # Perception 정보 포함 (Ch05)
        if self._perception_raw:
            parts.append("")
            parts.append(self._perception_to_text())

        parts.append("")
        parts.append("남은 목표를 달성하기 위한 새로운 계획을 생성해 주세요.")

        return "\n".join(parts)

    # ---- 내부 메서드 ----

    def _get_nearest_location(self) -> str:
        """AMCL 포즈에서 가장 가까운 시맨틱 위치를 반환합니다."""
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

    def _perception_to_text(self) -> str:
        """perception/context/raw JSON -> LLM 텍스트.

        /perception/context/raw JSON 구조 (Ch04 PerceptionContextBuilderNode):
        {
            "frame_w": int, "frame_h": int,
            "objects": [{id, class, confidence, center, bbox, direction, range_m}],
            "vlm_scene": {"scene_summary": str, "social_hints": [...]},
        }
        """
        data = self._perception_raw
        if not data:
            return ""

        lines = []

        # [Perception] 섹션: objects 요약
        objects = data.get("objects", [])
        if objects:
            lines.append("[Perception]")
            for obj in objects[:5]:  # 최대 5개까지
                cls = obj.get("class", "unknown")
                obj_id = obj.get("id", "?")
                direction = obj.get("direction", "?")
                range_m = obj.get("range_m")
                range_str = f"{range_m:.1f}m" if range_m else "depth N/A"
                conf = obj.get("confidence", 0)
                lines.append(
                    f"- {cls} (id={obj_id}, {direction}, {range_str}, "
                    f"conf={conf:.2f})"
                )

        # VLM scene summary (Ch04 vlm_client는 "scene_summary" 키로 publish)
        vlm = data.get("vlm_scene", {})
        vlm_desc = vlm.get("scene_summary")
        if vlm_desc:
            lines.append(f"- VLM: {vlm_desc}")

        # [Social Navigation] 섹션: social_hints 전체 필드 변환
        hints = vlm.get("social_hints", [])
        if hints:
            lines.append("")
            lines.append("[Social Navigation]")
            for hint in hints:
                hint_type = hint.get("type", "unknown")
                confidence = hint.get("confidence", 0)
                reason = hint.get("reason", "")
                side = hint.get("side")
                offset_m = hint.get("offset_m")

                parts = [f"{hint_type} (confidence {confidence:.2f}"]
                if reason:
                    parts[0] += f", reason: {reason}"
                parts[0] += ")"

                detail = ""
                if side:
                    detail += f" {side}"
                if offset_m is not None:
                    detail += f" {offset_m:.1f}m"

                desc = _social_hint_description(hint_type)
                lines.append(f"- {parts[0]}:{detail} {desc}")

        return "\n".join(lines)


def _social_hint_description(hint_type: str) -> str:
    """social_hints type -> 한국어 설명."""
    descriptions = {
        "avoid_between_people": "두 사람 사이 통과 금지",
        "prefer_side_pass": "우회 권장",
        "slow_down": "감속 권장",
        "clear_path": "경로 확보됨 (통과 가능)",
    }
    return descriptions.get(hint_type, hint_type)
