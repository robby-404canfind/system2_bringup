"""system2_planner_node.py — System2 통합 ROS2 노드."""
from pathlib import Path
from threading import Thread
from uuid import uuid4

import yaml
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from .action_dispatcher import ActionDispatcher
from .context_builder import ContextBuilder
from .llm_client import LLMClient
from .plan_generator import generate_and_validate
from .plan_models import HighLevelPlan
from .schema_validator import SchemaValidator


class System2PlannerNode(Node):
    """System2 LLM Planner — 자연어 → Plan → 실행 파이프라인."""

    def __init__(self):
        super().__init__("system2_planner")

        self.declare_parameter("config_dir", "")
        # 비어 있으면 llm_config.yaml의 기본값을 사용하고,
        # 값이 지정되면 ROS parameter가 override합니다.
        self.declare_parameter("backend", "")
        self.declare_parameter("model", "")

        config_dir = Path(
            self.get_parameter("config_dir").value
            or str(Path(__file__).parent.parent / "config")
        )

        loc_file = config_dir / "semantic_locations.yaml"
        with open(loc_file) as f:
            loc_data = yaml.safe_load(f) or {}
        self.semantic_locations = loc_data.get("locations", {})
        self.location_names = list(self.semantic_locations.keys())

        route_file = config_dir / "patrol_routes.yaml"
        if route_file.exists():
            with open(route_file) as f:
                route_data = yaml.safe_load(f) or {}
            self.patrol_route_names = list((route_data.get("routes") or {}).keys())
        else:
            self.patrol_route_names = ["office_loop", "lobby_loop"]

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

        self.status_pub = self.create_publisher(String, "/system2/status", 10)
        self.report_pub = self.create_publisher(String, "/system2/report", 10)
        self.plan_pub = self.create_publisher(String, "/system2/plan", 10)
        self.result_pub = self.create_publisher(
            String, "/system2/mission_result", 10
        )

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
        self.dispatcher = ActionDispatcher(
            nav2_navigator=None,
            status_callback=lambda msg: self.status_pub.publish(String(data=msg)),
            report_callback=lambda msg: self.report_pub.publish(String(data=msg)),
        )
        self.context_builder = ContextBuilder(
            semantic_locations=self.semantic_locations
        )

        self.command_sub = self.create_subscription(
            String, "/system2/user_command", self.handle_command_msg, 10
        )

        self._executor_thread = None

        self.get_logger().info(
            f"System2 Planner 초기화 완료 (backend={backend}, model={model})"
        )

    def handle_command_msg(self, msg: String):
        """Topic으로 명령을 수신합니다."""
        command = msg.data
        self.get_logger().info(f"명령 수신: '{command}'")

        if self._executor_thread and self._executor_thread.is_alive():
            self.get_logger().warn("이전 미션 실행 중 — 명령 거부")
            self.status_pub.publish(String(data="rejected: previous mission running"))
            return

        # 새 top-level 명령 planning에서는 이전 미션의 실행 이력을 섞지 않습니다.
        # (현재 위치 등 장기 상태는 ContextBuilder 내부에 유지됨)
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
                result = self.dispatcher.dispatch(step)
                if result.success:
                    self.context_builder.record_success(step, result)
                    break
                self.context_builder.record_failure(step, result, attempt)
                self.get_logger().warn(
                    f"Step {i} 실패 (시도 {attempt + 1}/{step.retry + 1}): "
                    f"{result.message}"
                )
            else:
                if replan_depth >= 1:
                    self.get_logger().error("Replan 깊이 초과 → 미션 종료")
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
                    self.result_pub.publish(
                        String(data=f"mission_failed: {plan.mission_id}")
                    )
                return

        self.result_pub.publish(String(data=f"mission_completed: {plan.mission_id}"))
        self.get_logger().info(f"미션 완료: {plan.mission_id} ({plan.intent})")


def main():
    rclpy.init()
    node = System2PlannerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()
