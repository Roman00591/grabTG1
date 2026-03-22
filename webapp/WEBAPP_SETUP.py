# Добавьте эти строки в main.py после импортов
# чтобы бот показывал кнопку открытия Mini App

WEBAPP_URL = "https://ВАШ_ДОМЕН_ИЛИ_NGROK"  # ← замените на реальный URL

# Добавьте этот хэндлер в main.py:
"""
@dp.message_handler(commands=['app'])
async def cmd_webapp(msg: types.Message):
    if not is_allowed(msg.from_user.id):
        return
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(
        text="🤖 Открыть панель управления",
        web_app=WebAppInfo(url=WEBAPP_URL)
    ))
    await msg.answer("Нажмите кнопку ниже чтобы открыть панель управления ботом:", reply_markup=kb)
"""
