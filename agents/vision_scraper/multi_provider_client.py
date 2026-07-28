"""Multi-provider AI client for vision-guided scraping."""

import os
import json
import base64
import time
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

# UI-TARS style tool definitions for function calling
UI_TARS_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Click at specified coordinates on the screen",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "number", "description": "X coordinate (0-1920)"},
                    "y": {"type": "number", "description": "Y coordinate (0-1080)"},
                    "reasoning": {"type": "string", "description": "Why clicking here"}
                },
                "required": ["x", "y", "reasoning"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "type",
            "description": "Type text at specified coordinates",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "number", "description": "X coordinate of input field"},
                    "y": {"type": "number", "description": "Y coordinate of input field"},
                    "text": {"type": "string", "description": "Text to type"},
                    "reasoning": {"type": "string", "description": "Why typing here"}
                },
                "required": ["x", "y", "text", "reasoning"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "Scroll the page up or down",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down"], "description": "Scroll direction"},
                    "amount": {"type": "number", "description": "Pixels to scroll (default 500)"},
                    "reasoning": {"type": "string", "description": "Why scrolling"}
                },
                "required": ["direction", "reasoning"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Wait for page to load",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration": {"type": "number", "description": "Seconds to wait"},
                    "reasoning": {"type": "string", "description": "Why waiting"}
                },
                "required": ["duration", "reasoning"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "goal_achieved",
            "description": "Call when the navigation goal is achieved",
            "parameters": {
                "type": "object",
                "properties": {
                    "reasoning": {"type": "string", "description": "Why goal is achieved"}
                },
                "required": ["reasoning"]
            }
        }
    }
]


class MultiProviderAIClient:
    """Client for multiple AI vision providers with automatic fallback."""

    def __init__(self, rate_limiter=None):
        self._rate_limiter = rate_limiter
        self._mistral_api_key = os.getenv("MISTRAL_API_KEY")
        self._gemini_api_key = os.getenv("GEMINI_API_KEY")
        self._nvidia_api_key = os.getenv("NVIDIA_API_KEY")
        self._max_retries = 2

    def _encode_image_to_base64(self, image_data: bytes) -> str:
        """Encode image bytes to base64 string."""
        return base64.b64encode(image_data).decode("utf-8")

    def _parse_json_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON from response text, handling markdown code blocks."""
        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())

    def _call_nvidia_vision(self, image_b64: str, prompt: str, model: str = "meta/llama-3.2-90b-vision-instruct") -> Dict[str, Any]:
        """Call NVIDIA API for vision analysis (supports Llama vision models)."""
        from openai import AsyncOpenAI
        
        client = AsyncOpenAI(
            api_key=self._nvidia_api_key,
            base_url="https://integrate.api.nvidia.com/v1",
        )
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            }
        ]
        
        # Run async in sync context
        import asyncio
        response = asyncio.run(
            client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
                max_tokens=200,
            )
        )
        return {"provider": "nvidia", "text": response.choices[0].message.content}

    def _call_mistral_function(
        self, 
        image_b64: str, 
        prompt: str, 
        model: str = "ministral-14b-latest"
    ) -> Dict[str, Any]:
        """Call Mistral API with UI-TARS style function calling."""
        if not self._mistral_api_key:
            raise RuntimeError("MISTRAL_API_KEY not configured")
        from mistralai import Mistral

        client = Mistral(api_key=self._mistral_api_key)
        messages = [
            {
                "role": "system",
                "content": "You are a UI navigation agent. Analyze the screenshot and call the appropriate tool to navigate towards the goal."
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": f"data:image/jpeg;base64,{image_b64}",
                    },
                ],
            }
        ]
        response = client.chat.complete(
            model=model,
            messages=messages,
            tools=UI_TARS_TOOLS,
            tool_choice="auto",
        )
        
        # Extract tool call
        message = response.choices[0].message
        if message.tool_calls:
            tool_call = message.tool_calls[0]
            return {
                "provider": "mistral",
                "tool_name": tool_call.function.name,
                "arguments": json.loads(tool_call.function.arguments),
            }
        else:
            # Fallback to text if no tool call
            return {
                "provider": "mistral",
                "tool_name": "error",
                "arguments": {"reasoning": message.content or "No tool call generated"},
            }

    def _call_mistral(self, image_b64: str, prompt: str, model: str = "pixtral-12b") -> Dict[str, Any]:
        """Call Mistral Pixtral API for vision analysis (legacy JSON mode)."""
        if not self._mistral_api_key:
            raise RuntimeError("MISTRAL_API_KEY not configured")
        from mistralai import Mistral

        client = Mistral(api_key=self._mistral_api_key)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": f"data:image/jpeg;base64,{image_b64}",
                    },
                ],
            }
        ]
        response = client.chat.complete(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
        )
        return {"provider": "mistral", "text": response.choices[0].message.content}

    def _call_gemini(self, image_b64: str, prompt: str, model: str = "gemini-2.0-flash") -> Dict[str, Any]:
        """Call Google Gemini API for vision analysis."""
        import google.generativeai as genai

        genai.configure(api_key=self._gemini_api_key)
        model_instance = genai.GenerativeModel(model)
        import io
        from PIL import Image

        image = Image.open(io.BytesIO(base64.b64decode(image_b64)))
        response = model_instance.generate_content([prompt, image])
        return {"provider": "gemini", "text": response.text}

    def vision_complete(
        self,
        image: bytes,
        prompt: str,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        use_function_calling: bool = True,
    ) -> Dict[str, Any]:
        """
        Call vision API with automatic provider selection and fallback.
        
        Args:
            image: Image bytes
            prompt: Vision prompt
            model: Specific model to use
            provider: Force specific provider ('mistral', 'nvidia', or 'gemini')
            use_function_calling: Use UI-TARS style function calling (Mistral only)
            
        Returns:
            Parsed response dict
        """
        image_b64 = self._encode_image_to_base64(image)
        
        # Provider priority: forced -> nvidia (if available) -> mistral -> gemini
        providers_to_try = []
        if provider:
            providers_to_try = [provider]
        else:
            # NVIDIA first (you have this key)
            if self._nvidia_api_key:
                providers_to_try = ["nvidia"]
            elif use_function_calling and self._mistral_api_key:
                providers_to_try = ["mistral"]
            providers_to_try.extend(["gemini"])
        
        seen = []
        for p in providers_to_try:
            if p not in seen:
                seen.append(p)
        
        last_error = None
        for p in seen:
            if self._rate_limiter and not self._rate_limiter.check_availability(p):
                continue
                
            for attempt in range(self._max_retries + 1):
                try:
                    if p == "nvidia":
                        result = self._call_nvidia_vision(image_b64, prompt, model or "meta/llama-3.2-90b-vision-instruct")
                    elif p == "mistral":
                        result = self._call_mistral(image_b64, prompt, model or "pixtral-12b")
                    elif p == "gemini":
                        result = self._call_gemini(image_b64, prompt, model or "gemini-2.0-flash")
                    else:
                        continue
                    
                    if self._rate_limiter:
                        self._rate_limiter.record_request(p)
                    
                    if "text" in result:
                        return {**result, "parsed": self._parse_json_response(result["text"])}
                    return result
                    
                except Exception as e:
                    last_error = str(e)
                    if attempt < self._max_retries:
                        time.sleep(2 ** attempt)
                    continue
        
        raise RuntimeError(f"All providers failed. Last error: {last_error}")
