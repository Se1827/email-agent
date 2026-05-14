"""Thin async wrapper around the Groq chat completions API."""

from __future__ import annotations

import logging
import time

from groq import AsyncGroq

from src.config import get_settings
from src.observability import span
from src.storage import safe_record_llm_interaction

log = logging.getLogger(__name__)

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=get_settings().groq_api_key)
    return _client


async def chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    model: str | None = None,
) -> str:
    """Send a chat completion request and return the assistant's reply text.

    Logs prompt size, model, and latency for observability.
    """
    client = _get_client()
    model = model or get_settings().groq_model

    prompt_chars = sum(len(m.get("content", "")) for m in messages)
    log.info("llm_request", extra={"model": model, "prompt_chars": prompt_chars})

    start = time.perf_counter()
    with span("llm.chat", model=model, prompt_chars=prompt_chars):
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    elapsed = time.perf_counter() - start

    reply = response.choices[0].message.content or ""
    safe_record_llm_interaction(
        purpose="chat",
        model=model,
        messages=messages,
        response=reply,
        latency_s=round(elapsed, 3),
        metadata={"temperature": temperature, "max_tokens": max_tokens},
    )
    log.info(
        "llm_response",
        extra={
            "model": model,
            "latency_s": round(elapsed, 3),
            "reply_chars": len(reply),
        },
    )
    return reply
