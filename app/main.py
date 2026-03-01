from __future__ import annotations
import asyncio
import json
from typing import Any, Dict, List

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
from redis import Redis

from app.config import get_settings
from app.memory import RedisMemory
from app.llm_openrouter import OpenRouterLLM, extract_assistant_message, has_tool_calls, tool_calls, tool_message
from app.sheets_client import SheetsClient
from app.tools import tool_schemas, ToolExecutor

SYSTEM_PROMPT = """Ты — университетский Telegram-агент для выбора элективов.
Твои обязанности:
- Вести диалог проактивно и собирать недостающие данные.
- Всегда проверять факты через tools (таблица/описания), не выдумывать.
- Никогда не раскрывать чужие данные: работай только в рамках текущей сессии.
- Запись в Google Sheet делай ТОЛЬКО после явного подтверждения пользователя.

Политика подтверждения:
- Перед write_selection ты обязан показать пользователю краткий превью-план (prepare_write_preview)
  и спросить "Подтверждаете запись? (Да/Нет)".
- write_selection вызывай только если пользователь явно ответил "Да" / "подтверждаю" / "записывай".

Что нужно уметь:
1) Пользователь пересылает сообщение — найди ссылку на Google Sheets и попроси подтвердить.
2) После подтверждения — запроси имя или табельный номер.
3) Верифицируй пользователя по таблице.
4) Покажи доступные курсы: название, зач.ед., преподаватель. Посчитай, сколько ещё можно добрать.
5) На вопросы про преподавателя/описание — отвечай из таблицы/ссылок.
6) На запрос рекомендации — кратко предложи 1-3 курса и почему они подходят, используя данные.
"""

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

async def run_agent_turn(
    llm: OpenRouterLLM,
    tools: ToolExecutor,
    memory: RedisMemory,
    user_key: str,
    user_text: str,
) -> str:
    # Load session
    state = memory.get_state(user_key)
    history = memory.get_history(user_key)

    if not history:
        history = [{"role": "system", "content": SYSTEM_PROMPT}]
        # Optional greeting hint
        history.append({"role": "assistant", "content": "Чтобы начать, перешлите сообщение со ссылкой на таблицу выборности (Google Sheets)."})
        memory.set_history(user_key, history)

    # Add user message
    history.append({"role": "user", "content": user_text})

    # A small “session state” injection: LLM sees what we already know
    state_block = json.dumps(state, ensure_ascii=False)
    history.append({
        "role": "system",
        "content": f"SESSION_STATE_JSON: {state_block}"
    })

    # Tool loop
    tools_schema = tool_schemas()
    for _ in range(6):  # prevent infinite loops
        resp = await llm.chat(history, tools=tools_schema)
        msg = extract_assistant_message(resp)

        if has_tool_calls(msg):
            # Save assistant message (with tool calls)
            history.append(msg)

            for tc in tool_calls(msg):
                tc_id = tc["id"]
                fn = tc["function"]["name"]
                args = json.loads(tc["function"].get("arguments", "{}"))

                result = await tools.run(fn, args, state)
                result_dict = result.model_dump()

                # Update state on certain tool results (we keep it deterministic in code)
                if fn == "confirm_sheet_link" and result.ok and result.data.get("confirmed"):
                    state = memory.update_state(user_key, {
                        "sheet_url": result.data["sheet_url"],
                        "sheet_confirmed": True,
                    })

                if fn == "verify_student" and result.ok and result.data.get("found"):
                    state = memory.update_state(user_key, {
                        "student_display_name": result.data.get("display_name"),
                        "student_row_index": result.data.get("row_index"),
                        "student_verified": True,
                    })

                if fn == "prepare_write_preview" and result.ok:
                    state = memory.update_state(user_key, {
                        "pending_write_preview": result.data,
                        "awaiting_write_confirmation": True,
                    })

                if fn == "write_selection" and result.ok:
                    # write done, clear pending confirmation
                    state = memory.update_state(user_key, {
                        "awaiting_write_confirmation": False,
                        "pending_write_preview": None,
                    })

                history.append(tool_message(tc_id, fn, result_dict))

            continue

        # No tools → final assistant text for this turn
        assistant_text = msg.get("content", "").strip()

        # Save final assistant msg & state/history
        history.append({"role": "assistant", "content": assistant_text})
        memory.set_history(user_key, history)
        memory.set_state(user_key, state)
        return assistant_text

    # If loop exhausted
    history.append({"role": "assistant", "content": "Я немного запутался в шагах. Давайте начнём заново: пришлите ссылку на таблицу выборности."})
    memory.set_history(user_key, history)
    return "Я немного запутался в шагах. Давайте начнём заново: пришлите ссылку на таблицу выборности."

async def main():
    settings = get_settings()

    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    memory = RedisMemory(redis)
    sheets = SheetsClient(settings.google_sa_json)
    tool_exec = ToolExecutor(sheets)

    llm = OpenRouterLLM(
        api_key=settings.openrouter_api_key,
        model=settings.openrouter_model,
        app_title="UniAgentBot",
    )

    @dp.message(Command("start"))
    async def start(m: Message):
        uk = user_key_from_message(m)
        memory.reset(uk)
        await m.answer(greeting(m) + "\n\nПерешли сообщение со ссылкой на таблицу выборности (Google Sheets).")

    @dp.message(Command("reset"))
    async def reset(m: Message):
        uk = user_key_from_message(m)
        memory.reset(uk)
        await m.answer("Ок, сбросила сессию. Пришли ссылку на таблицу выборности.")

    @dp.message(F.text)
    async def handle_text(m: Message):
        uk = user_key_from_message(m)
        user_text = m.text or ""

        # Optional: if we are awaiting confirmation, we can help LLM by putting a hint in state
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