"""Provider-independent OpenAI-compatible chat completion client."""

from dataclasses import dataclass
import httpx

from app.observability.tracing import record_llm_attempt, record_llm_completion, record_llm_failure


@dataclass(frozen=True, slots=True)
class LLMResult:
    text: str
    prompt_tokens: int | None
    completion_tokens: int | None


class LLMServiceError(RuntimeError):
    """OpenAI-compatible endpoint or its output could not be used."""


def _usage_value(usage: dict, key: str) -> int | None:
    raw = usage.get(key)
    return raw if isinstance(raw, int) and raw >= 0 else None


async def complete_chat(
    messages: list[dict[str, str]],
    *,
    base_url: str,
    api_key: str,
    model: str,
    max_tokens: int = 128,
    timeout_seconds: float = 150.0,
    disable_qwen_thinking: bool = True,
) -> LLMResult:
    """Make one call; never silently replace a failed generation with a fake answer."""
    if not messages or max_tokens <= 0:
        raise ValueError("messages must be present and max_tokens > 0")

    payload: dict = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    # Qwen3 on vLLM can exhaust a 1024-token context on internal reasoning.
    # Disable thinking only for the configured Qwen3 model, not all providers.
    if disable_qwen_thinking and "qwen3" in model.lower():
        payload["chat_template_kwargs"] = {"enable_thinking": False}

    headers = {"Authorization": f"Bearer {api_key or 'EMPTY'}"}
    endpoint = base_url.rstrip("/") + "/chat/completions"

    record_llm_attempt()
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, trust_env=False) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        record_llm_failure()
        raise LLMServiceError(f"Unable to call LLM at {endpoint}: {exc}") from exc

    choices = body.get("choices", []) if isinstance(body, dict) else []
    if not choices or not isinstance(choices[0], dict):
        record_llm_failure()
        raise LLMServiceError("LLM returned no choices.")
    message = choices[0].get("message") or {}
    text = message.get("content") if isinstance(message, dict) else None
    if not isinstance(text, str) or not text.strip():
        record_llm_failure()
        raise LLMServiceError("LLM returned an empty answer.")
    usage = body.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    prompt_tokens = _usage_value(usage, "prompt_tokens")
    completion_tokens = _usage_value(usage, "completion_tokens")
    record_llm_completion(prompt_tokens, completion_tokens)
    return LLMResult(
        text=text.strip(),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
