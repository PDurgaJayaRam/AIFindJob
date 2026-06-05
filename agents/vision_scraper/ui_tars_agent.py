"""
UI-TARS Agent - Enhanced with NVIDIA NIM free vision models.
Can do ANY task: scrape jobs, apply to jobs, fill forms, click buttons, etc.
Uses free NVIDIA NIM endpoints (no API cost).
"""

import os
import re
import time
import json
import base64
import logging
import requests
from typing import List, Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# ─── NVIDIA NIM Free Vision Models ────────────────────────────────────────────
# All these are FREE on NVIDIA NIM (build.nvidia.com)
NVIDIA_NIM_MODELS = {
    # Best for GUI agent tasks (vision + reasoning)
    "llama-3.2-90b-vision-instruct": {
        "name": "Llama 3.2 90B Vision",
        "description": "Best quality, 90B params, excellent GUI understanding",
        "endpoint": "https://integrate.api.nvidia.com/v1/chat/completions",
        "max_tokens": 1000,
    },
    "llama-3.2-11b-vision-instruct": {
        "name": "Llama 3.2 11B Vision",
        "description": "Good quality, faster, 11B params",
        "endpoint": "https://integrate.api.nvidia.com/v1/chat/completions",
        "max_tokens": 1000,
    },
    "cosmos3-nano-reasoner": {
        "name": "Cosmos3 Nano Reasoner",
        "description": "NVIDIA's own, great for physical world understanding",
        "endpoint": "https://integrate.api.nvidia.com/v1/chat/completions",
        "max_tokens": 1000,
    },
}

# Default model (best free option)
DEFAULT_MODEL = "llama-3.2-90b-vision-instruct"

# ─── UI-TARS System Prompt ────────────────────────────────────────────────────
UI_TARS_SYSTEM_PROMPT = """You are a powerful GUI agent. You can see the screen and perform any task on a computer.

You are given a task and your action history, with screenshots. You need to perform the next action to complete the task.

## Output Format
Thought: [Your reasoning about what you see and what to do next]
Action: [The exact action to take]

## Action Space
click(point='<point>x1 y1</point>')  - Click at coordinates (x,y in pixels)
type(content='xxx')  - Type text into focused element
scroll(direction='down')  - Scroll up or down
wait()  - Wait for page to load
hotkey(key='enter')  - Press keyboard shortcut
finished()  - Task is complete
goto(url='https://...')  - Navigate to URL
extract_data()  - Extract visible text/data from page
screenshot()  - Take a screenshot for analysis

## Important Rules
- Coordinates are in pixels (0-1920 for x, 0-1080 for y typically)
- Always think step by step before acting
- If you see a search box, type the query then click search
- If you see a form, fill it field by field
- If you see a button that advances the task, click it
- If the task is completed, return finished()
- DO NOT use markdown code blocks. Output plain text only.
- Be precise with coordinates - look at the screenshot carefully
"""


