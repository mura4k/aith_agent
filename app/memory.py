from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
from redis import Redis

Message = Dict[str, Any]  # {"role": "...", "content": "..."} + optional tool fields

class RedisMemory:
    """
    Per-user memory. user_key = f"tg:{telegram_user_id}"
    Stores:
      - chat history (list of messages)
      - structured session state (json)
    """
    def __init__(self, redis: Redis, ttl_seconds: int = 60 * 60 * 24 * 14):
        self.r = redis
        self.ttl = ttl_seconds

    def _k_hist(self, user_key: str) -> str:
        return f"{user_key}:hist"

    def _k_state(self, user_key: str) -> str:
        return f"{user_key}:state"

    def get_history(self, user_key: str) -> List[Message]:
        raw = self.r.get(self._k_hist(user_key))
        if not raw:
            return []
        return json.loads(raw)

    def set_history(self, user_key: str, history: List[Message]) -> None:
        self.r.set(self._k_hist(user_key), json.dumps(history, ensure_ascii=False))
        self.r.expire(self._k_hist(user_key), self.ttl)

    def append(self, user_key: str, message: Message) -> None:
        hist = self.get_history(user_key)
        hist.append(message)
        self.set_history(user_key, hist)

    def get_state(self, user_key: str) -> Dict[str, Any]:
        raw = self.r.get(self._k_state(user_key))
        if not raw:
            return {}
        return json.loads(raw)

    def set_state(self, user_key: str, state: Dict[str, Any]) -> None:
        self.r.set(self._k_state(user_key), json.dumps(state, ensure_ascii=False))
        self.r.expire(self._k_state(user_key), self.ttl)

    def update_state(self, user_key: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        state = self.get_state(user_key)
        state.update(patch)
        self.set_state(user_key, state)
        return state

    def reset(self, user_key: str) -> None:
        self.r.delete(self._k_hist(user_key))
        self.r.delete(self._k_state(user_key))
        