"""Shared LLM client for OpenAI-compatible APIs.

If ``TRADESCOUT_LLM_API_KEY`` is not set in ``.env``, all functions
return None gracefully so callers can fall back to their offline heuristics.
"""
from __future__ import annotations

import logging
from typing import Optional

from openai import OpenAI

from .config import settings

logger = logging.getLogger(__name__)


def is_available() -> bool:
    """True when an LLM API key is configured and the client is ready."""
    return bool(settings.llm_api_key.strip())


def _client() -> Optional[OpenAI]:
    if not is_available():
        return None
    return OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url or "https://api.openai.com/v1",
    )


def chat(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 800,
) -> Optional[str]:
    """Send a chat completion request. Returns the assistant's text, or None on
    any error / unconfigured key so callers degrade gracefully.
    """
    client = _client()
    if client is None:
        return None
    try:
        resp = client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = resp.choices[0].message.content
        return content.strip() if content else None
    except Exception:
        logger.exception("LLM chat request failed")
        return None