class UITarsAgent:
    """
    Enhanced UI-TARS Agent using NVIDIA NIM free vision models.
    
    Can perform ANY computer task:
    - Scrape job listings from portals
    - Apply to jobs (fill forms, upload resume)
    - Navigate websites
    - Fill out applications
    - Click buttons, links
    - Extract data from pages
    - And much more...
    
    Usage:
        agent = UITarsAgent(browser, nvidia_api_key)
        result = await agent.run("Go to naukri.com and apply to Java Developer jobs")
    """

    def __init__(
        self,
        browser_controller,
        nvidia_api_key: str = None,
        model: str = None,
        max_steps: int = 30,
    ):
        self.browser = browser_controller
        self.nvidia_api_key = nvidia_api_key or os.getenv("NVIDIA_API_KEY", "")
        self.model = model or DEFAULT_MODEL
        self.max_steps = max_steps
        self._history: List[Dict] = []
        self._viewport_width = 1400
        self._viewport_height = 900
        
        if not self.nvidia_api_key:
            logger.warning("No NVIDIA API key provided. Set NVIDIA_API_KEY env var.")

    def _call_nvidia_nim(self, screenshot_b64: str, task: str, history_text: str) -> str:
        """Call NVIDIA NIM vision model with UI-TARS prompt."""
        
        model_config = NVIDIA_NIM_MODELS.get(self.model, NVIDIA_NIM_MODELS[DEFAULT_MODEL])
        
        user_content = f"Task: {task}"
        if history_text:
            user_content += f"\n\nAction History:\n{history_text}"
        
        messages = [
            {
                "role": "system",
                "content": UI_TARS_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_content},
                    {
                        "type": "image_url",
                        "image_url": f"data:image/jpeg;base64,{screenshot_b64}",
                    },
                ],
            }
        ]
        
        headers = {
            "Authorization": f"Bearer {self.nvidia_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": model_config["max_tokens"],
            "temperature": 0.1,  # Low temperature for precise actions
            "top_p": 0.9,
        }
        
        try:
            response = requests.post(
                model_config["endpoint"],
                headers=headers,
                json=payload,
                timeout=90,
            )
            
            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"]
            elif response.status_code == 429:
                logger.warning("NVIDIA NIM rate limited. Waiting 5 seconds...")
                time.sleep(5)
                return self._call_nvidia_nim(screenshot_b64, task, history_text)
            else:
                raise Exception(f"NVIDIA NIM API error: {response.status_code} - {response.text}")
                
        except requests.exceptions.Timeout:
            raise Exception("NVIDIA NIM API timeout. Try again.")
        except requests.exceptions.ConnectionError:
            raise Exception("Cannot connect to NVIDIA NIM. Check internet connection.")

    def _clean_response(self, text: str) -> str:
        """Remove markdown code blocks and clean response."""
        text = re.sub(r'```\w*\n', '', text)
        text = text.replace('```', '')
        return text.strip()

    def _parse_action(self, response_text: str) -> Dict[str, Any]:
        """Parse UI-TARS action response."""
        text = self._clean_response(response_text)
        
        # Extract Thought and Action
        thought_match = re.search(r'Thought:\s*(.+?)(?=Action:|$)', text, re.DOTALL)
        action_match = re.search(r'Action:\s*(.+?)(?:\n|$)', text)
        
        thought = thought_match.group(1).strip() if thought_match else ""
        action = action_match.group(1).strip() if action_match else ""
        
        if not action:
            return {"action_type": "error", "error": "No action found", "thought": thought}
        
        # Parse action type and parameters
        if action.startswith("click("):
            # Extract coordinates: click(point='<point>500 400</point>') or click(point='500 400')
            coord_match = re.search(r"point='[^']*?(\d+)\s+(\d+)[^']*?'", action)
            if coord_match:
                x = int(coord_match.group(1))
                y = int(coord_match.group(2))
                # Normalize to 0-1 scale
                norm_x = x / self._viewport_width
                norm_y = y / self._viewport_height
                return {
                    "action_type": "click",
                    "action_inputs": {"start_box": [norm_x, norm_y]},
                    "thought": thought,
                }
        
        elif action.startswith("type("):
            content_match = re.search(r"content='([^']+)'", action)
            if content_match:
                return {
                    "action_type": "type",
                    "action_inputs": {"content": content_match.group(1)},
                    "thought": thought,
                }
        
        elif action.startswith("scroll("):
            direction_match = re.search(r"direction='(\w+)'", action)
            if direction_match:
                return {
                    "action_type": "scroll",
                    "action_inputs": {"direction": direction_match.group(1)},
                    "thought": thought,
                }
        
        elif action.startswith("hotkey("):
            key_match = re.search(r"key='([^']+)'", action)
            if key_match:
                return {
                    "action_type": "hotkey",
                    "action_inputs": {"key": key_match.group(1)},
                    "thought": thought,
                }
        
        elif action.startswith("goto("):
            url_match = re.search(r"url='([^']+)'", action)
            if url_match:
                return {
                    "action_type": "goto",
                    "action_inputs": {"url": url_match.group(1)},
                    "thought": thought,
                }
        
        elif action.startswith("finished("):
            return {
                "action_type": "finished",
                "action_inputs": {},
                "thought": thought,
            }
        
        elif action.startswith("extract_data("):
            return {
                "action_type": "extract_data",
                "action_inputs": {},
                "thought": thought,
            }
        
        elif action.startswith("screenshot("):
            return {
                "action_type": "screenshot",
                "action_inputs": {},
                "thought": thought,
            }
        
        elif action.startswith("wait("):
            return {
                "action_type": "wait",
                "action_inputs": {},
                "thought": thought,
            }
        
        return {"action_type": "unknown", "action": action, "thought": thought}

    async def _execute_action(self, parsed: Dict) -> bool:
        """Execute a parsed action on the browser. Returns True if successful."""
        action_type = parsed.get("action_type")
        inputs = parsed.get("action_inputs", {})
        
        try:
            if action_type == "click":
                x, y = inputs.get("start_box", [0, 0])
                # Convert normalized coordinates to pixels
                pixel_x = int(x * self._viewport_width)
                pixel_y = int(y * self._viewport_height)
                await self.browser.click_at(pixel_x, pixel_y)
                logger.info(f"Clicked at ({pixel_x}, {pixel_y})")
                return True
                
            elif action_type == "type":
                content = inputs.get("content", "")
                await self.browser.type_text(content)
                logger.info(f"Typed: {content[:50]}...")
                return True
                
            elif action_type == "scroll":
                direction = inputs.get("direction", "down")
                await self.browser.scroll(direction)
                logger.info(f"Scrolled {direction}")
                return True
                
            elif action_type == "hotkey":
                key = inputs.get("key", "enter")
                await self.browser.press_key(key)
                logger.info(f"Pressed key: {key}")
                return True
                
            elif action_type == "goto":
                url = inputs.get("url", "")
                await self.browser.go_to(url)
                logger.info(f"Navigated to: {url}")
                return True
                
            elif action_type == "extract_data":
                data = await self.browser.get_page_text()
                logger.info(f"Extracted {len(data)} chars of text")
                return True
                
            elif action_type == "screenshot":
                # Screenshot is taken automatically in the loop
                return True
                
            elif action_type == "wait":
                import asyncio
                await asyncio.sleep(2)
                return True
                
            elif action_type == "finished":
                return True
                
            else:
                logger.warning(f"Unknown action type: {action_type}")
                return False
                
        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return False

    async def run(self, task: str, callback=None) -> Dict[str, Any]:
        """
        Run a task using the UI-TARS agent.
        
        Args:
            task: Natural language task description
            callback: Optional callback function(action_num, thought, action_type)
            
        Returns:
            Dict with status, steps taken, and results
        """
        logger.info(f"Starting UI-TARS task: {task}")
        
        self._history = []
        start_time = time.time()
        
        for step in range(1, self.max_steps + 1):
            logger.info(f"Step {step}/{self.max_steps}")
            
            try:
                # Take screenshot
                screenshot_b64 = await self.browser.take_screenshot()
                
                if not screenshot_b64:
                    logger.error("Failed to take screenshot")
                    continue
                
                # Build history text
                history_text = ""
                for h in self._history[-5:]:  # Last 5 actions
                    history_text += f"Step {h['step']}: {h['thought']} -> {h['action_type']}\n"
                
                # Call NVIDIA NIM
                response_text = self._call_nvidia_nim(screenshot_b64, task, history_text)
                logger.info(f"AI Response: {response_text[:200]}...")
                
                # Parse action
                parsed = self._parse_action(response_text)
                action_type = parsed.get("action_type", "unknown")
                thought = parsed.get("thought", "")
                
                # Callback
                if callback:
                    callback(step, thought, action_type)
                
                # Store in history
                self._history.append({
                    "step": step,
                    "thought": thought,
                    "action_type": action_type,
                    "action_inputs": parsed.get("action_inputs", {}),
                })
                
                # Check if finished
                if action_type == "finished":
                    elapsed = time.time() - start_time
                    return {
                        "status": "success",
                        "steps": step,
                        "elapsed_seconds": round(elapsed, 1),
                        "history": self._history,
                    }
                
                # Execute action
                success = await self._execute_action(parsed)
                
                if not success:
                    logger.warning(f"Action failed: {action_type}")
                
                # Wait between actions
                import asyncio
                await asyncio.sleep(1.5)
                
            except Exception as e:
                logger.error(f"Step {step} error: {e}")
                # Continue to next step
        
        elapsed = time.time() - start_time
        return {
            "status": "timeout",
            "steps": self.max_steps,
            "elapsed_seconds": round(elapsed, 1),
            "history": self._history,
        }


