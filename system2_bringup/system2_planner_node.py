"""system2_planner_node.py — System2 통합 ROS2 노드 (Ch05 확장).

Ch03 대비 변경:
- /perception/context/raw 구독 -> ContextBuilder.update_perception()
- /amcl_pose 구독 -> ContextBuilder._robot_pose 업데이트
- Nav2GoToClient 생성 (Ch02 Nav2Navigator import)
- ActionClient 생성 (/system1/find, /system1/scan, /system1/follow,
  /system1/assess_scene, /system1/resolve_target)
- ActionDispatcher에 node, find/scan/follow client 전달
- go_home fallback: replan 실패 시 안전 위치로 복귀
- patrol_routes를 waypoint 리스트까지 로드 (Nav2GoToClient.exec_patrol 용)
"""
from pathlib import Path
from threading import Thread
from uuid import uuid4

import yaml
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from std_msgs.msg import String
from geometry_msgs.msg import PoseWithCovarianceStamped

from system_interfaces.action import AssessScene, Find, Follow, ResolveTarget, Scan

from .action_dispatcher import ActionDispatcher
from .context_builder import ContextBuilder
from .llm_client import LLMClient
from .nav2_go_to_client import Nav2GoToClient
from .plan_generator import generate_and_validate
from .plan_models import HighLevelPlan
from .schema_validator import SchemaValidator


