"""action_dispatcher.py — 검증된 Plan Step을 Unit Action으로 디스패치 (Ch05 확장).

Ch03 대비 변경:
- find/scan/follow/assess_scene/resolve_target 핸들러 추가 (ActionClient 경유 /system1/*)
- follow_query composite 핸들러 추가 (resolve_target 후 follow)
- patrol 실제 구현 (Nav2GoToClient 경유)
- ROS2 node 참조 + ActionClient 인스턴스 보유
- max_duration_sec: go_to/wait에만 적용, Perception Action은 Goal params에 위임

Perception ActionServer cancel 미지원 주의:
  find/scan/follow/assess_scene/resolve_target는 cancel_callback 미등록,
  exec_*() 내부에 취소 플래그 없음.
  상위에서 threading timeout으로 중단하면 로봇이 /cmd_vel을 계속 publish할 수 있음.
  Perception Action은 Goal의 자체 timeout에 위임하며
  max_duration_sec는 적용하지 않음.
"""
import time
from threading import Thread
from uuid import uuid4

import rclpy

from .plan_models import (
    ActionResult,
    AssessSceneStep,
    FindStep,
    FollowParams,
    FollowQueryStep,
    FollowStep,
    GoToStep,
    PatrolStep,
    ReportStep,
    ResolveTargetStep,
    ScanStep,
    Step,
    WaitStep,
)