# ─── Convenience Function ─────────────────────────────────────────────────────

async def run_task(
    browser_controller,
    task: str,
    nvidia_api_key: str = None,
    model: str = None,
    max_steps: int = 30,
    callback=None,
) -> Dict[str, Any]:
    """
    Run a task with the UI-TARS agent.
    
    Example:
        result = await run_task(
            browser,
            "Go to naukri.com, search for Java Developer jobs in Hyderabad, and extract the first 10 job listings"
        )
    """
    agent = UITarsAgent(
        browser_controller=browser_controller,
        nvidia_api_key=nvidia_api_key,
        model=model,
        max_steps=max_steps,
    )
    return await agent.run(task, callback=callback)


# ─── Predefined Tasks ─────────────────────────────────────────────────────────

PREDEFINED_TASKS = {
    "scrape_naukri": "Go to naukri.com, search for {keywords} jobs in {location}, and extract all job listings with title, company, salary, and apply link",
    
    "scrape_linkedin": "Go to linkedin.com/jobs, search for {keywords} in {location}, and extract job listings",
    
    "scrape_indeed": "Go to indeed.com, search for {keywords} jobs in {location}, and extract job listings",
    
    "apply_job": "Go to {job_url}, click Apply Now, fill the application form with my details, and submit",
    
    "fill_form": "Fill the form on this page with: name={name}, email={email}, phone={phone}, resume={resume_path}",
    
    "extract_jobs": "Extract all job listings visible on this page with title, company, location, salary, and apply link",
    
    "click_apply": "Find and click the Apply Now or Easy Apply button on this page",
    
    "navigate_and_search": "Go to {url}, find the search box, type '{query}', and click search",
}
