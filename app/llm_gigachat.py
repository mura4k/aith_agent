import requests
import json
import urllib3
from typing import Any, Dict, List, Optional

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class GigaChatLLM:
    """
    GigaChat API LLM with Bearer Token authentication.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "GigaChat",  # Default model
        base_url: str = "https://gigachat.devices.sberbank.ru/api/v1",
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def get_models(self) -> Dict:
        """
        Fetch available models from the GigaChat API.
        """
        url = f"{self.base_url}/models"
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
        }
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Error fetching models: {response.status_code}, {response.text}")

    def chat(self, messages: List[Dict[str, str]], tools: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """
        Send a request to GigaChat API for chat completion with tools.
        """
        chat_url = f"{self.base_url}/chat/completions"
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.api_key}',  # Using Bearer token
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "functions": tools if tools else [],  # Handle tools if they exist
            "n": 1,  # Number of completions
            "stream": False,  # Disable streaming
            "max_tokens": 512,  # Max tokens for the response
        }

        response = requests.post(chat_url, headers=headers, json=payload, verify=False)

        if response.status_code == 200:
            return response.json()  # Return chat completion response
        else:
            raise Exception(f"Error in chat completion: {response.status_code}, {response.text}")

def extract_assistant_message(resp: Dict[str, Any]) -> Dict[str, Any]:
    return resp["choices"][0]["message"]

def has_tool_calls(msg: Dict[str, Any]) -> bool:
    return bool(msg.get("tool_calls"))

def tool_calls(msg: Dict[str, Any]) -> List[Dict[str, Any]]:
    return msg.get("tool_calls", [])

def tool_message(tool_call_id: str, name: str, content: Any) -> Dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": name,
        "content": json.dumps(content, ensure_ascii=False),
    }