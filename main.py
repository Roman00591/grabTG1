import asyncio
import json
import logging
import os
import re
import sys

from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from telethon.errors import FloodWaitError

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

from database import (
    initialize_db,
    get_admins, add_admin, remove_admin,
    get_moderation, set_moderation,
    get_link_replacement, set_link_replacement,
    get_username_replacement, set_username_replacement,
    get_rss_scanning, set_rss_scanning,
    get_copywriting, set_copywriting,
    get_gpt_mode, set_gpt_mode,
    get_prompt, set_prompt,
    get_source_channels, add_source_channel, remove_source_channel,
    get_dest_channels, add_dest_channel, remove_dest_channel,
    get_channel_mapping, add_channel_mapping, remove_channel_mapping,
    get_words, add_word, remove_word,
    get_text_end, set_text_end,
    get_usernames, get_links,
    add_rss_channel_to_db, remove_rss_channel_from_db, get_all_rss_channels,
)
from copywriting import rewrite_text
from image_kandinsky import generate_image_with_kandinsky
from rss import scan_and_post_rss_news

# ─── Config ───────────────────────────────────────────────
with open('config.json', 'r') as f:
    config = json.load(f)

API_ID = config["api_id"]
API_HASH = config["api_hash"]
BOT_TOKEN = config["bot_token"]
MY_ID = config["my_id"]
TECH_CHANNEL = config["technical_channel_id"]
MAIN_CHANNEL = config.get("main_channel_id", TECH_CHANNEL)
RSS_TIMEOUT = config.get("rss_timeout", 3600)
POST_INTERVAL = config.get("post_interval", 3600)
MAX_RSS = config.get("max_rss_entries", 50)

