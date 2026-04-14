"""
Central LLM client — wraps OpenAI with retry, logging, and token tracking.
"""
import os
import time
import logging
from typing import Optional, List
from openai import OpenAI

logger = logging.getLogger(__name__)

_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY not set")
        _client = OpenAI(api_key=api_key)
    return _client


def chat(
    system: str,
    user: str,
    model: str = "gpt-4o",
    temperature: float = 0.2,
    max_tokens: int = 4096,
    retries: int = 3,
) -> str:
    """
    Single-turn chat with retry logic.
    Returns assistant message content as plain string.
    """
    client = get_client()
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]

    for attempt in range(1, retries + 1):
        try:
            t0 = time.time()
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            elapsed = time.time() - t0
            content = response.choices[0].message.content.strip()
            usage   = response.usage

            logger.info(
                "LLM call | model=%s tokens_in=%d tokens_out=%d latency=%.2fs",
                model, usage.prompt_tokens, usage.completion_tokens, elapsed,
            )
            return content

        except Exception as exc:
            logger.warning("LLM attempt %d/%d failed: %s", attempt, retries, exc)
            if attempt == retries:
                raise
            time.sleep(2 ** attempt)   # exponential back-off


def chat_with_history(
    messages: List[dict],
    model: str = "gpt-4o",
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> str:
    """
    Multi-turn chat. messages = [{"role": ..., "content": ...}, ...]
    """
    client = get_client()
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()
