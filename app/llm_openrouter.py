from __future__ import annotations
import httpx
import json
from typing import Any, Dict, List, Optional

class OpenRouterLLM:
    def __init__(self, api_key: str, model: str, app_title: str = "UniAgentBot"):
        self.api_key = api_key
        self.model = model
        self.app_title = app_title
        self.url = "https://openrouter.ai/api/v1/chat/completions"

    async def chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # optional but recommended by OpenRouter ecosystem
            "X-Title": self.app_title,
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(self.url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()

def extract_assistant_message(resp: Dict[str, Any]) -> Dict[str, Any]:
    # OpenAI-like schema: choices[0].message
    return resp["choices"][0]["message"]

def has_tool_calls(msg: Dict[str, Any]) -> bool:
    return bool(msg.get("tool_calls"))

def tool_calls(msg: Dict[str, Any]) -> List[Dict[str, Any]]:
    return msg.get("tool_calls", [])

def tool_message(tool_call_id: str, name: str, content: Any) -> Dict[str, Any]:
    # tool response message
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": name,
        "content": json.dumps(content, ensure_ascii=False),
    }
