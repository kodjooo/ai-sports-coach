"""Умный чат с тренером: память диалога (окно+резюме), контекст, действия."""
from __future__ import annotations

import re
from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.core import llm, progress, vector
from app.core import repository as repo
from app.core.db import async_session
from app.core.models import User
from app.handlers import coach_actions
from app.keyboards import confirm_action_kb
from app.utils import parse_weight, typing

router = Router()

# Параметры памяти диалога
WINDOW = 12            # сколько последних реплик держим дословно
OVERFLOW_TRIGGER = 20  # при каком количестве запускаем суммаризацию
FOLD = OVERFLOW_TRIGGER - WINDOW  # сколько старых реплик сворачиваем в резюме

TOOLS_HINT = (
    "Если уместно, предлагай изменения через функции: нагрузка (adjust_load), "
    "замена упражнения (replace_exercise), время (set_time), вес (log_weight), "
    "или ПОЛНЫЙ новый план (set_plan). Изменения применяются ТОЛЬКО после "
    "подтверждения кнопкой.\n"
    "Когда предлагаешь новую программу — НЕ вываливай её целиком текстом. Дай "
    "короткое резюме (2–4 предложения: суть и почему) и передай детали в set_plan; "
    "пользователь увидит краткое описание и кнопку «Применить». В set_plan для "
    "новых упражнений указывай группу мышц и краткую технику. В целом отвечай кратко."
)


def _context_block(profile, plan, weight_line, facts, memory, summary, env, equip) -> str:
    return (
        "Контекст о клиенте (не показывай дословно, используй по смыслу):\n"
        f"ПРОФИЛЬ: {profile or '—'}\n"
        f"МЕСТО ТРЕНИРОВОК: {env or 'дом'}; ИНВЕНТАРЬ: {equip or 'нет'}\n"
        f"ПЛАН: {plan}\n"
        f"ВЕС: {weight_line}\n"
        f"РЕЗЮМЕ ПРОШЛЫХ БЕСЕД: {summary or '—'}\n"
        f"ТРЕНИРОВКИ (до 2 мес.):\n{facts}\n"
        f"ЗАМЕТКИ ПАМЯТИ:\n{memory}"
    )


async def _maybe_summarize(user_id: int) -> None:
    """Сворачивает старые реплики в резюме, если окно переполнилось."""
    async with async_session() as db:
        cnt = await repo.count_chat_messages(db, user_id)
        if cnt <= OVERFLOW_TRIGGER:
            return
        old = await repo.pop_oldest_chat_messages(db, user_id, cnt - WINDOW)
        user = await db.get(User, user_id)
        prev = user.chat_summary if user else None
    new_summary = await llm.summarize_history(prev, old)
    async with async_session() as db:
        await repo.set_chat_summary(db, user_id, new_summary)


async def handle_chat(message: Message, state: FSMContext, text: str) -> None:
    """Обработка свободного сообщения (текст или расшифрованный голос)."""
    text = text.strip()
    data = await state.get_data()

    async with async_session() as db:
        user = await repo.get_user_by_tg(db, message.from_user.id)
        if user is None:
            await message.answer("Сначала нажми /start")
            return

        # Режим ожидания веса (после кнопки «Записать вес» в настройках)
        if data.get("expect_weight"):
            async with typing(message):
                weight = await parse_weight(text)
            if weight is None:
                await message.answer("Не уловил вес. Напиши, например «81.3».")
                return
            await repo.log_weight(db, user.id, weight)
            await state.update_data(expect_weight=False)
            await message.answer(f"Записал вес — {weight:g} кг ⚖️")
            return

        # Одинокое число (ответ на недельный вопрос о весе) → запись веса
        if re.fullmatch(r"\d{2,3}([.,]\d)?\s*(кг|kg)?", text):
            weight = float(re.sub(r"[^\d.,]", "", text).replace(",", "."))
            await repo.log_weight(db, user.id, weight)
            await message.answer(f"Записал вес — {weight:g} кг ⚖️")
            return

        # Собираем контекст
        facts = await progress.build_facts(db, user.id)
        plan = await progress.plan_text(db, user.id)
        weight = await repo.current_weight(db, user.id)
        dw = await repo.weight_change(db, user.id, days=30)
        window = await repo.get_chat_window(db, user.id, WINDOW)
        summary = user.chat_summary
        profile = user.profile_summary
        personal = user.system_prompt
        env, equip = user.environment, user.equipment
        uid = user.id
        await repo.add_chat_message(db, uid, "user", text)

    weight_line = f"{weight:g} кг" if weight is not None else "не записан"
    if weight is not None and dw is not None:
        weight_line += f" ({'−' if dw < 0 else '+'}{abs(dw):.1f} за месяц)"

    memory_docs = await vector.query_memory(uid, text)
    memory = "\n".join(f"- {d}" for d in memory_docs) if memory_docs else "нет заметок"

    context_block = _context_block(profile, plan, weight_line, facts, memory, summary, env, equip)
    system = llm._system_content(personal) + "\n\n" + TOOLS_HINT + "\n\n" + context_block
    messages = window + [{"role": "user", "content": text}]

    async with typing(message):
        result = await llm.chat_with_tools(messages, system)

    action = result.get("action")
    desc = coach_actions.describe(action) if action else None
    # Если модель вернула только действие без текста — подставим уместную реплику
    answer = result.get("text") or ("Есть идея по программе 👇" if desc else "Понял.")

    if desc:
        await state.update_data(pending_action=action)
        await message.answer(answer)
        await message.answer(f"💡 Предлагаю: {desc}", reply_markup=confirm_action_kb())
        assistant_content = f"{answer}\n[предложение: {desc}]"
    else:
        await message.answer(answer)
        assistant_content = answer

    async with async_session() as db:
        await repo.add_chat_message(db, uid, "assistant", assistant_content)
    # Реплику пользователя дублируем в семантическую память (долгая память)
    await vector.add_memory(
        uid, f"note-{message.message_id}", text, {"type": "user_note", "date": str(date.today())}
    )
    await _maybe_summarize(uid)


@router.callback_query(F.data == "act:apply")
async def act_apply(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    action = data.get("pending_action")
    if not action:
        await cb.answer("Действие уже неактуально")
        return
    result = await coach_actions.apply(action, cb.from_user.id)
    await state.update_data(pending_action=None)
    await cb.message.answer(f"✅ {result}")
    await cb.answer()


@router.callback_query(F.data == "act:cancel")
async def act_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(pending_action=None)
    await cb.message.answer("Ок, ничего не меняю 👌")
    await cb.answer()


@router.message(F.text & ~F.text.startswith("/"))
async def free_chat(message: Message, state: FSMContext) -> None:
    await handle_chat(message, state, message.text)
