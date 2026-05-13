"""test_u02_json_mode.py — JSON mode 검증 + Edge vs Cloud 지연 시간 비교."""
import json
import sys
import time
from pathlib import Path

# 패키지 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from system2_bringup.llm_client import LLMClient, LLMClientError


def test_json_mode(client: LLMClient):
    """JSON mode로 LLM 호출 → json.loads() 파싱 확인."""
    response = client.chat(
        messages=[
            {"role": "system", "content": "항상 JSON 형식으로 응답하세요."},
            {
                "role": "user",
                "content": (
                    "로봇에게 '회의실로 가줘'라는 명령을 "
                    "task와 location 필드가 있는 JSON으로 변환하세요."
                ),
            },
        ],
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content
    data = json.loads(raw)  # 파싱 실패 시 JSONDecodeError
    return data


def measure_latency(client: LLMClient, prompt: str) -> dict:
    """LLM 호출 + 지연 시간 측정."""
    start = time.time()
    response = client.chat([{"role": "user", "content": prompt}])
    elapsed = time.time() - start
    content = response.choices[0].message.content
    return {
        "backend": client.backend,
        "model": client.model,
        "elapsed": elapsed,
        "content": content,
    }


def main():
    # ── Step 1: Ollama JSON mode ──
    print("=" * 60)
    print("Step 1: Ollama JSON mode 테스트")
    print("=" * 60)

    client_local = LLMClient(backend="ollama", model="qwen2.5:7b")
    data = test_json_mode(client_local)
    print(f"  Parsed JSON: {json.dumps(data, indent=2, ensure_ascii=False)}")
    print("✓ Ollama JSON mode 정상\n")

    # ── Step 2: OpenRouter JSON mode (선택) ──
    print("=" * 60)
    print("Step 2: OpenRouter JSON mode 테스트 (선택)")
    print("=" * 60)

    client_cloud = None
    try:
        client_cloud = LLMClient(
            backend="openrouter",
            model="openai/gpt-oss-120b:free",
        )
        data = test_json_mode(client_cloud)
        print(f"  Parsed JSON: {json.dumps(data, indent=2, ensure_ascii=False)}")
        print("✓ OpenRouter JSON mode 정상\n")
    except LLMClientError as e:
        print(f"  건너뜀: {e}")
        print("△ OpenRouter 테스트 생략\n")

    # ── Step 3: 지연 시간 비교 ──
    print("=" * 60)
    print("Step 3: Edge vs Cloud 지연 시간 비교")
    print("=" * 60)

    prompt = (
        "당신은 배달 로봇입니다. 사용자가 '회의실 갔다가 충전소로 와'라고 했습니다. "
        "어떻게 하시겠습니까?"
    )

    result_local = measure_latency(client_local, prompt)
    print(f"  [Ollama] {result_local['elapsed']:.1f}초")
    print(f"           {result_local['content'][:150]}...")

    if client_cloud:
        result_cloud = measure_latency(client_cloud, prompt)
        print(f"  [OpenRouter] {result_cloud['elapsed']:.1f}초")
        print(f"               {result_cloud['content'][:150]}...")

        print(f"\n  비교: Ollama {result_local['elapsed']:.1f}초 vs "
              f"OpenRouter {result_cloud['elapsed']:.1f}초")
    else:
        print("\n  OpenRouter 미설정 — Ollama 단독 측정만 완료")

    print("\n" + "=" * 60)
    print("Unit 02 JSON mode + 지연 시간 비교 완료")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except LLMClientError as e:
        print(f"\n✗ LLM 에러: {e}")
        print(f"  backend={e.backend}, retriable={e.retriable}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"\n✗ JSON 파싱 실패: {e}")
        print("  JSON mode가 지원되지 않는 모델일 수 있습니다.")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ 예상치 못한 에러: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
