"""llm_client.py — Ollama/OpenRouter 통합 LLM 클라이언트."""
import os
from openai import OpenAI, APITimeoutError, APIConnectionError, APIStatusError


class LLMClientError(Exception):
    """LLMClient 내부 에러. 백엔드별 예외를 통합합니다."""

    def __init__(self, message: str, backend: str, retriable: bool = False):
        super().__init__(message)
        self.backend = backend
        self.retriable = retriable


def _build_backend_config(backend: str) -> dict:
    """현재 환경변수를 기준으로 백엔드 설정을 동적으로 구성합니다."""
    if backend == "ollama":
        return {
            "base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            "api_key": "ollama",  # Ollama는 API 키 불필요, 더미 값
        }

    if backend == "openrouter":
        return {
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": os.environ.get("OPENROUTER_API_KEY", ""),
        }

    raise ValueError(f"Unknown backend: {backend}. Use 'ollama' or 'openrouter'.")


class LLMClient:
    """Edge LLM(Ollama)과 Cloud LLM(OpenRouter)을 통합하는 클라이언트.

    런타임 계약:
    - timeout: 기본 10초. Topic ingress가 오래 붙잡히지 않도록 제한.
    - max_retries: 기본 1회. 실패 시 한 번만 재시도.
    - 예외: 모든 백엔드 에러는 LLMClientError로 정규화.
    """

    def __init__(
        self,
        backend: str = "ollama",
        model: str = "qwen2.5:7b",
        timeout: float = 10.0,
        max_retries: int = 1,
        supports_tools: bool | None = None,
        supports_structured_output: bool = False,
    ):
        config = _build_backend_config(backend)
        if backend == "openrouter" and not config["api_key"]:
            raise LLMClientError(
                "OPENROUTER_API_KEY 환경변수가 설정되지 않았습니다.", backend
            )
        self.client = OpenAI(**config, timeout=timeout, max_retries=max_retries)
        self.model = model
        self.backend = backend
        self.timeout = timeout

        # 백엔드별 기능 호환성 플래그.
        # None = 미확인 (u04에서 probe 또는 config로 결정),
        # True/False = 명시적 설정.
        self.supports_tools = supports_tools
        self.supports_structured_output = supports_structured_output

    def chat(self, messages: list[dict], **kwargs):
        """Chat Completions API 호출.

        모든 백엔드 예외를 LLMClientError로 정규화합니다.
        """
        try:
            return self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                **kwargs,
            )
        except APITimeoutError as e:
            raise LLMClientError(
                f"LLM 응답 타임아웃 ({self.timeout}초 초과)", self.backend, retriable=True
            ) from e
        except APIConnectionError as e:
            raise LLMClientError(
                f"LLM 연결 실패: {e}", self.backend, retriable=True
            ) from e
        except APIStatusError as e:
            raise LLMClientError(
                f"LLM API 에러 (HTTP {e.status_code}): {e.message}",
                self.backend,
                retriable=(e.status_code >= 500),
            ) from e

    def __repr__(self):
        return f"LLMClient(backend='{self.backend}', model='{self.model}')"
