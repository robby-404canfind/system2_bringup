# system2_bringup

Agentic VLA Ch05 통합용 System2 planner 패키지입니다.

- 자연어 명령을 `HighLevelPlan` JSON으로 변환합니다.
- Ch02 `social_nav_bringup`의 Nav2 adapter를 통해 `go_to`/`patrol`을 실행합니다.
- Ch04 `perception_bringup` ActionServer를 통해 `find`/`scan`/`follow`를 실행합니다.
- Ch05 `assess_scene`/`resolve_target`/`follow_query`로 장면 평가와 자연어 대상 추적을 연결합니다.
