"""tool_schemas.py — Function Calling용 Tool Definition (Ch05 확장).

Ch03 대비 변경:
    - find, scan, follow, assess_scene, resolve_target, follow_query Tool Definition 추가
- PERCEPTION_TARGET_HINTS: LLM 안내용 클래스 힌트 (L2 검증은 미적용)
"""
import json

# LLM이 자주 사용할 탐지 대상 힌트 (L2 허용 목록이 아닌 안내용)
PERCEPTION_TARGET_HINTS = [
    "person", "chair", "bottle", "cup", "laptop",
    "backpack", "handbag", "cell phone", "book", "potted plant",
]


def build_tool_schemas(locations: list[str], patrol_routes: list[str]) -> list[dict]:
    """허용 목록을 enum에 포함한 Tool Schema를 생성합니다."""
    return [
        {
            "type": "function",
            "function": {
                "name": "go_to",
                "description": "시맨틱 위치로 로봇을 이동시킵니다",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "enum": locations,
                            "description": "목적지 시맨틱 이름",
                        }
                    },
                    "required": ["location"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "patrol",
                "description": "사전 정의된 순찰 루트를 실행합니다",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "area": {
                            "type": "string",
                            "enum": patrol_routes,
                            "description": "순찰 루트 ID",
                        },
                        "duration": {
                            "type": "integer",
                            "description": "순찰 시간 (초)",
                            "minimum": 10,
                            "maximum": 3600,
                        },
                    },
                    "required": ["area", "duration"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "wait",
                "description": "지정 시간 동안 대기합니다",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "seconds": {
                            "type": "integer",
                            "description": "대기 시간 (초)",
                            "minimum": 1,
                            "maximum": 300,
                        }
                    },
                    "required": ["seconds"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "report",
                "description": "현재 상태를 보고합니다",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "description": "보고 내용"}
                    },
                    "required": ["status"],
                },
            },
        },
        # ---- Ch05 추가: Perception Actions ----
        {
            "type": "function",
            "function": {
                "name": "find",
                "description": "로봇이 주변을 회전하며 특정 대상을 찾습니다 (YOLO 기반)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_class": {
                            "type": "string",
                            "description": f"탐지 대상 클래스. 예: {', '.join(PERCEPTION_TARGET_HINTS[:5])}",
                        },
                        "timeout_sec": {
                            "type": "number",
                            "description": "탐색 제한 시간 (초)",
                            "minimum": 5,
                            "maximum": 120,
                            "default": 30,
                        },
                        "sweep_deg": {
                            "type": "number",
                            "description": "회전 탐색 각도 (도)",
                            "minimum": 0,
                            "maximum": 720,
                            "default": 360,
                        },
                    },
                    "required": ["target_class"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "scan",
                "description": "로봇이 주변을 회전 스캔하여 인지 가능한 모든 객체를 기록합니다",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "duration_sec": {
                            "type": "number",
                            "description": "스캔 시간 (초)",
                            "minimum": 5,
                            "maximum": 120,
                            "default": 30,
                        },
                        "sweep_deg": {
                            "type": "number",
                            "description": "회전 스캔 각도 (도)",
                            "minimum": 0,
                            "maximum": 720,
                            "default": 360,
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "follow",
                "description": "특정 대상을 추적하여 일정 거리를 유지하며 따라갑니다",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_class": {
                            "type": "string",
                            "description": "추적 대상 클래스",
                            "default": "person",
                        },
                        "target_id": {
                            "type": "integer",
                            "description": "추적 대상 YOLO ID (-1이면 첫 번째 감지 대상)",
                            "default": -1,
                        },
                        "target_distance_m": {
                            "type": "number",
                            "description": "유지할 목표 거리 (m)",
                            "minimum": 0.5,
                            "maximum": 5.0,
                            "default": 2.0,
                        },
                        "max_time_sec": {
                            "type": "number",
                            "description": "추적 제한 시간 (초)",
                            "minimum": 5,
                            "maximum": 180,
                            "default": 60,
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "assess_scene",
                "description": "현재 장면을 VLM으로 평가하고 수상 후보/위험도/근거를 반환합니다",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "장면 평가 질문",
                        },
                        "timeout_sec": {
                            "type": "number",
                            "description": "장면 평가 제한 시간 (초)",
                            "minimum": 5,
                            "maximum": 120,
                            "default": 30,
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "resolve_target",
                "description": "자연어 대상 설명을 현재 보이는 person track id로 해석합니다",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_query": {
                            "type": "string",
                            "description": "예: 파란색 옷을 입은 사람, 왼쪽 사람",
                        },
                        "timeout_sec": {
                            "type": "number",
                            "description": "대상 식별 제한 시간 (초)",
                            "minimum": 5,
                            "maximum": 120,
                            "default": 30,
                        },
                    },
                    "required": ["target_query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "follow_query",
                "description": "자연어 대상 설명을 track id로 해석한 뒤 해당 person을 추적합니다",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_query": {
                            "type": "string",
                            "description": "예: 파란색 옷을 입은 사람, 가방 든 사람",
                        },
                        "target_distance_m": {
                            "type": "number",
                            "description": "유지할 목표 거리 (m)",
                            "minimum": 0.5,
                            "maximum": 5.0,
                            "default": 2.0,
                        },
                        "max_time_sec": {
                            "type": "number",
                            "description": "추적 제한 시간 (초)",
                            "minimum": 5,
                            "maximum": 180,
                            "default": 60,
                        },
                        "resolve_timeout_sec": {
                            "type": "number",
                            "description": "대상 식별 제한 시간 (초)",
                            "minimum": 5,
                            "maximum": 120,
                            "default": 30,
                        },
                    },
                    "required": ["target_query"],
                },
            },
        },
    ]


def call_with_tools(client, messages: list, tools: list) -> dict:
    """native FC 실험용 helper.

    Ch03 main path는 Structured Output입니다.
    이 helper의 결과는 executor에 바로 넘기지 말고 별도 검증 또는 1-step
    plan 정규화를 거쳐야 합니다.
    """
    if client.supports_tools:
        response = client.chat(messages=messages, tools=tools, tool_choice="auto")
        tool_calls = response.choices[0].message.tool_calls
        if tool_calls:
            result = {
                "mode": "native_fc",
                "name": tool_calls[0].function.name,
                "args": json.loads(tool_calls[0].function.arguments),
            }
            return _validate_tool_result(result, tools)

    raise RuntimeError(
        "Native Function Calling 미지원 또는 tool_calls 없음. "
        "Ch03에서는 Structured Output 경로를 사용하세요."
    )


def _validate_tool_result(result: dict, tools: list[dict]) -> dict:
    """도구 이름과 args의 최소 형식을 검증합니다."""
    allowed_names = {tool["function"]["name"] for tool in tools}
    name = result.get("name")
    args = result.get("args")
    if name not in allowed_names:
        raise ValueError(f"알 수 없는 도구: {name}")
    if not isinstance(args, dict):
        raise ValueError("tool args는 dict여야 합니다.")
    return result
