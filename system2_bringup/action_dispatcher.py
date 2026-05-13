"""action_dispatcher.py — 검증된 Plan Step을 Unit Action으로 디스패치."""
import time
from typing import Callable, Optional

from .plan_models import (
    ActionResult,
    GoToStep,
    PatrolStep,
    ReportStep,
    Step,
    WaitStep,
)
from .report_node import exec_report
from .wait_node import exec_wait


class ActionDispatcher:
    """Step.task를 대응하는 Unit Action 핸들러로 디스패치합니다.

    Ch03 기본 경로는 시뮬레이션 모드입니다. 실제 go_to/patrol 연동이 필요할 때는
    adapter 형태의 executor(callable)를 주입합니다.
    """

    def __init__(
        self,
        nav2_navigator=None,
        go_to_executor: Optional[Callable[[str], bool]] = None,
        patrol_executor: Optional[Callable[[str, int], bool]] = None,
        status_callback=None,
        report_callback=None,
    ):
        self.nav = nav2_navigator
        self.go_to_executor = go_to_executor or getattr(nav2_navigator, "exec_go_to", None)
        self.patrol_executor = patrol_executor or getattr(nav2_navigator, "exec_patrol", None)
        self.status_cb = status_callback or (lambda msg: print(f"[status] {msg}"))
        self.report_cb = report_callback or self.status_cb

        self._handlers = {
            "go_to": self._exec_go_to,
            "patrol": self._exec_patrol,
            "wait": self._exec_wait,
            "report": self._exec_report,
        }

    def dispatch(self, step: Step) -> ActionResult:
        """Step을 실행하고 결과를 반환합니다."""
        handler = self._handlers.get(step.task)
        if handler is None:
            return ActionResult(success=False, message=f"Unknown task: {step.task}")
        self.status_cb(f"executing: {step.task}({step.params.model_dump()})")
        start = time.time()
        result = handler(step)
        result.elapsed_sec = time.time() - start
        return result

    def _exec_go_to(self, step: GoToStep) -> ActionResult:
        location = step.params.location
        if self.go_to_executor is None:
            return ActionResult(success=True, message=f"[sim] go_to({location}) done")
        try:
            success = self.go_to_executor(location)
            return ActionResult(
                success=success,
                message=f"go_to({location}) {'성공' if success else '실패'}",
            )
        except Exception as e:
            return ActionResult(success=False, message=f"go_to({location}) 에러: {e}")

    def _exec_patrol(self, step: PatrolStep) -> ActionResult:
        area = step.params.area
        duration = step.params.duration
        if self.patrol_executor is None:
            return ActionResult(
                success=True,
                message=f"[sim] patrol({area}, {duration}s) done",
            )
        try:
            success = self.patrol_executor(area, duration)
            return ActionResult(
                success=success,
                message=f"patrol({area}, {duration}s) {'성공' if success else '실패'}",
            )
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"patrol({area}, {duration}s) 에러: {e}",
            )

    def _exec_wait(self, step: WaitStep) -> ActionResult:
        seconds = step.params.seconds
        success = exec_wait(seconds, status_callback=self.status_cb)
        return ActionResult(success=success, message=f"wait({seconds}s) 완료")

    def _exec_report(self, step: ReportStep) -> ActionResult:
        status = step.params.status
        success = exec_report(status, report_callback=self.report_cb)
        return ActionResult(success=success, message=f"report({status}) 발행")
