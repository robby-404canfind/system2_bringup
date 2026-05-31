"""plan_models.py — HighLevelPlan 및 Step Pydantic 모델 (Ch05 확장).

Ch03 대비 변경:
- BaseStep.max_duration_sec: go_to/wait용 step timeout
- FindStep, ScanStep, FollowStep: Ch04 Perception Action 연동
- AssessSceneStep, ResolveTargetStep, FollowQueryStep: Agentic VLA scenario 연동
- Step union 확장
"""
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


# ---- Params ----

class GoToParams(BaseModel):
    location: str


class PatrolParams(BaseModel):
    area: str = Field(description="사전 정의된 patrol route ID")
    duration: int = Field(ge=10, le=3600)


class WaitParams(BaseModel):
    seconds: int = Field(ge=1, le=300)


class ReportParams(BaseModel):
    status: str


class FindParams(BaseModel):
    """Ch04 /system1/find Action Goal 파라미터."""
    target_class: str = Field(description="탐지 대상 클래스 (예: person)")
    timeout_sec: float = Field(default=30.0, ge=5.0, le=120.0)
    sweep_deg: float = Field(default=360.0, ge=0.0, le=720.0)


class ScanParams(BaseModel):
    """Ch04 /system1/scan Action Goal 파라미터."""
    duration_sec: float = Field(default=30.0, ge=5.0, le=120.0)
    sweep_deg: float = Field(default=360.0, ge=0.0, le=720.0)


class FollowParams(BaseModel):
    """Ch04 /system1/follow Action Goal 파라미터."""
    target_class: str = Field(default="person")
    target_id: int = Field(default=-1)
    target_distance_m: float = Field(default=2.0, ge=0.5, le=5.0)
    max_time_sec: float = Field(default=60.0, ge=5.0, le=180.0)


class AssessSceneParams(BaseModel):
    """Ch05 /system1/assess_scene Action Goal 파라미터."""
    query: str = Field(description="장면 평가 질문")
    timeout_sec: float = Field(default=30.0, ge=5.0, le=120.0)


class ResolveTargetParams(BaseModel):
    """Ch05 /system1/resolve_target Action Goal 파라미터."""
    target_query: str = Field(description="자연어 대상 설명")
    timeout_sec: float = Field(default=30.0, ge=5.0, le=120.0)


class FollowQueryParams(BaseModel):
    """자연어 대상 설명을 track id로 해석한 뒤 follow를 수행하는 고수준 파라미터."""
    target_query: str = Field(description="자연어 대상 설명")
    target_distance_m: float = Field(default=2.0, ge=0.5, le=5.0)
    max_time_sec: float = Field(default=60.0, ge=5.0, le=180.0)
    resolve_timeout_sec: float = Field(default=30.0, ge=5.0, le=120.0)


# ---- Steps ----

class BaseStep(BaseModel):
    guard: Optional[str] = Field(default=None, description="실행 전 조건 (Ch05)")
    retry: int = Field(default=0, ge=0, le=3, description="재시도 횟수")
    max_duration_sec: Optional[float] = Field(
        default=None,
        ge=1.0,
        le=180.0,
        description="Step timeout (초). go_to/wait에 적용. "
        "find/scan/follow는 Goal params timeout에 위임.",
    )


class GoToStep(BaseStep):
    task: Literal["go_to"]
    params: GoToParams


class PatrolStep(BaseStep):
    task: Literal["patrol"]
    params: PatrolParams


class WaitStep(BaseStep):
    task: Literal["wait"]
    params: WaitParams


class ReportStep(BaseStep):
    task: Literal["report"]
    params: ReportParams


class FindStep(BaseStep):
    task: Literal["find"]
    params: FindParams


class ScanStep(BaseStep):
    task: Literal["scan"]
    params: ScanParams


class FollowStep(BaseStep):
    task: Literal["follow"]
    params: FollowParams


class AssessSceneStep(BaseStep):
    task: Literal["assess_scene"]
    params: AssessSceneParams


class ResolveTargetStep(BaseStep):
    task: Literal["resolve_target"]
    params: ResolveTargetParams


class FollowQueryStep(BaseStep):
    task: Literal["follow_query"]
    params: FollowQueryParams


Step = Annotated[
    Union[
        GoToStep, PatrolStep, WaitStep, ReportStep,
        FindStep, ScanStep, FollowStep,
        AssessSceneStep, ResolveTargetStep, FollowQueryStep,
    ],
    Field(discriminator="task"),
]


class HighLevelPlan(BaseModel):
    """System2가 생성하는 고수준 미션 계획."""

    version: str = "1.0.0"
    mission_id: str = Field(description="호출측이 발급한 고유 미션 식별자")
    intent: str = Field(description="미션 의도 요약")
    constraints: list[str] = Field(default_factory=list, description="제약 조건")
    steps: list[Step] = Field(
        min_length=1,
        max_length=5,
        description="1-5개 실행 단계",
    )
    replan_rules: dict = Field(default_factory=dict, description="재계획 규칙")


class ActionResult(BaseModel):
    """Unit Action 실행 결과."""

    success: bool
    message: str = ""
    elapsed_sec: float = 0.0


class ValidationResult(BaseModel):
    """Schema Validation 결과."""

    ok: bool
    error: str = ""
    level: str = ""  # "L1", "L2", "L3"
