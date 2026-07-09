# Copyright 2026 Nan Zhijin
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""LLM provider abstraction.

DeepSeek is implemented (openai-compatible protocol).
Anthropic / OpenAI adapters can be added behind the same protocol.

API key resolution (highest to lowest priority):
  1. --api-key CLI argument
  2. Environment variable (DEEPSEEK_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY)
  3. .env file in current directory
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

# ── auto-load .env ──────────────────────────────────────
try:
    from dotenv import load_dotenv  # python-dotenv (optional)

    _env_path = Path(".env")
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass  # python-dotenv not installed — .env is skipped


class LLMAdapter(Protocol):
    """Minimal sync interface for LLM backends.

    Sync by design — the Generator is a CLI tool making a single call.
    Async can be added later if needed.
    """

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        max_tokens: int = 8192,
    ) -> str:
        """Send system + user prompt, return the LLM's text response."""
        ...


# ═══════════════════════════════════════════════════════════
# DeepSeek (openai-compatible)
# ═══════════════════════════════════════════════════════════

_DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class DeepSeekAdapter:
    """DeepSeek adapter via OpenAI-compatible SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = _DEEPSEEK_BASE_URL,
    ) -> None:
        import openai

        self._api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not self._api_key:
            raise ValueError(
                "DeepSeek API key not found. Set DEEPSEEK_API_KEY env var "
                "or pass --api-key."
            )

        self._client = openai.OpenAI(
            api_key=self._api_key,
            base_url=base_url,
        )
        self._default_model = "deepseek-chat"

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        max_tokens: int = 8192,
    ) -> str:
        response = self._client.chat.completions.create(
            model=model or self._default_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content
        if content is None:
            raise RuntimeError("LLM returned empty response")
        return content


# ═══════════════════════════════════════════════════════════
# Anthropic (native SDK — used via DeepSeek relay)
# ═══════════════════════════════════════════════════════════

_ANTHROPIC_BASE_URL = os.environ.get(
    "ANTHROPIC_BASE_URL", "https://api.anthropic.com"
)


class AnthropicAdapter:
    """Claude adapter via Anthropic SDK.

    By default uses ``ANTHROPIC_BASE_URL`` + ``ANTHROPIC_AUTH_TOKEN``
    (or ``DEEPSEEK_API_KEY``) from environment / .env.  Point
    ``ANTHROPIC_BASE_URL`` at a DeepSeek relay to use DeepSeek models
    through the Anthropic protocol.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        import anthropic

        self._api_key = (
            api_key
            or os.environ.get("ANTHROPIC_AUTH_TOKEN")
            or os.environ.get("DEEPSEEK_API_KEY")
        )
        if not self._api_key:
            raise ValueError(
                "Anthropic API key not found. Set ANTHROPIC_AUTH_TOKEN "
                "or DEEPSEEK_API_KEY in .env, or pass --api-key."
            )

        self._client = anthropic.Anthropic(
            api_key=self._api_key,
            base_url=base_url or _ANTHROPIC_BASE_URL,
        )
        self._default_model = os.environ.get(
            "ANTHROPIC_MODEL", "claude-sonnet-5"
        )

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        max_tokens: int = 16384,
    ) -> str:
        """Send prompt and return text response.

        Uses a high *max_tokens* default because reasoning models
        (DeepSeek-v4) spend tokens on internal thinking before producing
        text output.

        Streams the response: the SDK rejects non-streaming requests whose
        *max_tokens* could exceed the 10-minute ceiling, and large skills
        (many tasks) need that headroom. Streaming also avoids silent
        truncation of the JSON that caps the task count.
        """
        text_parts: list[str] = []
        with self._client.messages.stream(
            model=model or self._default_model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        ) as stream:
            for text in stream.text_stream:
                text_parts.append(text)
            final = stream.get_final_message()

        if not text_parts:
            # Reasoning models may exhaust token budget on thinking alone.
            thinking_len = sum(
                len(getattr(b, "thinking", "") or "")
                for b in final.content
            )
            raise RuntimeError(
                f"LLM produced no text output "
                f"(stop_reason={final.stop_reason}, "
                f"thinking_chars={thinking_len}). "
                f"Try increasing max_tokens (current={max_tokens})."
            )
        return "".join(text_parts)

    def research(
        self,
        topic: str,
        *,
        model: str | None = None,
        max_tokens: int = 8192,
    ) -> str:
        """Search the web and synthesize findings about *topic*.

        Uses the Anthropic web_search tool (relayed through DeepSeek).
        Returns a research summary suitable for injecting into a design prompt.
        """
        response = self._client.messages.create(
            model=model or self._default_model,
            max_tokens=max_tokens,
            system=(
                "You are a research assistant. Search the web to find "
                "established frameworks, best practices, canonical examples, "
                "expert methodologies, AND evaluation/scoring rubrics "
                "related to the topic. "
                "Synthesize your findings into a research brief covering:\n"
                "1. Key frameworks by name, core principles, notable works.\n"
                "2. How experts in this domain EVALUATE quality — what "
                "scoring rubrics, tier systems, or assessment criteria do "
                "they use? (e.g., in creative writing: publishers' manuscript "
                "evaluation forms; in code review: defect density thresholds; "
                "in design: heuristic evaluation scales.)\n"
                "3. What makes output 'good' vs 'excellent' in this domain — "
                "are there published benchmarks, competition criteria, or "
                "industry standards?\n"
                "This brief will be used by another AI to design a "
                "domain-specific Skill including its evaluation framework. "
                "Focus on actionable, NAMED methodologies — not generic advice."
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Research this topic thoroughly: {topic}\n\n"
                    "1. Find established frameworks, best practices, "
                    "canonical examples, and expert methodologies.\n"
                    "2. Find how experts EVALUATE and SCORE work in this "
                    "domain. Look for published rubrics, assessment criteria, "
                    "evaluation checklists, competition judging forms, "
                    "industry quality standards.\n"
                    "3. List specific names of frameworks, their core "
                    "principles, and how they're applied in practice."
                ),
            }],
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
            }],
        )
        text_blocks = [
            b.text for b in response.content if b.type == "text"
        ]
        if not text_blocks:
            raise RuntimeError("Research returned empty response")
        return "".join(text_blocks)


# ═══════════════════════════════════════════════════════════
# Adapter factory
# ═══════════════════════════════════════════════════════════

_ADAPTER_REGISTRY: dict[str, type] = {
    "deepseek": DeepSeekAdapter,
    "anthropic": AnthropicAdapter,
}


def create_adapter(model_spec: str, api_key: str | None = None) -> LLMAdapter:
    """Create an adapter from a ``provider/model`` spec string.

    >>> adapter = create_adapter("deepseek/deepseek-chat")
    >>> isinstance(adapter, DeepSeekAdapter)
    True
    """
    provider, sep, _model = model_spec.partition("/")
    if not sep:
        raise ValueError(
            f"Invalid model spec: '{model_spec}'. "
            f"Expected format: 'provider/model-name' "
            f"(e.g. 'deepseek/deepseek-chat')"
        )

    adapter_cls = _ADAPTER_REGISTRY.get(provider)
    if adapter_cls is None:
        valid = ", ".join(_ADAPTER_REGISTRY.keys())
        raise ValueError(
            f"Unknown provider: '{provider}'. "
            f"Available providers: {valid}"
        )

    return adapter_cls(api_key=api_key)
