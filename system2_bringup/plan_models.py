"""plan_models.py — HighLevelPlan 및 Step Pydantic 모델."""
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


class GoToParams(BaseModel):
    location: str


class PatrolParams(BaseModel):
    area: str = Field(description="사전 정의된 patrol route ID")
    duration: int = Field(ge=10, le=3600)


class WaitParams(BaseModel):
    seconds: int = Field(ge=1, le=300)


class ReportParams(BaseModel):
    status: str


class BaseStep(BaseModel):
    guard: Optional[str] = Field(default=None, description="실행 전 조건 (Ch05)")
    retry: int = Field(default=0, ge=0, le=3, description="재시도 횟수")


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


Step = Annotated[
    Union[GoToStep, PatrolStep, WaitStep, ReportStep],
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
