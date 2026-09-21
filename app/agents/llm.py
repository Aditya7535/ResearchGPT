"""
LLM backend for the ResearchGPT agent pipeline.

Matches the BusinessGPT pattern:
  Primary  : Groq API  →  llama-3.1-8b-instant  (fast, free tier)
  Fallback : Ollama    →  llama3 / mistral       (local, offline)

The ``get_llm()`` factory reads ``LLM_PROVIDER`` from the environment:
    LLM_PROVIDER=groq    →  ChatGroq (default)
    LLM_PROVIDER=ollama  →  ChatOllama

Environment variables
---------------------
    LLM_PROVIDER          : "groq" | "ollama"          (default: "groq")
    GROQ_API_KEY          : Groq API key                (required for groq)
    GROQ_MODEL            : Groq model name             (default: llama-3.1-8b-instant)
    OLLAMA_BASE_URL       : Ollama server URL           (default: http://localhost:11434)
    OLLAMA_MODEL          : Ollama model name           (default: llama3)
    LLM_TEMPERATURE       : float 0–1                  (default: 0.1 for agents)
    LLM_MAX_TOKENS        : int                        (default: 4096)
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults (matching BusinessGPT setup)
# ---------------------------------------------------------------------------
_DEFAULTS = {
    "LLM_PROVIDER":    "groq",
    "GROQ_MODEL":      "llama-3.1-8b-instant",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL":    "llama3",
    "LLM_TEMPERATURE": "0.1",
    "LLM_MAX_TOKENS":  "4096",
}


def _env(key: str) -> str:
    return os.environ.get(key, _DEFAULTS.get(key, ""))


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------

def get_llm(temperature: float | None = None, max_tokens: int | None = None) -> Any:
    """
    Return a LangChain chat model based on ``LLM_PROVIDER`` env var.

    Parameters
    ----------
    temperature:
        Override the default temperature. Defaults to ``LLM_TEMPERATURE`` env.
    max_tokens:
        Override max output tokens. Defaults to ``LLM_MAX_TOKENS`` env.

    Returns
    -------
    A LangChain ``BaseChatModel`` (ChatGroq | ChatOllama).

    Raises
    ------
    ImportError
        If the required provider package is not installed.
    ValueError
        If ``LLM_PROVIDER`` is unknown or required env vars are missing.
    """
    provider    = _env("LLM_PROVIDER").lower()
    temp        = temperature if temperature is not None else float(_env("LLM_TEMPERATURE"))
    max_tok     = max_tokens  if max_tokens  is not None else int(_env("LLM_MAX_TOKENS"))

    if provider == "groq":
        return _build_groq(temp, max_tok)
    if provider == "ollama":
        return _build_ollama(temp, max_tok)

    raise ValueError(
        f"Unknown LLM_PROVIDER='{provider}'. Set to 'groq' or 'ollama'."
    )


def _build_groq(temperature: float, max_tokens: int) -> Any:
    try:
        from langchain_groq import ChatGroq
    except ImportError as exc:
        raise ImportError(
            "langchain-groq is required. Install: pip install langchain-groq"
        ) from exc

    api_key = _env("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY env var is not set. "
            "Get a free key at https://console.groq.com"
        )

    model = _env("GROQ_MODEL")
    logger.info("LLM backend: Groq / %s (temp=%.2f)", model, temperature)
    return ChatGroq(
        api_key=api_key,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _build_ollama(temperature: float, max_tokens: int) -> Any:
    try:
        from langchain_ollama import ChatOllama
    except ImportError as exc:
        raise ImportError(
            "langchain-ollama is required. Install: pip install langchain-ollama"
        ) from exc

    base_url = _env("OLLAMA_BASE_URL")
    model    = _env("OLLAMA_MODEL")
    logger.info("LLM backend: Ollama / %s @ %s (temp=%.2f)", model, base_url, temperature)
    return ChatOllama(
        base_url=base_url,
        model=model,
        temperature=temperature,
        num_predict=max_tokens,
    )


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

def make_system_message(content: str) -> dict[str, str]:
    return {"role": "system", "content": content}


def make_human_message(content: str) -> dict[str, str]:
    return {"role": "human", "content": content}