class ActionDispatcher:
    """Step.task를 대응하는 Unit Action 핸들러로 디스패치합니다."""

    def __init__(
        self,
        nav2_navigator=None,
        node=None,
        find_client=None,
        scan_client=None,
        follow_client=None,
        assess_scene_client=None,
        resolve_target_client=None,
        status_callback=None,
        report_callback=None,
        snapshot_callback=None,
    ):
        self.nav = nav2_navigator
        self._node = node
        self._find_client = find_client
        self._scan_client = scan_client
        self._follow_client = follow_client
        self._assess_scene_client = assess_scene_client
        self._resolve_target_client = resolve_target_client
        self.status_cb = status_callback or (lambda msg: print(f"[status] {msg}"))
        self.report_cb = report_callback or self.status_cb
        self.snapshot_cb = snapshot_callback
        self._last_assessment_message = ""
        self._last_assessment_json = ""
        self._last_target_message = ""
        self._last_target_id = -1

        self._handlers = {
            "go_to": self._exec_go_to,
            "patrol": self._exec_patrol,
            "wait": self._exec_wait,
            "report": self._exec_report,
            "find": self._exec_find,
            "scan": self._exec_scan,
            "follow": self._exec_follow,
            "assess_scene": self._exec_assess_scene,
            "resolve_target": self._exec_resolve_target,
            "follow_query": self._exec_follow_query,
        }

        # 현재 실행 중인 미션 ID (dispatch 호출 시 갱신)
        self._current_mission_id: str = ""

    def dispatch(self, step: Step, mission_id: str = "") -> ActionResult:
        """Step을 실행하고 결과를 반환합니다.

        Args:
            step: 실행할 Step.
            mission_id: 상위 미션 ID. Perception Action Goal의 mission_id 필드에 주입됩니다.
        """
        handler = self._handlers.get(step.task)
        if handler is None:
            return ActionResult(success=False, message=f"Unknown task: {step.task}")
        self._current_mission_id = mission_id
        self.status_cb(f"executing: {step.task}({step.params.model_dump()})")
        start = time.time()
        result = handler(step)
        result.elapsed_sec = time.time() - start
        return result

    # ---- Ch03 기존 핸들러 ----

    def _exec_go_to(self, step: GoToStep) -> ActionResult:
        location = step.params.location
        if self.nav is None:
            return ActionResult(success=True, message=f"[sim] go_to({location}) done")

        max_dur = step.max_duration_sec
        result_container: list[ActionResult] = []

        def _run():
            try:
                success = self.nav.exec_go_to(location)
                result_container.append(
                    ActionResult(
                        success=success,
                        message=f"go_to({location}) {'성공' if success else '실패'}",
                    )
                )
            except Exception as e:
                result_container.append(
                    ActionResult(success=False, message=f"go_to({location}) 에러: {e}")
                )

        if max_dur is None:
            _run()
            return result_container[0] if result_container else ActionResult(
                success=False, message=f"go_to({location}) 결과 없음"
            )

        # max_duration_sec 적용: Nav2는 cancel 지원
        t = Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=max_dur)

        if t.is_alive():
            self.nav.cancel()
            t.join(timeout=5.0)
            return ActionResult(
                success=False,
                message=f"go_to({location}) max_duration_sec={max_dur}s 초과 → cancel",
            )

        return result_container[0] if result_container else ActionResult(
            success=False, message=f"go_to({location}) 결과 없음"
        )

    def _exec_patrol(self, step: PatrolStep) -> ActionResult:
        area = step.params.area
        duration = step.params.duration
        max_dur = step.max_duration_sec
        if self.nav is None:
            return ActionResult(
                success=True,
                message=f"[sim] patrol({area}, {duration}s) done",
            )

        # patrol duration 자체가 timeout 역할을 하지만
        # max_duration_sec가 더 짧으면 그 값으로 제한
        effective_dur = min(duration, int(max_dur)) if max_dur is not None else duration

        result_container: list[ActionResult] = []

        def _run():
            try:
                success = self.nav.exec_patrol(area, effective_dur)
                result_container.append(
                    ActionResult(
                        success=success,
                        message=f"patrol({area}, {effective_dur}s) "
                        f"{'완료' if success else '실패'}",
                    )
                )
            except Exception as e:
                result_container.append(
                    ActionResult(success=False, message=f"patrol({area}) 에러: {e}")
                )

        if max_dur is None:
            _run()
            return result_container[0] if result_container else ActionResult(
                success=False, message=f"patrol({area}) 결과 없음"
            )

        # max_duration_sec 적용: Nav2는 cancel 지원
        t = Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=max_dur)

        if t.is_alive():
            self.nav.cancel()
            t.join(timeout=5.0)
            return ActionResult(
                success=False,
                message=f"patrol({area}) max_duration_sec={max_dur}s 초과 → cancel",
            )

        return result_container[0] if result_container else ActionResult(
            success=False, message=f"patrol({area}) 결과 없음"
        )

    def _exec_wait(self, step: WaitStep) -> ActionResult:
        seconds = step.params.seconds
        max_dur = step.max_duration_sec
        actual = min(seconds, max_dur) if max_dur is not None else seconds
        self.status_cb(f"waiting {actual}s...")
        time.sleep(actual)
        if max_dur is not None and seconds > max_dur:
            return ActionResult(
                success=True,
                message=f"wait({seconds}s) max_duration_sec={max_dur}s로 제한됨",
            )
        return ActionResult(success=True, message=f"wait({actual}s) 완료")

    def _exec_report(self, step: ReportStep) -> ActionResult:
        status = step.params.status
        if status in {"latest_assessment", "assessment_result"}:
            status = self._last_assessment_message or "아직 장면 평가 결과가 없습니다."
        elif status in {"latest_target", "target_result"}:
            status = self._last_target_message or "아직 대상 식별 결과가 없습니다."
        report_text = status
        if self.snapshot_cb is not None:
            snapshot = self.snapshot_cb(
                reason="report",
                message=report_text,
                mission_id=self._current_mission_id,
            )
            snapshot_text = self._format_snapshot_for_report(snapshot)
            if snapshot_text:
                report_text = f"{report_text}\n{snapshot_text}"
        self.report_cb(report_text)
        return ActionResult(success=True, message=f"report({status}) publish")

    @staticmethod
    def _format_snapshot_for_report(snapshot: dict) -> str:
        if not isinstance(snapshot, dict) or not snapshot:
            return ""
        saved_files = snapshot.get("saved_files") or {}
        if not isinstance(saved_files, dict) or not saved_files:
            return ""
        parts = ["snapshot:"]
        for key in ("debug", "raw", "metadata"):
            value = saved_files.get(key)
            if value:
                parts.append(f"{key}={value}")
        return " ".join(parts)

    # ---- Ch05 추가: Perception Action 핸들러 ----

    def _exec_find(self, step: FindStep) -> ActionResult:
        """ActionClient로 /system1/find Goal 전송. timeout은 Goal params에 위임."""
        if self._find_client is None or self._node is None:
            return ActionResult(
                success=True,
                message=f"[sim] find({step.params.target_class}) done",
            )
        try:
            from system_interfaces.action import Find

            goal = Find.Goal()
            goal.request_id = f"req-{uuid4().hex[:8]}"
            goal.mission_id = self._current_mission_id
            goal.target_class = step.params.target_class
            goal.timeout_sec = step.params.timeout_sec
            goal.sweep_deg = step.params.sweep_deg

            def _on_feedback(fb_msg):
                fb = fb_msg.feedback
                self.status_cb(
                    f"find feedback: state={fb.state} detail={fb.detail} "
                    f"elapsed={fb.elapsed_sec:.1f}s"
                )

            return self._send_action_goal(
                self._find_client, goal, "find", feedback_callback=_on_feedback
            )
        except Exception as e:
            return ActionResult(success=False, message=f"find 에러: {e}")

    def _exec_scan(self, step: ScanStep) -> ActionResult:
        """ActionClient로 /system1/scan Goal 전송. timeout은 Goal params에 위임."""
        if self._scan_client is None or self._node is None:
            return ActionResult(
                success=True,
                message="[sim] scan(all_objects) done",
            )
        try:
            from system_interfaces.action import Scan

            goal = Scan.Goal()
            goal.request_id = f"req-{uuid4().hex[:8]}"
            goal.mission_id = self._current_mission_id
            goal.duration_sec = step.params.duration_sec
            goal.sweep_deg = step.params.sweep_deg

            def _on_feedback(fb_msg):
                fb = fb_msg.feedback
                self.status_cb(
                    f"scan feedback: state={fb.state} detail={fb.detail} "
                    f"elapsed={fb.elapsed_sec:.1f}s found={fb.objects_found}"
                )

            return self._send_action_goal(
                self._scan_client, goal, "scan", feedback_callback=_on_feedback
            )
        except Exception as e:
            return ActionResult(success=False, message=f"scan 에러: {e}")

    def _exec_follow(self, step: FollowStep) -> ActionResult:
        """ActionClient로 /system1/follow Goal 전송. timeout은 Goal params에 위임."""
        if self._follow_client is None or self._node is None:
            return ActionResult(
                success=True,
                message=f"[sim] follow({step.params.target_class}) done",
            )
        try:
            from system_interfaces.action import Follow

            goal = Follow.Goal()
            goal.request_id = f"req-{uuid4().hex[:8]}"
            goal.mission_id = self._current_mission_id
            goal.target_class = step.params.target_class
            goal.target_id = step.params.target_id
            goal.target_distance_m = step.params.target_distance_m
            goal.max_time_sec = step.params.max_time_sec

            def _on_feedback(fb_msg):
                fb = fb_msg.feedback
                self.status_cb(
                    f"follow feedback: state={fb.state} status={fb.target_status} "
                    f"dist={fb.current_distance_m:.2f}m elapsed={fb.elapsed_sec:.1f}s"
                )

            return self._send_action_goal(
                self._follow_client, goal, "follow", feedback_callback=_on_feedback
            )
        except Exception as e:
            return ActionResult(success=False, message=f"follow 에러: {e}")

    def _exec_assess_scene(self, step: AssessSceneStep) -> ActionResult:
        """ActionClient로 /system1/assess_scene Goal 전송."""
        if self._assess_scene_client is None or self._node is None:
            self._last_assessment_message = (
                f"[sim] assess_scene({step.params.query}) done"
            )
            return ActionResult(success=True, message=self._last_assessment_message)
        try:
            from system_interfaces.action import AssessScene

            goal = AssessScene.Goal()
            goal.request_id = f"req-{uuid4().hex[:8]}"
            goal.mission_id = self._current_mission_id
            goal.query = step.params.query
            goal.timeout_sec = step.params.timeout_sec

            def _on_feedback(fb_msg):
                fb = fb_msg.feedback
                self.status_cb(
                    f"assess_scene feedback: state={fb.state} detail={fb.detail} "
                    f"elapsed={fb.elapsed_sec:.1f}s"
                )

            def _handle_result(result):
                success = getattr(result, "success", False)
                message = getattr(result, "message", "")
                assessment_json = getattr(result, "assessment_json", "")
                self._last_assessment_message = message
                self._last_assessment_json = assessment_json
                return ActionResult(success=success, message=message)

            return self._send_action_goal(
                self._assess_scene_client,
                goal,
                "assess_scene",
                feedback_callback=_on_feedback,
                result_handler=_handle_result,
            )
        except Exception as e:
            return ActionResult(success=False, message=f"assess_scene 에러: {e}")

    def _exec_resolve_target(self, step: ResolveTargetStep) -> ActionResult:
        """ActionClient로 /system1/resolve_target Goal 전송."""
        return self._send_resolve_target(
            target_query=step.params.target_query,
            timeout_sec=step.params.timeout_sec,
        )

    def _exec_follow_query(self, step: FollowQueryStep) -> ActionResult:
        """target_query를 track id로 해석한 뒤 기존 follow Action을 실행."""
        resolve_result = self._send_resolve_target(
            target_query=step.params.target_query,
            timeout_sec=step.params.resolve_timeout_sec,
        )
        if not resolve_result.success:
            return resolve_result

        follow_step = FollowStep(
            task="follow",
            params=FollowParams(
                target_class="person",
                target_id=self._last_target_id,
                target_distance_m=step.params.target_distance_m,
                max_time_sec=step.params.max_time_sec,
            ),
            retry=step.retry,
            max_duration_sec=step.max_duration_sec,
        )
        follow_result = self._exec_follow(follow_step)
        follow_result.message = (
            f"{resolve_result.message}; {follow_result.message}"
        )
        return follow_result

    def _send_resolve_target(
        self,
        target_query: str,
        timeout_sec: float,
    ) -> ActionResult:
        if self._resolve_target_client is None or self._node is None:
            self._last_target_id = -1
            self._last_target_message = f"[sim] resolve_target({target_query}) done"
            return ActionResult(success=True, message=self._last_target_message)
        try:
            from system_interfaces.action import ResolveTarget

            goal = ResolveTarget.Goal()
            goal.request_id = f"req-{uuid4().hex[:8]}"
            goal.mission_id = self._current_mission_id
            goal.target_query = target_query
            goal.timeout_sec = timeout_sec

            def _on_feedback(fb_msg):
                fb = fb_msg.feedback
                self.status_cb(
                    f"resolve_target feedback: state={fb.state} detail={fb.detail} "
                    f"elapsed={fb.elapsed_sec:.1f}s"
                )

            def _handle_result(result):
                success = getattr(result, "success", False)
                message = getattr(result, "message", "")
                self._last_target_id = int(getattr(result, "target_id", -1))
                self._last_target_message = message
                return ActionResult(success=success, message=message)

            return self._send_action_goal(
                self._resolve_target_client,
                goal,
                "resolve_target",
                feedback_callback=_on_feedback,
                result_handler=_handle_result,
            )
        except Exception as e:
            return ActionResult(success=False, message=f"resolve_target 에러: {e}")

    # ---- 공통 ActionClient 헬퍼 ----

    def _send_action_goal(
        self,
        client,
        goal,
        action_name: str,
        feedback_callback=None,
        result_handler=None,
    ) -> ActionResult:
        """ActionClient Goal 전송 + polling 대기 (cancel 없이 완료 대기).

        Perception ActionServer가 cancel을 지원하지 않으므로,
        Goal 전송 후 ActionServer 내부 timeout으로 종료될 때까지 대기합니다.

        Args:
            feedback_callback: 서버로부터 중간 Feedback을 받을 때 호출.
                rclpy Action API가 `feedback_msg.feedback`으로 원본을 전달합니다.
        """
        node = self._node

        # Action Server 연결 대기
        if not client.wait_for_server(timeout_sec=5.0):
            return ActionResult(
                success=False,
                message=f"/system1/{action_name} 서버 연결 실패",
            )

        # Goal 비동기 전송 (feedback_callback 연결)
        send_future = client.send_goal_async(
            goal, feedback_callback=feedback_callback
        )
        while rclpy.ok() and not send_future.done():
            time.sleep(0.01)

        if not rclpy.ok():
            return ActionResult(success=False, message="rclpy 종료")

        goal_handle = send_future.result()
        if not goal_handle or not goal_handle.accepted:
            return ActionResult(
                success=False,
                message=f"/system1/{action_name} Goal 거부",
            )

        node.get_logger().info(f"[Dispatcher] /system1/{action_name} Goal 수락됨")

        # 결과 대기 (ActionServer 내부 timeout에 위임)
        result_future = goal_handle.get_result_async()
        while rclpy.ok() and not result_future.done():
            time.sleep(0.2)

        if not rclpy.ok():
            return ActionResult(success=False, message="rclpy 종료")

        try:
            result = result_future.result().result
            if result_handler is not None:
                handled = result_handler(result)
                node.get_logger().info(
                    f"[Dispatcher] /system1/{action_name} 완료: "
                    f"success={handled.success}, message={handled.message}"
                )
                return handled
            success = getattr(result, "success", False)
            message = getattr(result, "message", "")
            node.get_logger().info(
                f"[Dispatcher] /system1/{action_name} 완료: "
                f"success={success}, message={message}"
            )
            return ActionResult(success=success, message=message)
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"/system1/{action_name} 결과 처리 에러: {e}",
            )