# ─── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s-%(levelname)s-%(message)s',
    datefmt='%H:%M:%S',
    handlers=[logging.FileHandler('logi.txt', encoding='utf-8'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ─── Clients ──────────────────────────────────────────────
telethon_client = TelegramClient('myGrab', API_ID, API_HASH,
                                  device_model="Samsung S10 Lite",
                                  system_version='4.16.30-vxCUSTOM')
bot = Bot(token=BOT_TOKEN, parse_mode='HTML')
dp = Dispatcher(bot, storage=MemoryStorage())

# Хранилище сообщений на модерации: message_id -> list of messages
moderation_storage = {}


# ─── States ───────────────────────────────────────────────
class Form(StatesGroup):
    waiting_prompt = State()
    waiting_text_end = State()
    waiting_whitelist_add = State()
    waiting_blacklist_add = State()
    waiting_delete_word_add = State()
    waiting_source_channel = State()
    waiting_dest_channel = State()
    waiting_rss_add = State()
    waiting_admin_add = State()


# ─── Auth check ───────────────────────────────────────────
def is_allowed(user_id: int) -> bool:
    """Проверяет что пользователь — владелец или добавленный админ. Без жёстких ограничений."""
    if user_id == MY_ID:
        return True
    return user_id in get_admins()


# ─── Text helpers ─────────────────────────────────────────
def apply_replacements(text: str) -> str:
    if get_username_replacement():
        for old, new in get_usernames():
            text = re.sub(re.escape(old), new, text, flags=re.IGNORECASE)
    if get_link_replacement():
        for old, new in get_links():
            text = text.replace(old, new)
    return text


def apply_deleting_words(text: str) -> str:
    for word in get_words('deleting_text'):
        idx = text.lower().find(word.lower())
        if idx != -1:
            text = text[:idx].strip()
    return text


def passes_filters(text: str) -> bool:
    whitelist = get_words('whitelist')
    if whitelist and not any(w.lower() in text.lower() for w in whitelist):
        return False
    blacklist = get_words('blacklist')
    if any(w.lower() in text.lower() for w in blacklist):
        return False
    return True


# ─── Grabber ──────────────────────────────────────────────
async def process_message(event, messages: list, is_album=False):
    mapping = {src: dst for src, dst in get_channel_mapping()}
    if event.chat_id not in mapping:
        return

    dest_id = mapping[event.chat_id]
    combined_text = ""
    media_list = []

    for msg in messages:
        text = msg.text or msg.caption or ""
        if not passes_filters(text):
            logger.info("Сообщение отфильтровано")
            return
        text = apply_replacements(text)
        text = apply_deleting_words(text)
        if get_copywriting():
            rewritten = await rewrite_text(text)
            if rewritten:
                text = rewritten
        combined_text += text + "\n"
        if msg.media and not isinstance(msg.media, type(None)):
            media_list.append(msg.media)

    combined_text = combined_text.strip()
    tail = get_text_end(dest_id)
    if tail:
        combined_text += f"\n\n{tail}"

    if get_moderation():
        await send_to_moderation(event, combined_text, media_list, dest_id, is_album)
    else:
        await send_to_channel(dest_id, combined_text, media_list, is_album)


async def send_to_channel(dest_id, text, media_list, is_album):
    try:
        if media_list:
            if is_album and len(media_list) > 1:
                await telethon_client.send_file(dest_id, media_list, caption=text)
            else:
                for media in media_list:
                    await telethon_client.send_file(dest_id, media, caption=text)
        else:
            await telethon_client.send_message(dest_id, text)
        logger.info(f"Отправлено в канал {dest_id}")
    except FloodWaitError as e:
        logger.warning(f"FloodWait {e.seconds}s")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")


async def send_to_moderation(event, text, media_list, dest_id, is_album):
    await asyncio.sleep(1)
    try:
        if media_list:
            if is_album:
                sent = await telethon_client.send_file(TECH_CHANNEL, media_list, caption=text)
                sent = sent if isinstance(sent, list) else [sent]
            else:
                sent = []
                for m in media_list:
                    sent.append(await telethon_client.send_file(TECH_CHANNEL, m, caption=text))
        else:
            msg = await telethon_client.send_message(TECH_CHANNEL, text)
            sent = [msg]

        last_id = sent[-1].id
        moderation_storage[last_id] = {'messages': sent, 'dest_id': dest_id, 'text': text, 'media': media_list, 'album': is_album}

        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("✅ Отправить", callback_data=f"send_{last_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"decline_{last_id}"),
            InlineKeyboardButton("✏️ Рерайт", callback_data=f"rewrite_{last_id}"),
            InlineKeyboardButton("⏰ Отложить", callback_data=f"postpone_{last_id}"),
        )
        await bot.send_message(TECH_CHANNEL, f"📋 Новое сообщение на модерацию\n➡️ Канал: <code>{dest_id}</code>", reply_markup=kb)
    except Exception as e:
        logger.error(f"Ошибка модерации: {e}")


# ─── Telethon event handlers ──────────────────────────────
def setup_telethon_handlers():
    @telethon_client.on(events.NewMessage())
    async def on_new_message(event):
        if event.message.grouped_id:
            return
        mapping = {src: dst for src, dst in get_channel_mapping()}
        if event.chat_id in mapping:
            await process_message(event, [event.message], is_album=False)

    @telethon_client.on(events.Album())
    async def on_album(event):
        mapping = {src: dst for src, dst in get_channel_mapping()}
        if event.chat_id in mapping:
            await process_message(event, event.messages, is_album=True)


# ─── Moderation callbacks ─────────────────────────────────
@dp.callback_query_handler(lambda c: c.data and c.data.startswith(('send_', 'decline_', 'rewrite_', 'postpone_')))
async def moderation_callback(call: types.CallbackQuery):
    if not is_allowed(call.from_user.id):
        return

    parts = call.data.split('_', 1)
    action, msg_id = parts[0], int(parts[1])
    data = moderation_storage.get(msg_id)
    if not data:
        await call.answer("Сообщение не найдено")
        return

    if action == 'send':
        await send_to_channel(data['dest_id'], data['text'], data['media'], data['album'])
        await call.message.edit_text("✅ Отправлено")
        moderation_storage.pop(msg_id, None)

    elif action == 'decline':
        await call.message.edit_text("❌ Отклонено")
        moderation_storage.pop(msg_id, None)

    elif action == 'rewrite':
        rewritten = await rewrite_text(data['text'])
        if rewritten:
            data['text'] = rewritten
            await call.answer("Текст перереписан")
            kb = InlineKeyboardMarkup(row_width=2)
            kb.add(
                InlineKeyboardButton("✅ Отправить", callback_data=f"send_{msg_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"decline_{msg_id}"),
                InlineKeyboardButton("✏️ Рерайт ещё", callback_data=f"rewrite_{msg_id}"),
            )
            await call.message.edit_text(f"📝 Новый текст:\n\n{rewritten}", reply_markup=kb)
        else:
            await call.answer("Ошибка рерайта")

    elif action == 'postpone':
        await call.answer("⏰ Отложено на 1 час")
        await asyncio.sleep(3600)
        await send_to_channel(data['dest_id'], data['text'], data['media'], data['album'])
        moderation_storage.pop(msg_id, None)

    await call.answer()


# ─── Bot command handlers ─────────────────────────────────
@dp.message_handler(commands=['start', 'help'])
async def cmd_start(msg: types.Message):
    if not is_allowed(msg.from_user.id):
        return
    text = (
        "🤖 <b>MyGrab Bot — Управление</b>\n\n"
        "<b>Каналы:</b>\n"
        "/add_source — добавить канал-источник\n"
        "/add_dest — добавить канал-получатель\n"
        "/add_mapping — связать источник→получатель\n"
        "/channels — список каналов\n\n"
        "<b>Настройки:</b>\n"
        "/moderation — вкл/выкл модерацию\n"
        "/copywriting — вкл/выкл рерайт\n"
        "/gpt_mode — внутренний/внешний GPT\n"
        "/set_prompt — изменить промпт GPT\n"
        "/link_replace — вкл/выкл замену ссылок\n"
        "/user_replace — вкл/выкл замену юзернеймов\n\n"
        "<b>Фильтры:</b>\n"
        "/whitelist — белый список слов\n"
        "/blacklist — чёрный список слов\n"
        "/delete_words — слова для обрезки текста\n\n"
        "<b>RSS:</b>\n"
        "/rss — управление RSS\n\n"
        "<b>Другое:</b>\n"
        "/add_admin — добавить администратора\n"
        "/status — текущие настройки\n"
    )
    await msg.answer(text)


@dp.message_handler(commands=['status'])
async def cmd_status(msg: types.Message):
    if not is_allowed(msg.from_user.id):
        return
    mapping = get_channel_mapping()
    sources = {c: t for c, t in get_source_channels()}
    dests = {c: t for c, t in get_dest_channels()}
    pairs = "\n".join([f"  {sources.get(s, s)} → {dests.get(d, d)}" for s, d in mapping]) or "  нет"
    text = (
        f"⚙️ <b>Статус бота</b>\n\n"
        f"Модерация: {'✅' if get_moderation() else '❌'}\n"
        f"Рерайт: {'✅' if get_copywriting() else '❌'}\n"
        f"GPT режим: {'внутренний' if get_gpt_mode() else 'внешний'}\n"
        f"Замена ссылок: {'✅' if get_link_replacement() else '❌'}\n"
        f"Замена юзернеймов: {'✅' if get_username_replacement() else '❌'}\n"
        f"RSS сканирование: {'✅' if get_rss_scanning() else '❌'}\n\n"
        f"<b>Связки каналов:</b>\n{pairs}\n\n"
        f"<b>Промпт GPT:</b>\n{get_prompt()}"
    )
    await msg.answer(text)


# ─── Channel management ───────────────────────────────────
@dp.message_handler(commands=['add_source'])
async def cmd_add_source(msg: types.Message, state: FSMContext):
    if not is_allowed(msg.from_user.id):
        return
    await msg.answer("Перешлите любое сообщение из канала-источника или введите его ID:")
    await Form.waiting_source_channel.set()


@dp.message_handler(state=Form.waiting_source_channel, content_types=types.ContentTypes.ANY)
async def process_source_channel(msg: types.Message, state: FSMContext):
    await state.finish()
    channel_id = None
    title = "Без названия"
    if msg.forward_from_chat:
        channel_id = msg.forward_from_chat.id
        title = msg.forward_from_chat.title or title
    else:
        try:
            channel_id = int(msg.text.strip())
        except:
            await msg.answer("❌ Не удалось определить ID канала")
            return
    add_source_channel(channel_id, title)
    await msg.answer(f"✅ Канал-источник добавлен: <b>{title}</b> (<code>{channel_id}</code>)")


@dp.message_handler(commands=['add_dest'])
async def cmd_add_dest(msg: types.Message, state: FSMContext):
    if not is_allowed(msg.from_user.id):
        return
    await msg.answer("Перешлите любое сообщение из канала-получателя или введите его ID:")
    await Form.waiting_dest_channel.set()


@dp.message_handler(state=Form.waiting_dest_channel, content_types=types.ContentTypes.ANY)
async def process_dest_channel(msg: types.Message, state: FSMContext):
    await state.finish()
    channel_id = None
    title = "Без названия"
    if msg.forward_from_chat:
        channel_id = msg.forward_from_chat.id
        title = msg.forward_from_chat.title or title
    else:
        try:
            channel_id = int(msg.text.strip())
        except:
            await msg.answer("❌ Не удалось определить ID канала")
            return
    add_dest_channel(channel_id, title)
    await msg.answer(f"✅ Канал-получатель добавлен: <b>{title}</b> (<code>{channel_id}</code>)")


@dp.message_handler(commands=['add_mapping'])
async def cmd_add_mapping(msg: types.Message):
    if not is_allowed(msg.from_user.id):
        return
    sources = get_source_channels()
    dests = get_dest_channels()
    if not sources or not dests:
        await msg.answer("❌ Сначала добавьте каналы через /add_source и /add_dest")
        return
    kb = InlineKeyboardMarkup(row_width=1)
    for cid, title in sources:
        kb.add(InlineKeyboardButton(f"📥 {title}", callback_data=f"mapsrc_{cid}"))
    await msg.answer("Выберите канал-источник:", reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('mapsrc_'))
async def mapping_src_selected(call: types.CallbackQuery):
    src_id = int(call.data.split('_', 1)[1])
    dests = get_dest_channels()
    kb = InlineKeyboardMarkup(row_width=1)
    for cid, title in dests:
        kb.add(InlineKeyboardButton(f"📤 {title}", callback_data=f"mapdst_{src_id}_{cid}"))
    await call.message.edit_text("Выберите канал-получатель:", reply_markup=kb)
    await call.answer()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('mapdst_'))
async def mapping_dst_selected(call: types.CallbackQuery):
    _, src_id, dst_id = call.data.split('_')
    add_channel_mapping(int(src_id), int(dst_id))
    await call.message.edit_text(f"✅ Связка добавлена: <code>{src_id}</code> → <code>{dst_id}</code>")
    await call.answer()


@dp.message_handler(commands=['channels'])
async def cmd_channels(msg: types.Message):
    if not is_allowed(msg.from_user.id):
        return
    sources = get_source_channels()
    dests = get_dest_channels()
    mapping = get_channel_mapping()
    src_text = "\n".join([f"  • {t} (<code>{c}</code>)" for c, t in sources]) or "  нет"
    dst_text = "\n".join([f"  • {t} (<code>{c}</code>)" for c, t in dests]) or "  нет"
    map_text = "\n".join([f"  <code>{s}</code> → <code>{d}</code>" for s, d in mapping]) or "  нет"
    await msg.answer(f"<b>Источники:</b>\n{src_text}\n\n<b>Получатели:</b>\n{dst_text}\n\n<b>Связки:</b>\n{map_text}")


# ─── Toggles ──────────────────────────────────────────────
@dp.message_handler(commands=['moderation'])
async def cmd_moderation(msg: types.Message):
    if not is_allowed(msg.from_user.id):
        return
    new = not get_moderation()
    set_moderation(new)
    await msg.answer(f"Модерация: {'✅ включена' if new else '❌ выключена'}")


@dp.message_handler(commands=['copywriting'])
async def cmd_copywriting(msg: types.Message):
    if not is_allowed(msg.from_user.id):
        return
    new = not get_copywriting()
    set_copywriting(new)
    await msg.answer(f"Рерайт текстов: {'✅ включён' if new else '❌ выключен'}")


@dp.message_handler(commands=['gpt_mode'])
async def cmd_gpt_mode(msg: types.Message):
    if not is_allowed(msg.from_user.id):
        return
    new = not get_gpt_mode()
    set_gpt_mode(new)
    await msg.answer(f"GPT режим: {'внутренний (g4f)' if new else 'внешний (OpenAI API)'}")


@dp.message_handler(commands=['link_replace'])
async def cmd_link_replace(msg: types.Message):
    if not is_allowed(msg.from_user.id):
        return
    new = not get_link_replacement()
    set_link_replacement(new)
    await msg.answer(f"Замена ссылок: {'✅ включена' if new else '❌ выключена'}")


@dp.message_handler(commands=['user_replace'])
async def cmd_user_replace(msg: types.Message):
    if not is_allowed(msg.from_user.id):
        return
    new = not get_username_replacement()
    set_username_replacement(new)
    await msg.answer(f"Замена юзернеймов: {'✅ включена' if new else '❌ выключена'}")


# ─── Prompt ───────────────────────────────────────────────
@dp.message_handler(commands=['set_prompt'])
async def cmd_set_prompt(msg: types.Message, state: FSMContext):
    if not is_allowed(msg.from_user.id):
        return
    await msg.answer(f"Текущий промпт:\n<i>{get_prompt()}</i>\n\nВведите новый промпт:")
    await Form.waiting_prompt.set()


@dp.message_handler(state=Form.waiting_prompt)
async def process_prompt(msg: types.Message, state: FSMContext):
    set_prompt(msg.text.strip())
    await state.finish()
    await msg.answer(f"✅ Промпт обновлён:\n<i>{msg.text.strip()}</i>")


# ─── Word lists ───────────────────────────────────────────
@dp.message_handler(commands=['whitelist'])
async def cmd_whitelist(msg: types.Message):
    if not is_allowed(msg.from_user.id):
        return
    words = get_words('whitelist')
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("➕ Добавить слово", callback_data="wl_add"))
    if words:
        for w in words:
            kb.add(InlineKeyboardButton(f"❌ {w}", callback_data=f"wl_del_{w}"))
    text = "📋 <b>Белый список</b>\n" + ("\n".join(f"• {w}" for w in words) if words else "Пусто")
    await msg.answer(text, reply_markup=kb)


@dp.message_handler(commands=['blacklist'])
async def cmd_blacklist(msg: types.Message):
    if not is_allowed(msg.from_user.id):
        return
    words = get_words('blacklist')
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("➕ Добавить слово", callback_data="bl_add"))
    if words:
        for w in words:
            kb.add(InlineKeyboardButton(f"❌ {w}", callback_data=f"bl_del_{w}"))
    text = "🚫 <b>Чёрный список</b>\n" + ("\n".join(f"• {w}" for w in words) if words else "Пусто")
    await msg.answer(text, reply_markup=kb)


