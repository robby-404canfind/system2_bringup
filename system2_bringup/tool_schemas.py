"""tool_schemas.py — Function Calling용 Tool Definition."""
import json


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