class System2PlannerNode(Node):
    """System2 LLM Planner — 자연어 -> Plan -> 실행 파이프라인 (Ch05).

    Ch03 구조를 유지하면서 Perception + Nav2 통합을 추가합니다.
    """

    def __init__(self):
        super().__init__("system2_planner")

        # ---- ROS2 파라미터 ----
        self.declare_parameter("config_dir", "")
        self.declare_parameter("backend", "")
        self.declare_parameter("model", "")
        self.declare_parameter("go_home_location", "charging_station")

        # ---- Config 로드 ----
        config_dir = Path(
            self.get_parameter("config_dir").value
            or str(Path(__file__).parent.parent / "config")
        )

        # Semantic Locations: Ch05 hall 환경의 단일 기준 파일
        loc_file = config_dir / "semantic_locations.hall.yaml"
        with open(loc_file) as f:
            loc_data = yaml.safe_load(f) or {}
        self.semantic_locations = loc_data.get("locations", {})
        self.location_names = list(self.semantic_locations.keys())

        # Patrol Routes (waypoint 리스트까지 로드)
        route_file = config_dir / "patrol_routes.yaml"
        if route_file.exists():
            with open(route_file) as f:
                route_data = yaml.safe_load(f) or {}
            self.patrol_routes = route_data.get("routes") or {}
        else:
            self.patrol_routes = {
                "hall_loop": [
                    "office_entrance",
                    "cabinet",
                    "workstation",
                    "pallet",
                    "fire_extinguisher",
                    "charging_station",
                ],
            }
        self.patrol_route_names = list(self.patrol_routes.keys())

        # LLM config
        llm_cfg_file = config_dir / "llm_config.yaml"
        llm_cfg = {}
        if llm_cfg_file.exists():
            with open(llm_cfg_file) as f:
                llm_cfg = yaml.safe_load(f) or {}

        backend_override = self.get_parameter("backend").value
        model_override = self.get_parameter("model").value

        default_backend = llm_cfg.get("default_backend", "ollama")
        backends_cfg = llm_cfg.get("backends", {}) or {}
        backend = backend_override or default_backend
        backend_cfg = backends_cfg.get(backend, {}) or {}
        model = model_override or backend_cfg.get(
            "model",
            "qwen2.5:7b" if backend == "ollama" else "openai/gpt-oss-120b:free",
        )
        timeout = float(backend_cfg.get("timeout", 10.0))
        max_retries = int(backend_cfg.get("max_retries", 1))
        supports_tools = backend_cfg.get("supports_tools", None)
        supports_structured_output = bool(
            backend_cfg.get("supports_structured_output", False)
        )

        # ---- Publishers (Ch03 동일) ----
        self.status_pub = self.create_publisher(String, "/system2/status", 10)
        self.report_pub = self.create_publisher(String, "/system2/report", 10)
        self.plan_pub = self.create_publisher(String, "/system2/plan", 10)
        self.result_pub = self.create_publisher(
            String, "/system2/mission_result", 10
        )

        # ---- LLM Client + Validator (Ch03 동일) ----
        self.llm_client = LLMClient(
            backend=backend,
            model=model,
            timeout=timeout,
            max_retries=max_retries,
            supports_tools=supports_tools,
            supports_structured_output=supports_structured_output,
        )
        self.validator = SchemaValidator(
            self.location_names,
            self.patrol_route_names,
        )

        # ---- Ch05: Nav2 통합 ----
        self.nav_client = Nav2GoToClient(
            self, self.semantic_locations, self.patrol_routes
        )

        # ---- Ch05: Perception ActionClient ----
        self._find_client = ActionClient(self, Find, "/system1/find")
        self._scan_client = ActionClient(self, Scan, "/system1/scan")
        self._follow_client = ActionClient(self, Follow, "/system1/follow")
        self._assess_scene_client = ActionClient(
            self, AssessScene, "/system1/assess_scene"
        )
        self._resolve_target_client = ActionClient(
            self, ResolveTarget, "/system1/resolve_target"
        )

        # ---- Dispatcher (Ch03 확장) ----
        self.dispatcher = ActionDispatcher(
            nav2_navigator=self.nav_client,
            node=self,
            find_client=self._find_client,
            scan_client=self._scan_client,
            follow_client=self._follow_client,
            assess_scene_client=self._assess_scene_client,
            resolve_target_client=self._resolve_target_client,
            status_callback=lambda msg: self.status_pub.publish(String(data=msg)),
            report_callback=lambda msg: self.report_pub.publish(String(data=msg)),
        )

        # ---- Context Builder (Ch03 확장) ----
        self.context_builder = ContextBuilder(
            semantic_locations=self.semantic_locations
        )

        # ---- Ch05: Perception 구독 ----
        self.perception_sub = self.create_subscription(
            String, "/perception/context/raw", self._perception_cb, 10
        )

        # ---- Ch05: AMCL Pose 구독 ----
        self.amcl_sub = self.create_subscription(
            PoseWithCovarianceStamped, "/amcl_pose", self._amcl_cb, 10
        )

        # ---- Command 구독 (Ch03 동일) ----
        self.command_sub = self.create_subscription(
            String, "/system2/user_command", self.handle_command_msg, 10
        )

        self._executor_thread = None

        self.get_logger().info(
            f"System2 Planner 초기화 완료 (backend={backend}, model={model}), "
            f"locations={self.location_names}, "
            f"patrol_routes={self.patrol_route_names}"
        )

    # ---- Ch05: 콜백 ----

    def _perception_cb(self, msg: String):
        """Perception context 업데이트."""
        self.context_builder.update_perception(msg.data)

    def _amcl_cb(self, msg: PoseWithCovarianceStamped):
        """AMCL pose -> ContextBuilder 위치 업데이트."""
        pos = msg.pose.pose.position
        self.context_builder._robot_pose = (pos.x, pos.y)

    # ---- Command 처리 (Ch03 동일 구조) ----

    def handle_command_msg(self, msg: String):
        """Topic으로 명령을 수신합니다."""
        command = msg.data
        self.get_logger().info(f"명령 수신: '{command}'")

        if self._executor_thread and self._executor_thread.is_alive():
            self.get_logger().warn("이전 미션 실행 중 -- 명령 거부")
            self.status_pub.publish(String(data="rejected: previous mission running"))
            return

        # 새 top-level 명령 planning에서는 이전 미션의 실행 이력을 섞지 않습니다.
        # 현재 위치/Perception context는 유지하고, 실행 이력/진행 카운터만 초기화합니다.
        self.context_builder.reset_mission_state()

        context = self.context_builder.build()
        mission_id = f"cmd-{uuid4().hex[:8]}"

        try:
            plan = generate_and_validate(
                self.llm_client,
                command,
                self.location_names,
                self.patrol_route_names,
                mission_id=mission_id,
                validator=self.validator,
                context=context,
            )
        except Exception as e:
            self.get_logger().error(f"Plan 생성 실패: {e}")
            self.status_pub.publish(String(data=f"plan_failed: {e}"))
            return

        self.plan_pub.publish(String(data=plan.model_dump_json()))
        self.get_logger().info(f"Plan 생성 완료: {plan.intent}")

        self._executor_thread = Thread(
            target=self._execute_plan,
            args=(plan,),
            daemon=True,
        )
        self._executor_thread.start()

    # ---- Plan 실행 (Ch03 구조 + go_home fallback) ----

    def _execute_plan(self, plan: HighLevelPlan, replan_depth: int = 0):
        """백그라운드에서 Step을 순차 실행합니다."""
        self.status_pub.publish(String(data=f"mission_start: {plan.mission_id}"))
        self.context_builder.start_mission(len(plan.steps))

        for i, step in enumerate(plan.steps):
            self.status_pub.publish(
                String(
                    data=f"executing step {i}/{len(plan.steps)}: "
                    f"{step.task}({step.params})"
                )
            )

            result = None
            for attempt in range(step.retry + 1):
                result = self.dispatcher.dispatch(step, mission_id=plan.mission_id)
                if result.success:
                    self.context_builder.record_success(step, result)
                    break
                self.context_builder.record_failure(step, result, attempt)
                self.get_logger().warn(
                    f"Step {i} 실패 (시도 {attempt + 1}/{step.retry + 1}): "
                    f"{result.message}"
                )
            else:
                # retry 모두 실패 -> replan 시도
                if replan_depth >= 1:
                    self.get_logger().error(
                        "Replan 깊이 초과 -> go_home fallback"
                    )
                    self._go_home()
                    self.result_pub.publish(
                        String(data=f"mission_failed: {plan.mission_id}")
                    )
                    return

                self.status_pub.publish(String(data="replanning..."))
                self.get_logger().info("Replan 시작...")
                replan_context = self.context_builder.build_replan_context(
                    step, result
                )
                try:
                    new_plan = generate_and_validate(
                        self.llm_client,
                        replan_context,
                        self.location_names,
                        self.patrol_route_names,
                        mission_id=plan.mission_id,
                        validator=self.validator,
                    )
                    self._execute_plan(new_plan, replan_depth + 1)
                except Exception as e:
                    self.get_logger().error(f"Replan 실패: {e}")
                    self._go_home()
                    self.result_pub.publish(
                        String(data=f"mission_failed: {plan.mission_id}")
                    )
                return

        self.result_pub.publish(String(data=f"mission_completed: {plan.mission_id}"))
        self.get_logger().info(f"미션 완료: {plan.mission_id} ({plan.intent})")

    # ---- Ch05: go_home fallback ----

    def _go_home(self):
        """모든 전략 실패 시 안전 위치로 복귀."""
        home = self.get_parameter("go_home_location").value
        self.get_logger().warn(f"go_home 실행: '{home}'")
        self.status_pub.publish(String(data=f"go_home: {home}"))
        try:
            success = self.nav_client.exec_go_to(home)
            if success:
                self.get_logger().info(f"go_home('{home}') 완료")
            else:
                self.get_logger().error(f"go_home('{home}') 실패")
        except Exception as e:
            self.get_logger().error(f"go_home('{home}') 에러: {e}")


def main():
    rclpy.init()
    node = System2PlannerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()