@dp.message_handler(commands=['delete_words'])
async def cmd_delete_words(msg: types.Message):
    if not is_allowed(msg.from_user.id):
        return
    words = get_words('deleting_text')
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("➕ Добавить слово", callback_data="dw_add"))
    if words:
        for w in words:
            kb.add(InlineKeyboardButton(f"❌ {w}", callback_data=f"dw_del_{w}"))
    text = "✂️ <b>Слова для обрезки текста</b>\n" + ("\n".join(f"• {w}" for w in words) if words else "Пусто")
    await msg.answer(text, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data in ('wl_add', 'bl_add', 'dw_add'))
async def wordlist_add(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(wl_type=call.data[:2])
    mapping = {'wl': Form.waiting_whitelist_add, 'bl': Form.waiting_blacklist_add, 'dw': Form.waiting_delete_word_add}
    await mapping[call.data[:2]].set()
    await call.message.answer("Введите слово:")
    await call.answer()


@dp.message_handler(state=Form.waiting_whitelist_add)
async def process_wl_add(msg: types.Message, state: FSMContext):
    add_word('whitelist', msg.text.strip())
    await state.finish()
    await msg.answer(f"✅ Добавлено в белый список: <b>{msg.text.strip()}</b>")


@dp.message_handler(state=Form.waiting_blacklist_add)
async def process_bl_add(msg: types.Message, state: FSMContext):
    add_word('blacklist', msg.text.strip())
    await state.finish()
    await msg.answer(f"✅ Добавлено в чёрный список: <b>{msg.text.strip()}</b>")


@dp.message_handler(state=Form.waiting_delete_word_add)
async def process_dw_add(msg: types.Message, state: FSMContext):
    add_word('deleting_text', msg.text.strip())
    await state.finish()
    await msg.answer(f"✅ Добавлено в слова для обрезки: <b>{msg.text.strip()}</b>")


@dp.callback_query_handler(lambda c: c.data and (c.data.startswith('wl_del_') or c.data.startswith('bl_del_') or c.data.startswith('dw_del_')))
async def wordlist_del(call: types.CallbackQuery):
    prefix, word = call.data[:6], call.data[7:]
    table = {'wl_del': 'whitelist', 'bl_del': 'blacklist', 'dw_del': 'deleting_text'}[prefix]
    remove_word(table, word)
    await call.answer(f"Удалено: {word}")
    await call.message.edit_text(f"✅ Слово <b>{word}</b> удалено")


# ─── RSS ──────────────────────────────────────────────────
@dp.message_handler(commands=['rss'])
async def cmd_rss(msg: types.Message):
    if not is_allowed(msg.from_user.id):
        return
    channels = get_all_rss_channels()
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("➕ Добавить RSS", callback_data="rss_add"))
    rss_on = get_rss_scanning()
    kb.add(InlineKeyboardButton(f"{'❌ Выключить' if rss_on else '✅ Включить'} сканирование", callback_data="rss_toggle"))
    if channels:
        for url, title in channels:
            kb.add(InlineKeyboardButton(f"🗑 {title}", callback_data=f"rss_del_{url}"))
    text = f"📡 <b>RSS каналы</b> (сканирование: {'✅' if rss_on else '❌'})\n"
    text += "\n".join(f"• {t}" for _, t in channels) if channels else "Нет добавленных"
    await msg.answer(text, reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == 'rss_add')
