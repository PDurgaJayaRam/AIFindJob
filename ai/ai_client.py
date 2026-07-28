"""Multi-provider AI client with fallback support."""
import os
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
import httpx
from openai import AsyncOpenAI
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")


class AIClient:
    """Unified AI client supporting NVIDIA, OpenAI, DeepSeek, and Anthropic."""

    def __init__(self, provider: Optional[str] = None):
        self.provider = (provider or os.getenv("PRIMARY_AI_PROVIDER", "nvidia")).lower()

        self.clients: Dict[str, Any] = {}

        # NVIDIA / OpenAI / DeepSeek compatible (all OpenAI SDK)
        nvidia_key = os.getenv("NVIDIA_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")

        if nvidia_key:
            self.clients["nvidia"] = AsyncOpenAI(
                api_key=nvidia_key,
                base_url="https://integrate.api.nvidia.com/v1",
            )
        if openai_key:
            self.clients["openai"] = AsyncOpenAI(api_key=openai_key)
        if deepseek_key:
            self.clients["deepseek"] = AsyncOpenAI(
                api_key=deepseek_key,
                base_url="https://api.deepseek.com/v1",
            )
        if anthropic_key:
            try:
                from anthropic import AsyncAnthropic
                self.clients["anthropic"] = AsyncAnthropic(api_key=anthropic_key)
            except ImportError:
                pass

        # Mistral (direct SDK)
        mistral_key = os.getenv("MISTRAL_API_KEY")
        if mistral_key:
            try:
                from mistralai import Mistral
                self.clients["mistral"] = Mistral(api_key=mistral_key, timeout_ms=300000)
            except ImportError:
                pass

        all_providers = ["mistral", "nvidia", "deepseek", "openai", "anthropic"]
        self._fallback_order = [self.provider] + [p for p in all_providers if p != self.provider and p in self.clients]

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        json_mode: bool = False,
    ) -> str:
        errors = []
        for provider in self._fallback_order:
            try:
                return await self._call_provider(provider, messages, model, temperature, max_tokens, json_mode)
            except Exception as e:
                errors.append(f"{provider}: {e}")
                await asyncio.sleep(0.5)
        raise RuntimeError(f"All AI providers failed: {'; '.join(errors)}")

    async def _call_provider(
        self,
        provider: str,
        messages: List[Dict[str, str]],
        model: Optional[str],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> str:
        client = self.clients[provider]

        if provider == "anthropic":
            system_msg = ""
            user_msgs = []
            for m in messages:
                if m["role"] == "system":
                    system_msg = m["content"]
                else:
                    user_msgs.append({"role": m["role"], "content": m["content"]})
            resp = await client.messages.create(
                model=model or "claude-3-haiku-20240307",
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_msg or "You are a helpful assistant.",
                messages=user_msgs,
            )
            return resp.content[0].text

        # NVIDIA / OpenAI / DeepSeek
        default_model = {
            "mistral": "mistral-large-latest",
            "nvidia": "meta/llama-3.1-8b-instruct",
            "deepseek": "deepseek-chat",
            "openai": "gpt-4o-mini",
        }.get(provider, "meta/llama-3.1-8b-instruct")

        kwargs = {
            "model": model or default_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        # NVIDIA specific params
        if provider == "nvidia":
            # step-3.5-flash is a general chat model, no special vision handling needed
            pass
        elif json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        resp = await client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content
        if not content or not content.strip():
            raise RuntimeError(f"{provider} returned empty response")
        # Strip markdown code blocks if present (NVIDIA returns ```json ... ```)
        content = content.strip()
        if content.startswith("```"):
            # Remove opening ```json or ``` marker
            first_newline = content.find("\n")
            if first_newline > 0:
                content = content[first_newline + 1:]
            # Remove closing ```
            if content.endswith("```"):
                content = content[:-3].strip()
        # Extract JSON if model returned extra text
        if json_mode:
            # Try array first, then object
            first_bracket = content.find("[")
            first_brace = content.find("{")
            if first_bracket >= 0 and (first_brace < 0 or first_bracket < first_brace):
                # Array
                last_bracket = content.rfind("]")
                if last_bracket > first_bracket:
                    content = content[first_bracket:last_bracket + 1]
            elif first_brace >= 0:
                # Object
                last_brace = content.rfind("}")
                if last_brace > first_brace:
                    content = content[first_brace:last_brace + 1]
        return content


# Global singleton
_ai_client: Optional[AIClient] = None


def get_ai_client() -> AIClient:
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient()
    return _ai_client
