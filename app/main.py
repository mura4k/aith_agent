# app/main.py
from __future__ import annotations

import asyncio
import json, re
from typing import Any, Dict, List, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from redis import Redis

from app.config import get_settings
from app.memory import RedisMemory
from app.llm_gigachat import (
    GigaChatLLM,
    extract_assistant_message,
    has_tool_calls,
    tool_calls,
    tool_message,
)
from app.sheets_client import SheetsClient
from app.tools import tool_schemas, ToolExecutor

SYSTEM_PROMPT = """Ты — университетский Telegram-агент для выбора элективов.
Твои обязанности:
- Вести диалог проактивно и собирать недостающие данные.
- Всегда проверять факты через tools (таблица/описания), не выдумывать.
- Никогда не раскрывать чужие данные: работай только в рамках текущей сессии.
- Запись в Google Sheet делай ТОЛЬКО после явного подтверждения пользователя.

ВАЖНО ПРО ССЫЛКУ:
- Я (система) сама извлекаю ссылку на Google Sheets и кладу в SESSION_STATE поле candidate_sheet_url.
- Ты обязан показать её пользователю и спросить подтверждение ("Это та ссылка? Да/Нет").
- confirm_sheet_link вызывай ТОЛЬКО если пользователь явно подтвердил.

ПРО TOOLS:
- Когда вызываешь tool, arguments ДОЛЖНЫ быть строго валидным JSON:
  * только двойные кавычки
  * никаких комментариев
  * никаких хвостовых запятых
  * только объект { ... } без дополнительного текста

Политика подтверждения записи:
- Перед write_selection ты обязан показать пользователю превью (prepare_write_preview)
  и спросить "Подтверждаете запись? (Да/Нет)".
- write_selection вызывай только если пользователь явно ответил "Да" / "подтверждаю" / "записывай".
"""

SHEET_URL_RE = re.compile(r"https?://docs\.google\.com/spreadsheets/[^\s)]+", re.IGNORECASE)


def user_key_from_message(msg: Message) -> str:
    return f"tg:{msg.from_user.id}"


def greeting(msg: Message) -> str:
    uname = msg.from_user.full_name or msg.from_user.username or "студент"
    return f"Привет, {uname}!"


def normalize_yes_no(text: str) -> str:
    t = (text or "").strip().lower()
    if t in {"да", "ага", "ок", "okay", "подтверждаю", "записывай", "согласен", "confirm", "yes"}:
        return "yes"
    if t in {"нет", "неа", "no", "cancel", "отмена", "не подтверждаю"}:
        return "no"
    return "unknown"


def extract_sheet_url(text: str) -> Optional[str]:
    m = SHEET_URL_RE.search(text or "")
    return m.group(0) if m else None


# -------- robust tool-args parsing (extract first JSON object + repairs) --------
def _extract_first_json_object(s: str) -> Optional[str]:
    s = s.strip()
    start = s.find("{")
    if start == -1:
        return None

    depth = 0
    in_str = False
    esc = False

    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        else:
            if ch == '"':
                in_str = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start : i + 1]
    return None


def safe_parse_tool_args(raw: str) -> Dict[str, Any]:
    if not raw:
        return {}

    candidate = raw.strip()

    first_obj = _extract_first_json_object(candidate)
    if first_obj:
        candidate = first_obj

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    s = candidate
    s = s.replace("“", '"').replace("”", '"').replace("’", "'")
    s = re.sub(r",\s*([}\]])", r"\1", s)
    s = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:\s*)", r'\1"\2"\3', s)
    # fix accidental double quote before http(s): ""https:// -> "https://
    s = re.sub(r'""(https?://)', r'"\1', s)

    if "'" in s and '"' not in s:
        s = s.replace("'", '"')

    first_obj2 = _extract_first_json_object(s)
    if first_obj2:
        s = first_obj2

    try:
        return json.loads(s)
    except json.JSONDecodeError:
        print("TOOL ARGUMENTS JSON PARSE FAILED (returning empty dict)")
        print("raw:", raw)
        print("candidate:", candidate)
        print("repaired:", s)
        return {}


