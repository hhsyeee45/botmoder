import asyncio
import re
from collections import defaultdict, deque
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand

import os
TOKEN = os.getenv("BOT_TOKEN")
dp = Dispatcher()


moderator_active = False
warnings = defaultdict(int)
MAX_MESSAGES = 10
TIME_WINDOW = 30
user_activity = defaultdict(lambda: deque())

# --- Завантаження списку слів ---
with open(r"C:\Users\Алекс\Desktop\bot\bad_words.txt", encoding="utf-8") as f:
    BAD_WORDS = {line.strip().lower() for line in f if line.strip()}

def censor_text(text: str) -> str:
    censored = text
    for bad_word in BAD_WORDS:
        # регулярка ловить слово і всі його форми
        pattern = re.compile(rf"\b{bad_word}\w*\b", re.IGNORECASE)
        censored = pattern.sub(lambda m: "#" * len(m.group()), censored)
    return censored

# --- Inline кнопки ---
inline_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Активувати", callback_data="play")],
        [InlineKeyboardButton(text="⏹️ Зупинити", callback_data="stop")],
        [InlineKeyboardButton(text="ℹ️ Інфо", callback_data="info")]
    ]
)

# --- Спільні функції ---
async def activate_moderator(target):
    global moderator_active
    moderator_active = True
    await target.answer("✅ Модератор активований!")

async def stop_moderator(target):
    global moderator_active
    moderator_active = False
    await target.answer("⏹️ Модератор зупинений.")

async def user_info(target, user, count):
    await target.answer(
        f"ℹ️ Інформація про користувача:\n"
        f"👤 {user.full_name}\n"
        f"⚠️ Попереджень: {count}"
    )

# --- Команда /start ---
@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "👋 Привіт! Я бот‑модератор.\n\n"
        "Я допоможу підтримувати порядок у чаті.\n"
        "Вибери дію нижче:",
        reply_markup=inline_kb
    )

# --- Хендлери для меню команд ---
@dp.message(Command("play"))
async def play_handler(message: Message):
    await activate_moderator(message)

@dp.message(Command("stop"))
async def stop_handler(message: Message):
    await stop_moderator(message)

@dp.message(Command("info"))
async def info_handler(message: Message):
    args = message.text.split()
    if len(args) == 1:
        # якщо аргументів немає → показуємо статистику самого себе
        user_id = message.from_user.id
        user = message.from_user
    else:
        target = args[1]
        if target.startswith("@"):
            # тут можна зробити lookup по username, якщо ти його зберігаєш
            user_id = message.from_user.id   # тимчасово показуємо себе
            user = message.from_user
        else:
            try:
                user_id = int(target)
                user = message.from_user  # lookup по id
            except ValueError:
                await message.answer("❌ Використовуйте /info або /info @username або /info user_id")
                return

    count = warnings[user_id]
    await message.answer(
        f"ℹ️ Інформація про користувача:\n"
        f"👤 {user.full_name}\n"
        f"🆔 ID: {user_id}\n"
        f"⚠️ Попереджень: {count}"
    )

# --- Хендлери для inline‑кнопок ---
@dp.callback_query(F.data == "play")
async def play_callback(callback_query):
    await activate_moderator(callback_query.message)
    await callback_query.message.edit_reply_markup(reply_markup=None)
    await callback_query.answer()

@dp.callback_query(F.data == "stop")
async def stop_callback(callback_query):
    await stop_moderator(callback_query.message)
    await callback_query.message.edit_reply_markup(reply_markup=None)
    await callback_query.answer()

@dp.callback_query(F.data == "info")
async def info_callback(callback_query):
    user_id = callback_query.from_user.id
    count = warnings[user_id]
    await user_info(callback_query.message, callback_query.from_user, count)
    await callback_query.message.edit_reply_markup(reply_markup=None)
    await callback_query.answer()

# --- Модерація ---
@dp.message(F.text | F.photo | F.sticker) 
async def moderation_handler(message: Message):
    if not moderator_active:
        return

    user_id = message.from_user.id
    now = message.date.timestamp()

    # --- Цензура ---
    if message.text:
        censored = censor_text(message.text)
        if censored != message.text:
            warnings[user_id] += 1
            try:
                await message.delete()
            except Exception:
                pass
            await message.answer(
                f"⚠️ {message.from_user.first_name}, твоє повідомлення містило погані слова:\n\n{censored}"
            )

    # --- Антиспам (текст, фото, стікери) ---
    user_activity[user_id].append(message)  # зберігаємо самі повідомлення
    timestamps = [msg.date.timestamp() for msg in user_activity[user_id]]

    # очищаємо старі записи
    while timestamps and now - timestamps[0] > TIME_WINDOW:
        user_activity[user_id].popleft()
        timestamps.pop(0)

    # якщо більше ніж 10 повідомлень
    if len(user_activity[user_id]) > MAX_MESSAGES:
        warnings[user_id] += 1

        # залишаємо тільки перше повідомлення
        first_msg = user_activity[user_id][0]
        for msg in list(user_activity[user_id])[1:]:
            try:
                await msg.delete()
            except Exception:
                pass

        await message.answer(
            f"🚫 {message.from_user.first_name}, занадто багато повідомлень! "
            f"⚠️ Попереджень: {warnings[user_id]}"
        )

        # очищаємо чергу, залишаємо тільки перше
        user_activity[user_id].clear()
        user_activity[user_id].append(first_msg)

# --- Запуск ---
async def main():
    bot = Bot(token=TOKEN)

    # Реєстрація команд для меню (/)
    commands = [
        BotCommand(command="start", description="Запустити бота"),
        BotCommand(command="play", description="Активувати модератора"),
        BotCommand(command="stop", description="Зупинити модератора"),
        BotCommand(command="info", description="Інформація про користувача"),
    ]
    await bot.set_my_commands(commands)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