async def rss_add_cb(call: types.CallbackQuery, state: FSMContext):
    await Form.waiting_rss_add.set()
    await call.message.answer("Введите URL RSS-ленты:")
    await call.answer()


@dp.message_handler(state=Form.waiting_rss_add)
async def process_rss_add(msg: types.Message, state: FSMContext):
    url = msg.text.strip()
    try:
        import feedparser
        feed = feedparser.parse(url)
        title = feed.feed.get('title', url)
        add_rss_channel_to_db(url, title)
        await msg.answer(f"✅ RSS добавлен: <b>{title}</b>")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")
    await state.finish()


@dp.callback_query_handler(lambda c: c.data == 'rss_toggle')
async def rss_toggle(call: types.CallbackQuery):
    new = not get_rss_scanning()
    set_rss_scanning(new)
    await call.answer(f"RSS сканирование {'включено' if new else 'выключено'}")
    await call.message.edit_text(f"RSS сканирование: {'✅ включено' if new else '❌ выключено'}")


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('rss_del_'))
async def rss_del(call: types.CallbackQuery):
    url = call.data[8:]
    remove_rss_channel_from_db(url)
    await call.answer("Удалено")
    await call.message.edit_text("✅ RSS канал удалён")


# ─── Admin management ─────────────────────────────────────
@dp.message_handler(commands=['add_admin'])
async def cmd_add_admin(msg: types.Message, state: FSMContext):
    if msg.from_user.id != MY_ID:
        return
    await msg.answer("Введите Telegram ID нового администратора:")
    await Form.waiting_admin_add.set()


@dp.message_handler(state=Form.waiting_admin_add)
async def process_admin_add(msg: types.Message, state: FSMContext):
    await state.finish()
    try:
        user_id = int(msg.text.strip())
        add_admin(user_id)
        await msg.answer(f"✅ Администратор добавлен: <code>{user_id}</code>")
    except:
        await msg.answer("❌ Неверный ID")


# ─── RSS background task ──────────────────────────────────
async def rss_task():
    while True:
        await asyncio.sleep(RSS_TIMEOUT)
        if get_rss_scanning():
            logger.info("Запуск сканирования RSS")
            dest_channels = get_dest_channels()
            if dest_channels:
                dest_id = dest_channels[0][0]
                await scan_and_post_rss_news(telethon_client, dest_id, MAX_RSS)


# ─── Main ─────────────────────────────────────────────────
async def main():
    initialize_db()
    logger.info("SMM Assistant - Запущен")

    await telethon_client.start()
    me = await telethon_client.get_me()
    logger.info(f"Авторизован как: {me.first_name} (ID: {me.id})")

    setup_telethon_handlers()
    asyncio.create_task(rss_task())

    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
