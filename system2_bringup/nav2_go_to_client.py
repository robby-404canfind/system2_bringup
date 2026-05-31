"""nav2_go_to_client.py — Ch02 Nav2Navigator + exec_go_to adapter (Ch05 신규).

Ch02의 Nav2Navigator와 exec_go_to()를 import하여,
ActionDispatcher가 기대하는 exec_go_to(location) -> bool 인터페이스를 제공합니다.
"""
import time
from typing import Any, Dict

from rclpy.node import Node

from social_nav_bringup.nav2_navigator import Nav2Navigator
from social_nav_bringup.go_to_node import exec_go_to


class Nav2GoToClient:
    """Ch02 Nav2Navigator + exec_go_to를 ActionDispatcher 인터페이스로 래핑.

    Ch03에서는 nav2_navigator=None으로 시뮬레이션 모드였습니다.
    Ch05에서는 이 클래스를 주입하여 실제 Nav2 이동을 수행합니다.
    """

    def __init__(
        self,
        node: Node,
        semantic_locations: Dict[str, Dict[str, float]],
        patrol_routes: Dict[str, list] | None = None,
    ):
        self._node = node
        self._semantic_locations = semantic_locations
        self._patrol_routes = patrol_routes or {}
        self._nav_feedback: Dict[str, Any] = {
            "distance_remaining": None,
            "stamp": 0.0,
        }
        self._navigator = Nav2Navigator(
            node, feedback_cb=self._nav_feedback.update
        )

    def exec_go_to(self, location: str) -> bool:
        """시맨틱 위치 이름 -> Nav2 Goal 전송 + stuck 감지.

        Args:
            location: semantic_locations에 정의된 위치 이름

        Returns:
            True(도착) / False(실패)
        """
        if location not in self._semantic_locations:
            self._node.get_logger().error(
                f"[Nav2GoToClient] Unknown location: '{location}'. "
                f"사용 가능: {list(self._semantic_locations.keys())}"
            )
            return False

        goal = self._semantic_locations[location]
        self._node.get_logger().info(
            f"[Nav2GoToClient] go_to('{location}') -> "
            f"({goal.get('x', 0):.2f}, {goal.get('y', 0):.2f})"
        )

        # Ch02 exec_go_to 함수 호출 (stuck detection 포함)
        self._nav_feedback["distance_remaining"] = None
        return exec_go_to(
            self._node, self._navigator, self._nav_feedback, goal
        )

    def exec_patrol(self, area: str, duration: int) -> bool:
        """patrol route의 waypoint를 duration(초) 동안 순환 방문.

        Args:
            area: patrol_routes에 정의된 route ID
            duration: 순환 제한 시간 (초)

        Returns:
            True(정상 종료) / False(실패)
        """
        waypoints = self._patrol_routes.get(area)
        if not waypoints:
            self._node.get_logger().error(
                f"[Nav2GoToClient] Unknown patrol route: '{area}'. "
                f"사용 가능: {list(self._patrol_routes.keys())}"
            )
            return False

        self._node.get_logger().info(
            f"[Nav2GoToClient] patrol('{area}', {duration}s) 시작: "
            f"waypoints={waypoints}"
        )

        start = time.time()
        wp_idx = 0
        while (time.time() - start) < duration:
            location = waypoints[wp_idx % len(waypoints)]
            self._node.get_logger().info(
                f"[Nav2GoToClient] patrol waypoint {wp_idx}: '{location}'"
            )
            success = self.exec_go_to(location)
            if not success:
                self._node.get_logger().warn(
                    f"[Nav2GoToClient] patrol waypoint '{location}' 실패, "
                    "다음 waypoint로 진행"
                )
            wp_idx += 1

        elapsed = time.time() - start
        self._node.get_logger().info(
            f"[Nav2GoToClient] patrol('{area}') 완료: "
            f"{wp_idx}개 waypoint 방문, {elapsed:.0f}초 소요"
        )
        return True

    def cancel(self):
        """현재 Nav2 Goal을 취소합니다."""
        self._navigator.cancel_all()
