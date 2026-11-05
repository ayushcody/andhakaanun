"""
LLM Client — Groq API wrapper.

Replaces the previous Gemini client. Uses Groq's OpenAI-compatible async client
with a primary + fallback model chain and timeout handling.

Models are configured via GROQ_MODEL_PRIMARY / GROQ_MODEL_FALLBACK env vars.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from apps.api.config import Settings, get_settings

logger = logging.getLogger("andhakaanun.llm")


class LLMClient:
    """
    Wrapper around Groq async client.
    Supports primary + fallback model chain with timeout.
    """

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._client = None

    def set_api_key(self, api_key: str):
        """Override the default API key (forces re-init)."""
        self._settings.groq_api_key = api_key
        self._client = None

    def _get_client(self):
        """Lazy-initialize the Groq async client."""
        if self._client is None:
            from groq import AsyncGroq

            self._client = AsyncGroq(api_key=self._settings.groq_api_key)
            logger.info("✓ Groq async client initialized")
        return self._client

    async def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Call Groq and return parsed JSON response.

        Args:
            prompt: The user prompt.
            system_instruction: System-level instruction.
            model_name: Which model to use (defaults to primary).

        Returns:
            Dict with keys: data, raw_text, model, latency_ms, token_count.
        """
        import asyncio

        client = self._get_client()
        model = model_name or self._settings.groq_model_primary
        timeout = self._settings.groq_timeout_seconds

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        logger.info("Calling Groq model=%s (timeout=%ds)", model, timeout)
        start = time.perf_counter()

        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=self._settings.groq_temperature,
                    max_tokens=self._settings.groq_max_tokens,
                    response_format={"type": "json_object"},
                ),
                timeout=timeout,
            )

            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.info("Groq responded in %dms (model=%s)", elapsed_ms, model)

            raw_text = response.choices[0].message.content or ""
            if not raw_text:
                raise ValueError("Empty response from Groq")

            raw_text = raw_text.strip()

            try:
                parsed = json.loads(raw_text)
            except json.JSONDecodeError:
                parsed = self._extract_json(raw_text)

            token_count = 0
            try:
                if response.usage:
                    token_count = response.usage.total_tokens or 0
            except Exception:
                pass

            return {
                "data": parsed,
                "raw_text": raw_text,
                "model": model,
                "latency_ms": elapsed_ms,
                "token_count": token_count,
            }

        except TimeoutError as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.warning(
                "Groq TIMEOUT after %dms (model=%s, limit=%ds)", elapsed_ms, model, timeout
            )
            raise TimeoutError(f"Groq {model} timed out after {timeout}s") from e

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.error("Groq error after %dms (model=%s): %s", elapsed_ms, model, e)
            raise

    async def generate_with_fallback(
        self,
        prompt: str,
        system_instruction: str | None = None,
    ) -> dict[str, Any]:
        """
        Try primary model, fall back to secondary on error/timeout.

        Chain: GROQ_MODEL_PRIMARY → GROQ_MODEL_FALLBACK → raise
        """
        primary = self._settings.groq_model_primary
        fallback = self._settings.groq_model_fallback
        primary_err_msg = ""

        try:
            return await self.generate(
                prompt=prompt,
                system_instruction=system_instruction,
                model_name=primary,
            )
        except Exception as primary_error:
            primary_err_msg = str(primary_error)
            logger.warning(
                "Primary model (%s) failed: %s — trying fallback", primary, primary_error
            )

        try:
            result = await self.generate(
                prompt=prompt,
                system_instruction=system_instruction,
                model_name=fallback,
            )
            result["fallback_used"] = True
            return result
        except Exception as fallback_error:
            logger.error("Fallback model (%s) also failed: %s", fallback, fallback_error)
            raise RuntimeError(
                f"Both models failed. Primary: {primary_err_msg}, Fallback: {fallback_error}"
            ) from fallback_error

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Extract JSON from markdown code blocks or raw text."""
        import re

        patterns = [
            r"```json\s*\n?(.*?)\n?```",
            r"```\s*\n?(.*?)\n?```",
            r"\{.*\}",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1) if match.lastindex else match.group())
                except (json.JSONDecodeError, IndexError):
                    continue

        raise ValueError(f"Could not parse JSON from response: {text[:200]}...")


# Singleton
_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Get or create singleton LLM client."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
