# Telegram Mini App — Инструкция

## Что это?
Красивый веб-интерфейс управления ботом, который открывается прямо внутри Telegram.

## Файлы
- `index.html` — интерфейс Mini App
- `webapp_server.py` — Flask API сервер

## Установка

### 1. Установите зависимости
```
pip install flask flask-cors
```

### 2. Запустите сервер
```
cd webapp
python webapp_server.py
```
Сервер запустится на http://localhost:5000

### 3. Сделайте сервер доступным из интернета
Telegram требует HTTPS. Используйте ngrok (бесплатно):
```
ngrok http 5000
```
Скопируйте HTTPS ссылку вида: https://abc123.ngrok.io

### 4. Добавьте команду /app в бота
В main.py добавьте:
```python
WEBAPP_URL = "https://abc123.ngrok.io"  # ваша ngrok ссылка

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
    await msg.answer("Панель управления ботом:", reply_markup=kb)
```

### 5. Готово!
Напишите боту /app — появится кнопка, при нажатии откроется красивый интерфейс.

## Возможности интерфейса
- 🏠 Главная — быстрые переключатели всех режимов
- 📡 Каналы — добавление/удаление связок каналов
- 🔍 Фильтры — белый/чёрный список, слова для обрезки
- 🤖 GPT — настройка промпта и RSS лент
- 📋 Логи — просмотр последних записей в реальном времени
