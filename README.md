# system2_bringup

Agentic VLA Ch05 통합용 System2 planner 패키지입니다.

- 자연어 명령을 `HighLevelPlan` JSON으로 변환합니다.
- Ch02 `social_nav_bringup`의 Nav2 adapter를 통해 `go_to`/`patrol`을 실행합니다.
- Ch04 `perception_bringup` ActionServer를 통해 `find`/`scan`/`follow`를 실행합니다.
- Ch05 `assess_scene`/`resolve_target`/`follow_query`로 장면 평가와 자연어 대상 추적을 연결합니다.

## Semantic Locations

Ch05 통합 실습의 hall semantic location 단일 기준은 `config/semantic_locations.hall.yaml`입니다. `social_nav_bringup`은 `exec_go_to()`/`Nav2Navigator` 실행 로직만 제공하고, System2 planner가 이 파일에서 로드한 좌표 dict를 전달합니다.

`social_nav_bringup/config/semantic_locations.office.yaml`은 Ch02 단독 `go_to_node`/`patrol_node` 유닛 액션 테스트용 office 환경 파일로 유지합니다.