# ---------------- agent loop ----------------
async def run_agent_turn(
    llm: GigaChatLLM,
    tools: ToolExecutor,
    memory: RedisMemory,
    user_key: str,
    user_text: str,
) -> str:
    state = memory.get_state(user_key)
    history = memory.get_history(user_key)

    if not history:
        history = [{"role": "system", "content": SYSTEM_PROMPT}]
        history.append(
            {
                "role": "assistant",
                "content": "Чтобы начать, пришлите/перешлите сообщение со ссылкой на таблицу выборности (Google Sheets).",
            }
        )
        memory.set_history(user_key, history)

    # Append the user's message
    history.append({"role": "user", "content": user_text})

    # Keep the state small: session hints only
    state_block = json.dumps(state, ensure_ascii=False)
    history.append({"role": "system", "content": f"SESSION_STATE_JSON: {state_block}"})

    # Ensure system message is at the top of the history (if not already)
    if history[0]["role"] != "system":
        history = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    tools_schema = tool_schemas()

    for _ in range(6):  # prevent infinite loops
        print(history)
        resp = await llm.chat(history, tools=tools_schema)
        msg = extract_assistant_message(resp)

        if has_tool_calls(msg):
            # Validate tool args BEFORE appending tool-calling assistant message.
            parsed_calls: List[tuple] = []
            bad = False

            for tc in tool_calls(msg):
                fn = tc["function"]["name"]
                raw_args = tc["function"].get("arguments", "")
                args = safe_parse_tool_args(raw_args)

                if not args:
                    bad = True
                    history.append(
                        {
                            "role": "system",
                            "content": (
                                f"Tool call '{fn}' had invalid JSON arguments. "
                                "Retry the SAME tool call with STRICT valid JSON arguments only."
                            ),
                        }
                    )
                    break

                parsed_calls.append((tc, fn, args))

            if bad:
                # Do NOT append broken assistant tool_calls; retry model.
                continue

            # Now it's safe to append assistant message containing tool_calls
            history.append(msg)

            # Execute tools
            for tc, fn, args in parsed_calls:
                tc_id = tc.get("id", "gc_tool_call_0")
                result = await tools.run(fn, args, state)
                result_dict = result.model_dump()

                # deterministic state updates
                if fn == "confirm_sheet_link" and result.ok and result.data.get("confirmed"):
                    state = memory.update_state(
                        user_key,
                        {
                            "sheet_url": result.data["sheet_url"],
                            "sheet_confirmed": True,
                            "candidate_sheet_url": None,
                        },
                    )

                if fn == "verify_student" and result.ok and result.data.get("found"):
                    state = memory.update_state(
                        user_key,
                        {
                            "student_display_name": result.data.get("display_name"),
                            "student_row_index": result.data.get("row_index"),
                            "student_verified": True,
                        },
                    )

                if fn == "prepare_write_preview" and result.ok:
                    state = memory.update_state(
                        user_key,
                        {
                            "pending_write_preview": result.data,
                            "awaiting_write_confirmation": True,
                        },
                    )

                if fn == "write_selection" and result.ok:
                    state = memory.update_state(
                        user_key,
                        {
                            "awaiting_write_confirmation": False,
                            "pending_write_preview": None,
                        },
                    )

                history.append(tool_message(tc_id, fn, result_dict))

            continue

        assistant_text = (msg.get("content") or "").strip()
        history.append({"role": "assistant", "content": assistant_text})
        memory.set_history(user_key, history)
        memory.set_state(user_key, state)
        return assistant_text

    history.append(
        {
            "role": "assistant",
            "content": "Я немного запутался. Пришлите ссылку на таблицу выборности ещё раз, пожалуйста.",
        }
    )
    memory.set_history(user_key, history)
    return "Я немного запутался. Пришлите ссылку на таблицу выборности ещё раз, пожалуйста."


# ---------------- bot wiring ----------------
async def main():
    settings = get_settings()

    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    memory = RedisMemory(redis)

    sheets = SheetsClient(settings.google_sa_json)
    tool_exec = ToolExecutor(sheets)

    llm = GigaChatLLM(
        api_key=settings.gigachat_api_key,
        model=settings.gigachat_model,
        base_url=settings.gigachat_base_url,
    )

    @dp.message(Command("start"))
    async def start(m: Message):
        uk = user_key_from_message(m)
        memory.reset(uk)
        await m.answer(greeting(m) + "\n\nПришлите ссылку на таблицу выборности (Google Sheets).")

    @dp.message(Command("reset"))
    async def reset(m: Message):
        uk = user_key_from_message(m)
        memory.reset(uk)
        await m.answer("Ок, сбросила сессию. Пришли ссылку на таблицу выборности.")

    @dp.message(F.text)
    async def handle_text(m: Message):
        uk = user_key_from_message(m)
        user_text = m.text or ""

        # Deterministically extract candidate sheet URL and store in state
        url = extract_sheet_url(user_text)
        if url:
            memory.update_state(uk, {"candidate_sheet_url": url})

        # If awaiting write confirmation, store last yes/no (optional hint)
        state = memory.get_state(uk)
        if state.get("awaiting_write_confirmation"):
            yn = normalize_yes_no(user_text)
            if yn in {"yes", "no"}:
                memory.update_state(uk, {"last_write_confirmation": yn})

        reply = await run_agent_turn(llm, tool_exec, memory, uk, user_text)
        await m.answer(reply)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())