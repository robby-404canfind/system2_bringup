"""test_u02_connection.py — Ollama 연결 + 기본 대화 + 에러 핸들링 확인."""
import sys
from pathlib import Path

# 패키지 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from system2_bringup.llm_client import LLMClient, LLMClientError


def test_ollama_connection():
    """Ollama 연결 및 기본 대화 테스트."""
    print("=" * 60)
    print("Step 1: Ollama 연결 + 기본 대화")
    print("=" * 60)

    client = LLMClient(backend="ollama", model="qwen2.5:7b")
    print(f"  클라이언트: {client}")

    response = client.chat(
        [{"role": "user", "content": "안녕하세요, 당신은 누구인가요?"}]
    )
    content = response.choices[0].message.content
    print(f"  응답: {content[:200]}")
    print("✓ Ollama 연결 성공\n")


def test_openrouter_connection():
    """OpenRouter 연결 테스트 (API 키 설정 시)."""
    print("=" * 60)
    print("Step 2: OpenRouter 연결 (선택)")
    print("=" * 60)

    try:
        client = LLMClient(
            backend="openrouter",
            model="openai/gpt-oss-120b:free",
        )
        response = client.chat(
            [{"role": "user", "content": "안녕하세요, 당신은 누구인가요?"}]
        )
        content = response.choices[0].message.content
        print(f"  클라이언트: {client}")
        print(f"  응답: {content[:200]}")
        print("✓ OpenRouter 연결 성공\n")
    except LLMClientError as e:
        print(f"  건너뜀: {e}")
        print("△ OPENROUTER_API_KEY 미설정 — OpenRouter 테스트 생략\n")


def test_error_handling():
    """에러 핸들링 확인: 잘못된 base_url로 LLMClientError 발생 테스트."""
    import os

    print("=" * 60)
    print("Step 3: 에러 핸들링 확인")
    print("=" * 60)

    # 존재하지 않는 포트로 강제 에러 유발
    original = os.environ.get("OLLAMA_BASE_URL")
    os.environ["OLLAMA_BASE_URL"] = "http://localhost:19999/v1"

    try:
        client = LLMClient(
            backend="ollama", model="qwen2.5:7b", timeout=3.0, max_retries=0
        )
        client.chat([{"role": "user", "content": "테스트"}])
        print("✗ 에러가 발생해야 하는데 성공함")
    except LLMClientError as e:
        print(f"  에러: {e}")
        print(f"  backend: {e.backend}")
        print(f"  retriable: {e.retriable}")
        print("✓ LLMClientError 정상 발생\n")
    finally:
        # 원래 값 복원
        if original is not None:
            os.environ["OLLAMA_BASE_URL"] = original
        else:
            os.environ.pop("OLLAMA_BASE_URL", None)


if __name__ == "__main__":
    try:
        test_ollama_connection()
        test_openrouter_connection()
        test_error_handling()
        print("=" * 60)
        print("Unit 02 연결 테스트 완료")
        print("=" * 60)
    except LLMClientError as e:
        print(f"\n✗ LLM 에러: {e}")
        print(f"  backend={e.backend}, retriable={e.retriable}")
        print("\n호스트에서 'ollama serve'가 실행 중인지 확인하세요.")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ 예상치 못한 에러: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
