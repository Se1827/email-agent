"""LangChain-based LLM client using ChatGroq.

Provides both a raw ``chat()`` interface (backward-compatible) and a
structured ``invoke_chain()`` for LangChain LCEL chains.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable

from src.config import get_settings
from src.observability import span
from src.storage import safe_record_llm_interaction

log = logging.getLogger(__name__)

_llm: BaseChatModel | None = None


def _get_llm(*, temperature: float = 0.3, max_tokens: int = 1024) -> BaseChatModel:
    """Return a ChatGroq instance configured with the given params."""
    from langchain_groq import ChatGroq

    cfg = get_settings()
    return ChatGroq(
        api_key=cfg.groq_api_key,
        model=cfg.groq_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def get_default_llm() -> BaseChatModel:
    """Return a shared default ChatGroq instance (temp=0.3, 1024 tokens)."""
    global _llm
    if _llm is None:
        _llm = _get_llm()
    return _llm


def _to_langchain_messages(messages: list[dict[str, str]]) -> list[BaseMessage]:
    """Convert dict-based messages to LangChain message objects."""
    result: list[BaseMessage] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            result.append(SystemMessage(content=content))
        elif role == "assistant":
            result.append(AIMessage(content=content))
        else:
            result.append(HumanMessage(content=content))
    return result


async def chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    model: str | None = None,
) -> str:
    """Send a chat completion request and return the assistant's reply text.

    Backward-compatible with the old Groq-direct interface but now uses
    LangChain ChatGroq under the hood.
    """
    llm = _get_llm(temperature=temperature, max_tokens=max_tokens)
    if model:
        llm = llm.bind(model=model)

    lc_messages = _to_langchain_messages(messages)
    prompt_chars = sum(len(m.content) for m in lc_messages)
    actual_model = model or get_settings().groq_model

    log.info("llm_request", extra={"model": actual_model, "prompt_chars": prompt_chars})

    start = time.perf_counter()
    with span("llm.chat", model=actual_model, prompt_chars=prompt_chars):
        response: AIMessage = await llm.ainvoke(lc_messages)
    elapsed = time.perf_counter() - start

    reply = response.content or ""
    safe_record_llm_interaction(
        purpose="chat",
        model=actual_model,
        messages=messages,
        response=reply,
        latency_s=round(elapsed, 3),
        metadata={"temperature": temperature, "max_tokens": max_tokens, "engine": "langchain_groq"},
    )
    log.info(
        "llm_response",
        extra={
            "model": actual_model,
            "latency_s": round(elapsed, 3),
            "reply_chars": len(reply),
        },
    )
    return reply


async def invoke_chain(
    chain: Runnable,
    inputs: dict[str, Any],
    *,
    purpose: str = "chain",
) -> str:
    """Invoke a LangChain LCEL chain and return the string output.

    Handles observability, logging, and storage recording.
    """
    model = get_settings().groq_model
    log.info("chain_invoke", extra={"purpose": purpose, "model": model})

    start = time.perf_counter()
    with span(f"llm.chain.{purpose}", model=model):
        result = await chain.ainvoke(inputs)
    elapsed = time.perf_counter() - start

    # Extract text from result — handles AIMessage or plain str
    if isinstance(result, AIMessage):
        reply = result.content or ""
    elif isinstance(result, BaseMessage):
        reply = result.content or ""
    else:
        reply = str(result)

    safe_record_llm_interaction(
        purpose=purpose,
        model=model,
        messages=[{"role": "chain_input", "content": str(inputs)[:500]}],
        response=reply,
        latency_s=round(elapsed, 3),
        metadata={"engine": "langchain_chain"},
    )
    log.info(
        "chain_response",
        extra={
            "purpose": purpose,
            "model": model,
            "latency_s": round(elapsed, 3),
            "reply_chars": len(reply),
        },
    )
    return reply
