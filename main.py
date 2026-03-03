import asyncio
import json
import os
import random
import aiohttp
from urllib.parse import quote
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, Message, LabeledPrice,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

# -----------------------------
# CONFIG
# -----------------------------
API_TOKEN = "8493246716:AAGwPq4IzWqFAuhaNLDMFJ-ALRyzKp5Y220"
BOT_USERNAME = "RekchiAi_bot"
PAYMENT_PROVIDER = "1650291590:TEST:1759584442432_8mWh2HL87VsElKyh"
ADMINS = ["Behruzxan", "H08_09"]
RECEIPT_CHANNEL = "-1003181756108"
PROOF_CHANNEL = "@rekchi_tv"
TOPUP_CARD_NUMBER = "9860606740391457"
MAX_FILE_SIZE = 50 * 1024 * 1024

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(f"{DATA_DIR}/videos", exist_ok=True)
USERS_FILE = f"{DATA_DIR}/users.json"
BUTTONS_FILE = f"{DATA_DIR}/buttons.json"
VIDEOS_META = f"{DATA_DIR}/videos.json"
CONFIG_FILE = f"{DATA_DIR}/config.json"
PROMOCODES_FILE = f"{DATA_DIR}/promocodes.json"
ORDERS_FILE = f"{DATA_DIR}/orders.json"

# -----------------------------
# Utilities to load/save JSON
# -----------------------------
def load_json(path, default=None):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default if default is not None else {}, f)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# -----------------------------
# Persistent data
# -----------------------------
users = load_json(USERS_FILE, {})
buttons = load_json(BUTTONS_FILE, {})
videos = load_json(VIDEOS_META, {})
config = load_json(CONFIG_FILE, {"channels": [], "contact": None})
config.setdefault("channels", [])
config.setdefault("contact", None)
save_json(CONFIG_FILE, config)
promocodes = load_json(PROMOCODES_FILE, {})
orders = load_json(ORDERS_FILE, {})

# -----------------------------
# FSM States
# -----------------------------
class S(StatesGroup):
    waiting_for_subscription = State()
    waiting_for_captcha = State()
    waiting_for_views = State()
    waiting_for_video_link = State()
    waiting_for_purchase_views = State()
    waiting_for_topup = State()
    waiting_for_promocode = State()
    admin_await_channel = State()
    admin_await_remove_channel = State()
    admin_await_button_title = State()
    admin_await_button_msg = State()
    admin_await_remove_button = State()
    admin_await_video_title = State()
    admin_await_video_file = State()
    admin_await_broadcast = State()
    admin_await_remove_video = State()
    admin_await_promocode_name = State()
    admin_await_promocode_type = State()
    admin_await_promocode_amount = State()
    admin_await_promocode_limit = State()
    admin_await_remove_promocode = State()
    waiting_for_topup_receipt = State()
    admin_await_contact = State()
    waiting_for_admin_message = State()

# -----------------------------
# Business logic helpers
# -----------------------------
def referal_count_by_views(v: int) -> int:
    if v <= 1000:
        return 1
    elif v <= 5000:
        return 3
    elif v <= 10000:
        return 5
    else:
        return max(1, v // 2000)

def calculate_price(views: int) -> int:
    if views >= 100000:
        return int(views * 0.5)
    elif views >= 50000:
        return int(views * 0.6)
    elif views >= 20000:
        return int(views * 0.7)
    elif views >= 10000:
        return int(views * 0.8)
    elif views >= 5000:
        return int(views * 0.9)
    elif views >= 1000:
        return views
    else:
        return -1

def get_reply_keyboard(username: str = ""):
    is_admin_flag = username in ADMINS
    kb = [
        [KeyboardButton(text="👁 1k"), KeyboardButton(text="👁 5k"), KeyboardButton(text="👁 10k")],
        [KeyboardButton(text="🔢 Ko'rishlar sonini kiritish"), KeyboardButton(text="👬 Referal")],
        [KeyboardButton(text="💳 Xarid qilish"), KeyboardButton(text="💰 Balans")],
        [KeyboardButton(text="🎬 Video darslik"), KeyboardButton(text="🎟 Promokod")],
        [KeyboardButton(text="📞 Adminga murojaat")]
    ]
    for title in buttons.keys():
        kb.append([KeyboardButton(text=title)])
    if is_admin_flag:
        kb.append([KeyboardButton(text="📋 Tugmalar ro'yxati"), KeyboardButton(text="⚙️ Admin panel")])
        kb.append([KeyboardButton(text="📊 Statistika")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_xarid_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 1K sotib olish"), KeyboardButton(text="🛒 5K sotib olish"), KeyboardButton(text="🛒 10K sotib olish")],
            [KeyboardButton(text="🔢 Ko'rish sonini kiritish 💰"), KeyboardButton(text="❌ Bekor qilish")],
        ],
        resize_keyboard=True
    )

def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Kanal qo'shish"), KeyboardButton(text="❌ Kanal o'chirish")],
            [KeyboardButton(text="🆕 Tugma qo'shish"), KeyboardButton(text="🗑 Tugma o'chirish")],
            [KeyboardButton(text="🎬 Video darslik qo'shish"), KeyboardButton(text="🗑 Video o'chirish")],
            [KeyboardButton(text="🎟 Promokod qo'shish"), KeyboardButton(text="📋 Promokodlar")],
            [KeyboardButton(text="📋 Tugmalar ro'yxati"), KeyboardButton(text="📢 Reklama tarqatish")],
            [KeyboardButton(text="👤 Adminga murojaat sozlash"), KeyboardButton(text="🗑 Promokod o'chirish")],
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="⬅️ Ortga")]
        ],
        resize_keyboard=True
    )

def generate_captcha():
    return str(random.randint(1000, 9999))

def get_hashtags(v: int):
    return [
        "#Videolaringizni rekga chiqaradigan suniy intelektni hohlaysizmi? Telegramga RekchiAi_bot ga kiring.",
        ".",
        ".",
        "#Telegramdagi #RekchiAi_bot"
    ]

def get_valid_ref_count(uid: str) -> int:
    confirmed_refs = [r for r in users.get(uid, {}).get("refs", []) if users.get(r, {}).get("confirmed")]
    bonus = users.get(uid, {}).get("bonus_refs", 0)
    return len(confirmed_refs) + bonus

# -----------------------------
# Neosmm API helpers
# -----------------------------
NEOSMM_API_URL = "https://neosmm.uz/api/v2"
NEOSMM_API_KEY = "66a5383b19b6766a5383b19b73"
NEOSMM_SERVICE_ID = 783

async def send_to_neosmm(link, count):
    payload = {"key": NEOSMM_API_KEY, "action": "add", "service": NEOSMM_SERVICE_ID, "link": link, "quantity": count}
    async with aiohttp.ClientSession() as session:
        async with session.post(NEOSMM_API_URL, data=payload) as resp:
            try:
                return await resp.json()
            except Exception:
                try:
                    text = await resp.text()
                    return {"error": "Invalid JSON from API", "raw": text}
                except Exception:
                    return {"error": "APIdan noto'g'ri javob"}

async def check_neosmm_order(order_id):
    payload = {"key": NEOSMM_API_KEY, "action": "status", "order": order_id}
    async with aiohttp.ClientSession() as session:
        async with session.post(NEOSMM_API_URL, data=payload) as resp:
            try:
                return await resp.json()
            except Exception:
                try:
                    text = await resp.text()
                    return {"error": "Invalid JSON from API", "raw": text}
                except Exception:
                    return {"error": "APIdan noto'g'ri javob"}

# -----------------------------
# Order status poller
# -----------------------------
async def poll_order_status(order_id, user_id, link, target_views, interval_seconds=600):
    max_checks = 48
    checks = 0
    last_msg_id = None
    last_done = -1
    while checks < max_checks:
        await asyncio.sleep(interval_seconds)
        checks += 1
        try:
            status_resp = await check_neosmm_order(order_id)
        except Exception as e:
            try:
                await bot.send_message(PROOF_CHANNEL, f"Order {order_id}: status check failed: {e}")
            except Exception:
                pass
            continue
        status_text = status_resp.get("status") or status_resp.get("result") or status_resp.get("state") or None
        remains = status_resp.get("remains") or status_resp.get("left") or status_resp.get("quantity_left") or status_resp.get("left_count")
        done = target_views
        if remains is not None:
            try:
                rem_int = int(remains)
                done = int(target_views) - rem_int
                if done < 0:
                    done = 0
            except Exception:
                done = 0
        if done == last_done:
            continue
        progress = f"👁 {done} / {target_views}"
        report = (
            f"📌 Buyurtma: <code>{order_id}</code>\n"
            f"🔗 Video: <a href='{link}'>Ko'rish</a>\n"
            f"🎯 Maqsad: {target_views}\n"
            f"📊 Holat: {progress}\n"
        )
        if status_text:
            report += f"📋 Status: {status_text}\n"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎬 Video ko'rish", url=link)],
            [InlineKeyboardButton(text="👤 Foydalanuvchi", callback_data=f"user_{user_id}"), InlineKeyboardButton(text="👁 Isbot kanali", url="https://t.me/rekchi_tv")]
        ])
        try:
            if last_msg_id is None:
                msg = await bot.send_message(PROOF_CHANNEL, report, parse_mode="HTML", reply_markup=kb)
                last_msg_id = msg.message_id
            else:
                await bot.edit_message_text(
                    chat_id=PROOF_CHANNEL,
                    message_id=last_msg_id,
                    text=report,
                    parse_mode="HTML",
                    reply_markup=kb
                )
            last_done = done
        except Exception:
            pass
        completed_states = {"Completed", "completed", "Finished", "finished", "Success", "success"}
        if status_text and str(status_text) in completed_states or (remains is not None and int(remains) == 0):
            try:
                await bot.edit_message_text(
                    chat_id=PROOF_CHANNEL,
                    message_id=last_msg_id,
                    text=f"✅ Buyurtma yakunlandi!\n{report}",
                    parse_mode="HTML",
                    reply_markup=kb
                )
            except Exception:
                pass
            break
    if checks >= max_checks:
        try:
            await bot.edit_message_text(
                chat_id=PROOF_CHANNEL,
                message_id=last_msg_id,
                text=f"⚠️ Buyurtma tugatilmadi.\n{report}",
                parse_mode="HTML"
            )
        except Exception:
            pass

# -----------------------------
# Bot & Dispatcher
# -----------------------------
bot = Bot(API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# -----------------------------
# Subscription helpers
# -----------------------------
async def get_not_subscribed(user_id: int):
    channels = config.get("channels", [])
    not_subscribed = []
    if not channels:
        return []
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch, user_id)
            if member.status in ("left", "kicked"):
                not_subscribed.append(ch)
        except Exception:
            not_subscribed.append(ch)
    return not_subscribed

def make_subscribe_keyboard(not_subscribed):
    rows = []
    for ch in not_subscribed:
        label = ch if isinstance(ch, str) and ch.startswith("@") else ("@" + ch if isinstance(ch, str) and not ch.isdigit() else str(ch))
        url = f"https://t.me/{ch.replace('@','')}" if isinstance(ch, str) and not ch.isdigit() else None
        if url:
            rows.append([InlineKeyboardButton(text=label, url=url)])
        else:
            rows.append([InlineKeyboardButton(text=label, callback_data="noop")])
    rows.append([InlineKeyboardButton(text="✅ Obuna bo'ldim", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@dp.callback_query(F.data == "noop")
async def noop_callback(c: types.CallbackQuery):
    await c.answer("Bu havola orqali obuna bo'lish imkoni mavjud emas.", show_alert=True)

# -----------------------------
# FREE scheme video button
# -----------------------------
def make_free_scheme_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Videoni ko'rish", callback_data="free_video")],
        [InlineKeyboardButton(text="👁 Isbot kanali", url="https://t.me/rekchi_tv")]
    ])

@dp.callback_query(F.data == "free_video")
async def send_free_video(c: types.CallbackQuery):
    uid = str(c.from_user.id)
    if not videos:
        await c.answer("🎬 Video darsliklar mavjud emas!", show_alert=True)
        return
    for vid_id, meta in videos.items():
        if isinstance(meta, dict):
            try:
                await c.message.answer_video(video=vid_id, caption=f"🎬 {meta['title']}\n{meta.get('desc','')}")
                await c.answer()
                return
            except Exception:
                continue
    await c.answer("❌ Video yuborilmadi (xatolik)!", show_alert=True)

# -----------------------------
# Helper to ensure subscription
# -----------------------------
async def ensure_subscription_or_ask(m: Message, state: FSMContext):
    not_sub = await get_not_subscribed(m.from_user.id)
    if not_sub:
        kb = make_subscribe_keyboard(not_sub)
        await m.answer("❗ Iltimos, quyidagi kanallarga obuna bo'ling:", reply_markup=kb)
        await state.set_state(S.waiting_for_subscription)
        return False
    return True

# -----------------------------
# START flow — REFERALNI TO'G'RI QO'SHISH
# -----------------------------
@dp.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    uid = str(m.from_user.id)
    username = m.from_user.username or ""
    ref = m.text.split(" ")[1] if len(m.text.split(" ")) > 1 else None

    # Foydalanuvchini yaratish yoki yangilash
    if uid not in users:
        users[uid] = {
            "refs": [], "confirmed": False, "captcha": "", "hashtags": [],
            "await_video": False, "views": 0, "username": username, "balance": 0,
            "intro_video_sent": False, "bonus_refs": 0, "ref_of": None  # 👈 Yangi maydon
        }
    else:
        users[uid]["username"] = username

    # Referalni faqat BIRINCHI marta qo'shish
    if ref and ref != uid and not users[uid].get("ref_of"):
        users[uid]["ref_of"] = ref
        if ref in users and uid not in users[ref].get("refs", []):
            users[ref].setdefault("refs", []).append(uid)
            save_json(USERS_FILE, users)

    save_json(USERS_FILE, users)

    c = generate_captcha()
    users[uid]["captcha"] = c
    save_json(USERS_FILE, users)

    await m.answer(f"🤖 Botdan foydalanish uchun kodni kiriting:\n<b>{c}</b>", parse_mode="HTML")
    await state.set_state(S.waiting_for_captcha)

@dp.callback_query(F.data == "check_sub")
async def check_sub(c: types.CallbackQuery, state: FSMContext):
    uid = str(c.from_user.id)
    not_subscribed = await get_not_subscribed(c.from_user.id)
    if not_subscribed:
        await c.answer("❌ Hali ham obuna bo'lmagansiz!", show_alert=True)
        return
    users.setdefault(uid, {})["confirmed"] = True
    save_json(USERS_FILE, users)
    if videos and not users[uid].get("intro_video_sent", False):
        vid_id, meta = next(iter(videos.items()))
        if isinstance(meta, dict):
            try:
                await c.message.answer_video(video=vid_id, caption=f"🎬 {meta['title']}\n{meta.get('desc', '')}")
                users[uid]["intro_video_sent"] = True
                save_json(USERS_FILE, users)
            except Exception:
                pass
    try:
        await c.message.edit_text("✅ Obuna tasdiqlandi! Endi botdan foydalanishingiz mumkin.")
    except Exception:
        pass
    await c.message.answer("Asosiy menyu", reply_markup=get_reply_keyboard(users[uid].get("username", "")))
    await state.clear()

@dp.message(S.waiting_for_captcha)
async def check_captcha(m: Message, state: FSMContext):
    uid = str(m.from_user.id)
    username = m.from_user.username or ""
    if users.get(uid, {}).get("captcha") == m.text.strip():
        not_subscribed = await get_not_subscribed(m.from_user.id)
        if not_subscribed:
            kb = make_subscribe_keyboard(not_subscribed)
            await m.answer("❗ Iltimos, quyidagi kanallarga obuna bo'ling:", reply_markup=kb)
            await state.set_state(S.waiting_for_subscription)
            return
        users.setdefault(uid, {})["confirmed"] = True
        save_json(USERS_FILE, users)
        if videos and not users[uid].get("intro_video_sent", False):
            vid_id, meta = next(iter(videos.items()))
            if isinstance(meta, dict):
                try:
                    await m.answer_video(video=vid_id, caption=f"🎬 {meta['title']}\n{meta.get('desc', '')}")
                    users[uid]["intro_video_sent"] = True
                    save_json(USERS_FILE, users)
                except Exception:
                    pass
        await m.answer("✅ Tasdiqlandi! Endi botdan foydalanishingiz mumkin.", reply_markup=get_reply_keyboard(username))
        await state.clear()
    else:
        c = generate_captcha()
        users.setdefault(uid, {})["captcha"] = c
        save_json(USERS_FILE, users)
        await m.answer(f"❌ Kod noto'g'ri! Yangi kod:\n<b>{c}</b>", parse_mode="HTML")

# -----------------------------
# XARID QILISH MENYUSI — TO'G'RI ISHLASHI UCHUN
# -----------------------------
def create_purchase_kb(views: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Xarid qilish", callback_data=f"buy_paid_{views}")]
    ])

@dp.message(F.text == "💳 Xarid qilish")
async def buy_menu(m: Message):
    uid = str(m.from_user.id)
    if not users.get(uid, {}).get("confirmed", False):
        await m.answer("❗ Avval botdan foydalanishni tasdiqlang.")
        return
    await m.answer("🛒 Xarid qilish uchun quyidagilardan birini tanlang:", reply_markup=get_xarid_keyboard())

@dp.message(F.text == "🛒 1K sotib olish")
async def buy_1k_paid(m: Message):
    uid = str(m.from_user.id)
    if not users.get(uid, {}).get("confirmed", False):
        await m.answer("❗ Avval botdan foydalanishni tasdiqlang.")
        return
    price = calculate_price(1000)
    await m.answer(
        f"🛒 1K ko'rish narxi: <b>{price}</b> so'm",
        parse_mode="HTML",
        reply_markup=create_purchase_kb(1000)
    )

@dp.message(F.text == "🛒 5K sotib olish")
async def buy_5k_paid(m: Message):
    uid = str(m.from_user.id)
    if not users.get(uid, {}).get("confirmed", False):
        await m.answer("❗ Avval botdan foydalanishni tasdiqlang.")
        return
    price = calculate_price(5000)
    await m.answer(
        f"🛒 5K ko'rish narxi: <b>{price}</b> so'm",
        parse_mode="HTML",
        reply_markup=create_purchase_kb(5000)
    )

@dp.message(F.text == "🛒 10K sotib olish")
async def buy_10k_paid(m: Message):
    uid = str(m.from_user.id)
    if not users.get(uid, {}).get("confirmed", False):
        await m.answer("❗ Avval botdan foydalanishni tasdiqlang.")
        return
    price = calculate_price(10000)
    await m.answer(
        f"🛒 10K ko'rish narxi: <b>{price}</b> so'm",
        parse_mode="HTML",
        reply_markup=create_purchase_kb(10000)
    )

@dp.message(F.text == "🔢 Ko'rish sonini kiritish 💰")
async def buy_custom_paid(m: Message, state: FSMContext):
    uid = str(m.from_user.id)
    if not users.get(uid, {}).get("confirmed", False):
        await m.answer("❗ Avval botdan foydalanishni tasdiqlang.")
        return
    await m.answer("Necha ko'rish sotib olmoqchisiz? (faqat raqam kiriting, minimal: 1000):")
    await state.set_state(S.waiting_for_purchase_views)

@dp.message(S.waiting_for_purchase_views)
async def process_custom_paid(m: Message, state: FSMContext):
    if not m.text or not m.text.strip().isdigit():
        await m.answer("🔢 Faqat son kiriting! Masalan: 15000")
        return
    views = int(m.text.strip())
    price = calculate_price(views)
    if price == -1:
        await m.answer("❌ Kamida 1000 ko'rish bo'lishi kerak!")
        await state.clear()
        return
    await m.answer(
        f"🛒 {views} ta ko'rish narxi: <b>{price}</b> so'm",
        parse_mode="HTML",
        reply_markup=create_purchase_kb(views)
    )
    await state.clear()

@dp.callback_query(F.data.startswith("buy_paid_"))
async def handle_paid_purchase(c: types.CallbackQuery, state: FSMContext):
    uid = str(c.from_user.id)
    username = c.from_user.username or ""
    try:
        views = int(c.data.split("_")[2])
    except (IndexError, ValueError):
        await c.answer("❌ Noto'g'ri so'rov!")
        return

    price = calculate_price(views)
    if price == -1:
        await c.answer("❌ Noto'g'ri ko'rish miqdori!")
        return

    balance = users.get(uid, {}).get("balance", 0)
    if balance < price:
        await c.answer("❌ Balans yetarli emas!", show_alert=True)
        return

    # Balansdan pulni ayrish
    users[uid]["balance"] -= price
    save_json(USERS_FILE, users)

    # Foydalanuvchiga heshteglar va video so'rash
    hs = get_hashtags(views)
    users[uid]["hashtags"] = hs
    users[uid]["await_video"] = True
    users[uid]["views"] = views
    save_json(USERS_FILE, users)

    ht = "\n".join(hs)
    await c.message.edit_text(
        f"✅ To'lov muvaffaqiyatli amalga oshirildi!\n"
        f"💰 {price} so'm balansingizdan ayrildi.\n\n"
        f"🎯 {views} ta ko'rish uchun mos heshteglar:\n<pre>{ht}</pre>\n"
        f"📋 Nusxalash uchun ustiga bosing.\n📹 Endi video havolasini yuboring:",
        parse_mode="HTML"
    )
    await state.set_state(S.waiting_for_video_link)
    await c.answer()

# -----------------------------
# VIEWS HANDLERS (REFERAL ASOSIDA)
# -----------------------------
@dp.message(F.text == "👁 1k")
async def buy_1k(m: Message, state: FSMContext):
    ok = await ensure_subscription_or_ask(m, state)
    if not ok:
        return
    uid = str(m.from_user.id)
    username = m.from_user.username or ""
    valid_count = get_valid_ref_count(uid)
    req = 1
    if valid_count >= req:
        hs = get_hashtags(1000)
        users.setdefault(uid, {})["hashtags"] = hs
        users[uid]["await_video"] = True
        users[uid]["views"] = 1000
        users[uid]["used_ref_for_views"] = True
        save_json(USERS_FILE, users)
        ht = "\n".join(hs)
        await m.answer(
            f"Referallaringizdan 1 tasi ishlatiladi.\n"
            f"🎯 1k ko'rish uchun mos heshteglar:\n<pre>{ht}</pre>\n"
            f"📋 Nusxalash uchun ustiga bosing.\n📹 Endi video havolasini yuboring:",
            parse_mode="HTML",
            reply_markup=get_reply_keyboard(username)
        )
        await state.set_state(S.waiting_for_video_link)
    else:
        msg = "⚠️ 1K ko'rish uchun 1 ta tasdiqlangan referal kerak.\n🎁 Qanday bepul sxema olish mumkin: Videoni ko'ring 👇"
        await m.answer(msg, reply_markup=make_free_scheme_kb())

@dp.message(F.text == "👁 5k")
async def buy_5k(m: Message, state: FSMContext):
    ok = await ensure_subscription_or_ask(m, state)
    if not ok:
        return
    uid = str(m.from_user.id)
    username = m.from_user.username or ""
    valid_count = get_valid_ref_count(uid)
    req = 3
    if valid_count >= req:
        hs = get_hashtags(5000)
        users.setdefault(uid, {})["hashtags"] = hs
        users[uid]["await_video"] = True
        users[uid]["views"] = 5000
        users[uid]["used_ref_for_views"] = True
        save_json(USERS_FILE, users)
        ht = "\n".join(hs)
        await m.answer(
            f"Referallaringizdan 3 tasi ishlatiladi.\n"
            f"🎯 5k ko'rish uchun mos heshteglar:\n<pre>{ht}</pre>\n"
            f"📋 Nusxalash uchun ustiga bosing.\n📹 Endi video havolasini yuboring:",
            parse_mode="HTML",
            reply_markup=get_reply_keyboard(username)
        )
        await state.set_state(S.waiting_for_video_link)
    else:
        msg = "⚠️ 5K ko'rish uchun 3 ta tasdiqlangan referal kerak.\n🎁 Qanday bepul sxema olish mumkin: Videoni ko'ring 👇"
        await m.answer(msg, reply_markup=make_free_scheme_kb())

@dp.message(F.text == "👁 10k")
async def buy_10k(m: Message, state: FSMContext):
    ok = await ensure_subscription_or_ask(m, state)
    if not ok:
        return
    uid = str(m.from_user.id)
    username = m.from_user.username or ""
    valid_count = get_valid_ref_count(uid)
    req = 5
    if valid_count >= req:
        hs = get_hashtags(10000)
        users.setdefault(uid, {})["hashtags"] = hs
        users[uid]["await_video"] = True
        users[uid]["views"] = 10000
        users[uid]["used_ref_for_views"] = True
        save_json(USERS_FILE, users)
        ht = "\n".join(hs)
        await m.answer(
            f"Referallaringizdan 5 tasi ishlatiladi.\n"
            f"🎯 10k ko'rish uchun mos heshteglar:\n<pre>{ht}</pre>\n"
            f"📋 Nusxalash uchun ustiga bosing.\n📹 Endi video havolasini yuboring:",
            parse_mode="HTML",
            reply_markup=get_reply_keyboard(username)
        )
        await state.set_state(S.waiting_for_video_link)
    else:
        msg = "⚠️ 10K ko'rish uchun 5 ta tasdiqlangan referal kerak.\n🎁 Qanday bepul sxema olish mumkin: Videoni ko'ring 👇"
        await m.answer(msg, reply_markup=make_free_scheme_kb())

@dp.message(F.text == "🔢 Ko'rishlar sonini kiritish")
async def custom_views_input(m: Message, state: FSMContext):
    ok = await ensure_subscription_or_ask(m, state)
    if not ok:
        return
    username = m.from_user.username or ""
    await m.answer("Kerakli ko'rishlar sonini kiriting (masalan: 25000):", reply_markup=get_reply_keyboard(username))
    await state.set_state(S.waiting_for_views)

@dp.message(S.waiting_for_views)
async def process_views_input(m: Message, state: FSMContext):
    uid = str(m.from_user.id)
    username = m.from_user.username or ""
    if not m.text or not m.text.strip().isdigit():
        await m.answer("🔢 Faqat son kiriting! Masalan: 15000", reply_markup=get_reply_keyboard(username))
        return
    views = int(m.text.strip())
    valid_count = get_valid_ref_count(uid)
    refs_needed = referal_count_by_views(views)
    if valid_count < refs_needed:
        msg = f"⚠️ {views} ta ko'rish uchun {refs_needed} ta referal kerak.\n🎁 Qanday bepul sxema olish mumkin: Videoni ko'ring 👇"
        await m.answer(msg, reply_markup=make_free_scheme_kb())
        await state.clear()
        return
    hs = get_hashtags(views)
    users.setdefault(uid, {})["hashtags"] = hs
    users[uid]["await_video"] = True
    users[uid]["views"] = views
    users[uid]["used_ref_for_views"] = True
    save_json(USERS_FILE, users)
    ht = "\n".join(hs)
    await m.answer(
        f"🎯 {views:,} ta ko'rish uchun mos heshteglar:\n<pre>{ht}</pre>\n📋 Nusxalash uchun ustiga bosing.\n📹 Endi video havolasini yuboring:",
        parse_mode="HTML",
        reply_markup=get_reply_keyboard(username)
    )
    await state.set_state(S.waiting_for_video_link)

# -----------------------------
# VIEWS & PURCHASE flows
# -----------------------------
@dp.message(S.waiting_for_video_link)
async def process_video_link(m: Message, state: FSMContext):
    uid = str(m.from_user.id)
    username = m.from_user.username or ""
    link = (m.text or "").strip()
    views = users.get(uid, {}).get("views", 0)
    if not link.startswith("http"):
        await m.answer("❗ Faqat video havolasini yuboring!")
        return

    result = await send_to_neosmm(link, views)
    order_id = None
    if isinstance(result, dict):
        order_id = result.get("order") or result.get("id") or result.get("result")

    if order_id:
        orders.setdefault(str(order_id), {
            "user_id": uid,
            "username": username,
            "link": link,
            "views": views,
            "created_at": datetime.utcnow().isoformat(),
            "api_response": result
        })
        save_json(ORDERS_FILE, orders)

        await m.answer(f"✅ Buyurtma qabul qilindi!\nID: <code>{order_id}</code>\nKo'rishlar: <b>{views}</b>\nVideo: {link}", parse_mode="HTML")
        proof_msg = (
            f"📌 Yangi buyurtma qabul qilindi\n"
            f"Foydalanuvchi: @{username if username else uid} (ID: {uid})\n"
            f"Order ID: {order_id}\n"
            f"Link: {link}\n"
            f"Talab qilingan ko'rishlar: {views}\n"
            f"Vaqt: {datetime.utcnow().isoformat()} UTC"
        )
        try:
            await bot.send_message(PROOF_CHANNEL, proof_msg)
        except Exception:
            pass
        try:
            asyncio.create_task(poll_order_status(str(order_id), uid, link, views))
        except Exception:
            pass
    else:
        err_info = result.get("error") if isinstance(result, dict) else str(result)
        await m.answer("❌ Buyurtma xatolik bilan yakunlandi!\nSabab: " + str(err_info), parse_mode="HTML")

    users.setdefault(uid, {})["await_video"] = False
    users[uid]["hashtags"] = []
    users[uid]["views"] = 0
    users[uid]["used_ref_for_views"] = False
    save_json(USERS_FILE, users)
    await state.clear()

# -----------------------------
# BALANCE & TOPUP
# -----------------------------
@dp.message(F.text == "💰 Balans")
async def show_balance(m: Message):
    uid = str(m.from_user.id)
    username = m.from_user.username or ""
    balance = users.get(uid, {}).get("balance", 0)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💳 Balansni to'ldirish", callback_data="topup_balance")]]
    )
    await m.answer(
        f"💰 Sizning balansingiz: <b>{balance} so'm</b>\n"
        f"👇 Balansni to'ldirish uchun pastdagi tugmani bosing:",
        parse_mode="HTML",
        reply_markup=kb
    )

@dp.callback_query(F.data == "topup_balance")
async def topup_balance_callback(c: types.CallbackQuery, state: FSMContext):
    await c.answer()
    await c.message.answer("💳 Balansni to'ldirish uchun miqdorni kiriting (so'm):\nMinimal: 1000 so'm")
    await state.set_state(S.waiting_for_topup)

@dp.message(S.waiting_for_topup)
async def process_topup(m: Message, state: FSMContext):
    uid = str(m.from_user.id)
    if not m.text or not m.text.strip().isdigit():
        await m.answer("💳 Iltimos, faqat son kiriting! Masalan: 10000")
        return
    amount = int(m.text.strip())
    if amount < 1000:
        await m.answer("💳 Minimal to'ldirish miqdori: 1000 so'm!")
        return
    await state.update_data(topup_amount=amount)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Kartani nusxalash", callback_data="copy_card")],
        [InlineKeyboardButton(text="📤 To'lov chekini yuborish", callback_data="upload_receipt")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_topup")]
    ])
    await m.answer(
        f"💳 Pulni quyidagi karta raqamiga o'tkazing:\n<b>{TOPUP_CARD_NUMBER}</b>\n"
        f"🔔 O'tkazma summasi: <b>{amount:,} so'm</b>\n"
        "1) Kartaga pul o'tkazing.\n"
        "2) To'lov chekini (skrinshot / foto / PDF) pastdan yuboring.\n"
        "3) Admin tekshiradi va tasdiqlasa balansga mablag' qo'shiladi.",
        parse_mode="HTML",
        reply_markup=kb
    )
    await state.set_state(S.waiting_for_topup_receipt)

@dp.callback_query(F.data == "copy_card")
async def copy_card_callback(c: types.CallbackQuery):
    card_number = TOPUP_CARD_NUMBER
    try:
        await c.message.answer(f"Karta raqami: <code>{card_number}</code>\nUstiga bosib nusxalashingiz mumkin.", parse_mode="HTML")
        await c.answer("Karta raqami yuborildi (nusxalash uchun ustiga bosing).", show_alert=True)
    except Exception:
        await c.answer("Karta raqamini yuborolmadi.", show_alert=True)

@dp.callback_query(F.data == "upload_receipt")
async def upload_receipt_callback(c: types.CallbackQuery, state: FSMContext):
    await c.answer()
    await c.message.answer("📤 Iltimos, to'lov chekini (foto yoki PDF) yuboring:")
    await state.set_state(S.waiting_for_topup_receipt)

@dp.callback_query(F.data == "cancel_topup")
async def cancel_topup_callback(c: types.CallbackQuery, state: FSMContext):
    await c.answer("To'lov bekor qilindi.")
    try:
        await c.message.answer("To'lov bekor qilindi.", reply_markup=get_reply_keyboard(c.from_user.username or ""))
    except Exception:
        pass
    await state.clear()

@dp.message(S.waiting_for_topup_receipt)
async def handle_topup_receipt(m: Message, state: FSMContext):
    uid = str(m.from_user.id)
    data = await state.get_data()
    amount = data.get("topup_amount")
    if amount is None:
        await m.answer("❗ To'lov miqdori topilmadi. Iltimos, avval miqdorni kiriting.", reply_markup=get_reply_keyboard(m.from_user.username or ""))
        await state.clear()
        return
    caption = (
        f"🔔 To'lov fayli\n"
        f"Foydalanuvchi: @{m.from_user.username if m.from_user.username else m.from_user.full_name}\n"
        f"ID: {uid}\n"
        f"Summasi: {amount:,} so'm\n"
        "Admin: tasdiqlang yoki bekor qiling."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_topup|{uid}|{amount}")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"reject_topup|{uid}|{amount}")]
    ])
    try:
        if m.photo:
            photo = m.photo[-1].file_id
            await bot.send_photo(RECEIPT_CHANNEL, photo=photo, caption=caption, reply_markup=kb)
        elif m.document:
            await bot.send_document(RECEIPT_CHANNEL, document=m.document.file_id, caption=caption, reply_markup=kb)
        elif m.text:
            await bot.send_message(RECEIPT_CHANNEL, caption + "\nFoydalanuvchi xabar:\n" + m.text, reply_markup=kb)
        else:
            await m.answer("❗ Not supported file type. Iltimos, foto yoki PDF yuboring.")
            return
    except Exception as e:
        await m.answer("❗ Chekni admin kanaliga yuborishda xatolik yuz berdi. Iltimos, admin bilan bog'laning.")
        for admin in ADMINS:
            try:
                await bot.send_message(f"@{admin}", f"To'lov chekini yuborishda xatolik: {e}\nFoydalanuvchi: {uid}\nSummasi: {amount}")
            except Exception:
                continue
        await state.clear()
        return
    await m.answer("✅ Chek yuborildi! Administratsiya tekshiradi. Sizga xabar keladi.", reply_markup=get_reply_keyboard(m.from_user.username or ""))
    await state.clear()

@dp.callback_query(F.data.startswith("approve_topup|"))
async def approve_topup(c: types.CallbackQuery):
    if c.from_user.username not in ADMINS:
        await c.answer("Sizda bunday huquq yo'q.", show_alert=True)
        return
    try:
        parts = c.data.split("|")
        _, uid, amount = parts
        amount = int(amount)
    except Exception:
        await c.answer("❗ Noto'g'ri ma'lumot.", show_alert=True)
        return
    users.setdefault(uid, {}).setdefault("balance", 0)
    users[uid]["balance"] += amount
    save_json(USERS_FILE, users)
    try:
        if c.message.caption is not None:
            await c.message.edit_caption((c.message.caption or "") + f"\n✅ Tasdiqlandi: @{c.from_user.username}")
        else:
            await c.message.edit_text((c.message.text or "") + f"\n✅ Tasdiqlandi: @{c.from_user.username}")
    except Exception:
        pass
    try:
        await bot.send_message(uid, f"✅ To'lovingiz tasdiqlandi! Balansingizga {amount:,} so'm qo'shildi.\nYangi balans: {users[uid]['balance']:,} so'm")
    except Exception:
        pass
    await c.answer("To'lov muvaffaqiyatli tasdiqlandi va balansga qo'shildi.")

@dp.callback_query(F.data.startswith("reject_topup|"))
async def reject_topup(c: types.CallbackQuery):
    if c.from_user.username not in ADMINS:
        await c.answer("Sizda bunday huquq yo'q.", show_alert=True)
        return
    try:
        parts = c.data.split("|")
        _, uid, amount = parts
        amount = int(amount)
    except Exception:
        await c.answer("❗ Noto'g'ri ma'lumot.", show_alert=True)
        return
    try:
        if c.message.caption is not None:
            await c.message.edit_caption((c.message.caption or "") + f"\n❌ Bekor qilindi: @{c.from_user.username}")
        else:
            await c.message.edit_text((c.message.text or "") + f"\n❌ Bekor qilindi: @{c.from_user.username}")
    except Exception:
        pass
    try:
        await bot.send_message(uid, f"❌ Sizning to'lovingiz qabul qilinmadi. Iltimos, chekni tekshirib qayta yuboring yoki admin bilan bog'laning.")
    except Exception:
        pass
    await c.answer("To'lov bekor qilindi va foydalanuvchiga xabar yuborildi.")

@dp.message(F.successful_payment)
async def successful_payment(m: Message, state: FSMContext):
    uid = str(m.from_user.id)
    info = m.successful_payment.to_python()
    payload = info['invoice_payload']
    if "topup_" in payload:
        amount = int(payload.split("_")[1])
        users.setdefault(uid, {}).setdefault("balance", 0)
        users[uid]["balance"] += amount
        save_json(USERS_FILE, users)
        await m.answer(f"✅ Balansingiz to'ldirildi! Yangi balans: <b>{users[uid]['balance']} so'm</b>", parse_mode="HTML")
        await state.clear()
    elif "buy_" in payload:
        views = int(payload.split("_")[1])
        price = calculate_price(views)
        if price == -1:
            await m.answer("❌ Noto'g'ri ko'rish miqdori!")
            return
        users.setdefault(uid, {})["hashtags"] = get_hashtags(views)
        users[uid]["await_video"] = True
        users[uid]["views"] = views
        save_json(USERS_FILE, users)
        await state.set_state(S.waiting_for_video_link)
        await m.answer(f"✅ To'lov muvaffaqiyatli amalga oshirildi!\n💳 Miqdor: {info['total_amount']/100} so'm\n💰 Ko'rishlar: {views} ta\n📹 Endi video havolasini yuboring:", reply_markup=get_reply_keyboard(users[uid].get("username", "")))

# -----------------------------
# PROMOCODE
# -----------------------------
@dp.message(F.text == "🎟 Promokod")
async def ask_promocode(m: Message, state: FSMContext):
    await m.answer("🎟 Promokodingizni kiriting:")
    await state.set_state(S.waiting_for_promocode)

@dp.message(S.waiting_for_promocode)
async def process_promocode(m: Message, state: FSMContext):
    uid = str(m.from_user.id)
    code = m.text.strip().upper()
    if code not in promocodes:
        await m.answer("❌ Bunday promokod mavjud emas!")
        await state.clear()
        return
    pc = promocodes[code]
    used_by = pc.setdefault("used_by", {})
    total_used = sum(used_by.values())
    if uid in used_by:
        await m.answer("❌ Siz bu promokoddan allaqachon foydalangansiz!")
        await state.clear()
        return
    if len(used_by) >= pc.get("limit", 0):
        await m.answer("❌ Ushbu promokodning foydalanuvchi limiti tugagan!")
        await state.clear()
        return
    if total_used >= pc.get("amount", 0):
        await m.answer("❌ Ushbu promokodning bonus miqdori tugagan!")
        await state.clear()
        return
    remaining = pc.get("amount", 0) - total_used
    if pc["type"] == "views":
        give = min(1000, remaining)
    elif pc["type"] == "balance":
        give = min(1000000000, remaining) if remaining > 0 else 0
    elif pc["type"] == "referral":
        give = 1
    else:
        give = 0
    if pc["type"] == "views":
        users.setdefault(uid, {})["hashtags"] = get_hashtags(give)
        users[uid]["await_video"] = True
        users[uid]["views"] = give
        used_by[uid] = used_by.get(uid, 0) + give
        save_json(USERS_FILE, users)
        save_json(PROMOCODES_FILE, promocodes)
        ht = "\n".join(get_hashtags(give))
        await m.answer(
            f"🎉 Siz <b>{code}</b> promokodidan foydalandingiz!\n"
            f"✅ {give} ta ko'rish berildi.\n"
            f"🎯 Heshteglar:\n<pre>{ht}</pre>\n"
            f"📹 Endi video havolasini yuboring:",
            parse_mode="HTML"
        )
        await state.set_state(S.waiting_for_video_link)
    elif pc["type"] == "balance":
        users.setdefault(uid, {}).setdefault("balance", 0)
        users[uid]["balance"] += give
        used_by[uid] = used_by.get(uid, 0) + give
        save_json(USERS_FILE, users)
        save_json(PROMOCODES_FILE, promocodes)
        await m.answer(f"🎉 {give} so'm balansga qo'shildi!", parse_mode="HTML")
        await state.clear()
    elif pc["type"] == "referral":
        users.setdefault(uid, {}).setdefault("bonus_refs", 0)
        users[uid]["bonus_refs"] += 1
        used_by[uid] = used_by.get(uid, 0) + 1
        save_json(USERS_FILE, users)
        save_json(PROMOCODES_FILE, promocodes)
        await m.answer("🎉 1ta referal bonus sifatida berildi")
        await state.clear()

# -----------------------------
# REFERAL
# -----------------------------
@dp.message(F.text == "👬 Referal")
async def referal_combined(m: Message):
    uid = str(m.from_user.id)
    username = m.from_user.username or ""
    confirmed_refs = [r for r in users.get(uid, {}).get("refs", []) if users.get(r, {}).get("confirmed")]
    bonus = users.get(uid, {}).get("bonus_refs", 0)
    count = len(confirmed_refs) + bonus
    ref_link = f"https://t.me/{BOT_USERNAME}?start={uid}"
    msg = f"👬 Sizda hozirda <b>{count}</b> ta tasdiqlangan referal mavjud.\n"
    msg += f"🔗 Sizning shaxsiy havolangiz:\n<code>{ref_link}</code>\n"
    msg += "📤 Do'stlaringizga taklif qilish uchun pastdagi tugmani bosing 👇"
    share_text = "👆Bu suniy intelekt sizni instagramdagi videolaringizni mutlaqo bepul rekka chiqarib beradi."
    encoded_text = quote(f"{share_text}\n{ref_link}")
    encoded_url = quote(ref_link)
    url = f"https://t.me/share/url?url={encoded_url}&text={encoded_text}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Do'stlarga taklif qilish", url=url)]
    ])
    await m.answer(msg, parse_mode="HTML", reply_markup=kb)

# -----------------------------
# Adminga murojaat
# -----------------------------
@dp.message(F.text == "📞 Adminga murojaat")
async def contact_admin_start(m: Message, state: FSMContext):
    contact = config.get("contact")
    contact_label = contact if contact else "Hozircha kontakt belgilanmagan."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Murojaat yuborish", callback_data="start_contact")],
        [InlineKeyboardButton(text="👁 Isbot kanali", url="https://t.me/rekchi_tv")],
        [InlineKeyboardButton(text="🔎 Kontaktni ko'rsatish", callback_data="show_contact")]
    ])
    await m.answer(f"Adminga murojaat qilish:\nKontakt: {contact_label}", reply_markup=kb)

@dp.callback_query(F.data == "show_contact")
async def show_contact_cb(c: types.CallbackQuery):
    contact = config.get("contact")
    if contact:
        await c.answer(f"Kontakt: {contact}", show_alert=True)
    else:
        await c.answer("Kontakt belgilanmagan.", show_alert=True)

@dp.callback_query(F.data == "start_contact")
async def start_contact_cb(c: types.CallbackQuery):
    contact = config.get("contact")
    if contact:
        if isinstance(contact, str) and contact.startswith("@"):
            url = f"https://t.me/{contact}"
        elif contact.isdigit():
            url = f"https://t.me/{ADMINS[0]}"
        else:
            url = f"https://t.me/{ADMINS[0]}"
    else:
        url = f"https://t.me/{ADMINS[0]}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Adminga o'tish", url=url)]
    ])
    await c.message.edit_text("Siz adminga murojaat qilishingiz mumkin:", reply_markup=kb)
    await c.answer()

# -----------------------------
# VIDEO LIST
# -----------------------------
@dp.message(F.text.in_(["🎬 Video darslik", "Video darslik"]))
async def show_videos(m: Message, state: FSMContext):
    try:
        await state.clear()
    except Exception:
        pass
    username = m.from_user.username or ""
    if not videos:
        await m.answer("🎬 Video darsliklar hozircha yo'q.", reply_markup=get_reply_keyboard(username))
        return
    video_items = [(vid_id, meta) for vid_id, meta in videos.items() if isinstance(meta, dict)]
    kb_rows = []
    for idx, (vid_id, meta) in enumerate(video_items):
        kb_rows.append([InlineKeyboardButton(text=meta['title'], callback_data=f"v{idx}")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    uid = str(m.from_user.id)
    users.setdefault(uid, {})["__video_list"] = [vid_id for vid_id, _ in video_items]
    save_json(USERS_FILE, users)
    await m.answer("🎬 Video darsliklar ro'yxati:", reply_markup=kb)

@dp.callback_query(F.data.startswith("v"))
async def send_video_callback(c: types.CallbackQuery):
    uid = str(c.from_user.id)
    try:
        idx = int(c.data[1:])
        video_list = users.get(uid, {}).get("__video_list", [])
        if idx < 0 or idx >= len(video_list):
            raise IndexError()
        file_id = video_list[idx]
        meta = videos.get(file_id)
        if not meta or not isinstance(meta, dict):
            raise ValueError()
        await c.message.answer_video(
            video=file_id,
            caption=f"🎬 {meta['title']}\n{meta.get('desc', '')}"
        )
        await c.answer("✅ Video yuborildi!")
    except Exception:
        await c.answer("❌ Video topilmadi yoki xatolik yuz berdi!", show_alert=True)

# -----------------------------
# BUTTONS LIST
# -----------------------------
@dp.message(F.text == "📋 Tugmalar ro'yxati")
async def buttons_list(m: Message):
    if not buttons:
        await m.answer("❗ Tugma ro'yxati bo'sh.", reply_markup=get_reply_keyboard(m.from_user.username or ""))
        return
    msg = "📋 Tugmalar ro'yxati:\n"
    for key, btn in buttons.items():
        if isinstance(btn, dict):
            msg += f"\n{key}: {btn['msg']}"
    await m.answer(msg, reply_markup=get_reply_keyboard(m.from_user.username or ""))

# -----------------------------
# ADMIN PANEL
# -----------------------------
@dp.message(F.text == "⚙️ Admin panel")
async def admin_panel(m: Message):
    username = m.from_user.username or ""
    if username in ADMINS:
        await m.answer("⚙️ Admin panel", reply_markup=get_admin_keyboard())
    else:
        await m.answer("Siz admin emassiz!", reply_markup=get_reply_keyboard(username))

# --- Admin functions ---
@dp.message(F.text == "➕ Kanal qo'shish")
async def admin_add_channel(m: Message, state: FSMContext):
    if m.from_user.username not in ADMINS:
        return
    await m.answer("Kanal username (@kanal_nomi) yoki ID ni kiriting:")
    await state.set_state(S.admin_await_channel)

@dp.message(S.admin_await_channel)
async def admin_save_channel(m: Message, state: FSMContext):
    channel = m.text.strip()
    if channel:
        if channel not in config["channels"]:
            config["channels"].append(channel)
            save_json(CONFIG_FILE, config)
            await m.answer(f"✅ Kanal qo'shildi: {channel}", reply_markup=get_admin_keyboard())
        else:
            await m.answer("❗ Bu kanal allaqachon ro'yxatda bor.", reply_markup=get_admin_keyboard())
    else:
        await m.answer("❗ Kanal nomini yoki ID ni kiriting.", reply_markup=get_admin_keyboard())
    await state.clear()

@dp.message(F.text == "❌ Kanal o'chirish")
async def admin_remove_channel(m: Message, state: FSMContext):
    if m.from_user.username not in ADMINS:
        return
    chs = config.get("channels", [])
    if not chs:
        await m.answer("❗ Kanal ro'yxati bo'sh.", reply_markup=get_admin_keyboard())
        return
    msg = "O'chirish uchun kanalni tanlang:\n" + "\n".join(chs)
    await m.answer(msg)
    await state.set_state(S.admin_await_remove_channel)

@dp.message(S.admin_await_remove_channel)
async def admin_delete_channel(m: Message, state: FSMContext):
    channel = m.text.strip()
    if channel in config["channels"]:
        config["channels"].remove(channel)
        save_json(CONFIG_FILE, config)
        await m.answer(f"✅ Kanal o'chirildi: {channel}", reply_markup=get_admin_keyboard())
    else:
        await m.answer("❌ Kanal topilmadi.", reply_markup=get_admin_keyboard())
    await state.clear()

@dp.message(F.text == "🆕 Tugma qo'shish")
async def admin_add_button(m: Message, state: FSMContext):
    if m.from_user.username not in ADMINS:
        return
    await m.answer("Yangi tugma nomini kiriting:")
    await state.set_state(S.admin_await_button_title)

@dp.message(S.admin_await_button_title)
async def admin_save_button_title(m: Message, state: FSMContext):
    title = m.text.strip()
    if title in buttons:
        await m.answer("❗ Bu tugma allaqachon mavjud.", reply_markup=get_admin_keyboard())
        await state.clear()
        return
    await state.update_data(title=title)
    await m.answer("Tugma uchun xabarni kiriting:")
    await state.set_state(S.admin_await_button_msg)

@dp.message(S.admin_await_button_msg)
async def admin_save_button_msg(m: Message, state: FSMContext):
    data = await state.get_data()
    title = data.get("title")
    msg_text = m.text.strip()
    if title:
        buttons[title] = {"msg": msg_text}
        save_json(BUTTONS_FILE, buttons)
        await m.answer(f"✅ Tugma qo'shildi: {title}", reply_markup=get_admin_keyboard())
    else:
        await m.answer("Xatolik yuz berdi!", reply_markup=get_admin_keyboard())
    await state.clear()

@dp.message(F.text == "🗑 Tugma o'chirish")
async def admin_remove_button(m: Message, state: FSMContext):
    if m.from_user.username not in ADMINS:
        return
    if not buttons:
        await m.answer("❗ Tugma ro'yxati bo'sh.")
        return
    msg = "O'chirish uchun tugmani tanlang:\n" + "\n".join(buttons.keys())
    await m.answer(msg)
    await state.set_state(S.admin_await_remove_button)

@dp.message(S.admin_await_remove_button)
async def admin_delete_button(m: Message, state: FSMContext):
    title = m.text.strip()
    if title in buttons:
        del buttons[title]
        save_json(BUTTONS_FILE, buttons)
        await m.answer(f"✅ Tugma o'chirildi: {title}", reply_markup=get_admin_keyboard())
    else:
        await m.answer("❌ Tugma topilmadi.", reply_markup=get_admin_keyboard())
    await state.clear()

@dp.message(F.text == "🗑 Video o'chirish")
async def admin_remove_video(m: Message, state: FSMContext):
    if m.from_user.username not in ADMINS:
        return
    if not videos:
        await m.answer("❗ Video ro'yxati bo'sh.", reply_markup=get_admin_keyboard())
        return
    msg = "O'chirish uchun videoni tanlang:\n"
    for vid_id, meta in videos.items():
        if isinstance(meta, dict):
            msg += f"📹 {meta['title']}\n"
    await m.answer(msg + "\nVideo nomini kiriting:")
    await state.set_state(S.admin_await_remove_video)

@dp.message(S.admin_await_remove_video)
async def admin_delete_video(m: Message, state: FSMContext):
    title = m.text.strip()
    found = None
    for vid_id, meta in videos.items():
        if isinstance(meta, dict) and meta.get('title') == title:
            found = vid_id
            break
    if found:
        del videos[found]
        save_json(VIDEOS_META, videos)
        await m.answer(f"✅ Video o'chirildi: {title}", reply_markup=get_admin_keyboard())
    else:
        await m.answer("❌ Video topilmadi.", reply_markup=get_admin_keyboard())
    await state.clear()

@dp.message(F.text == "🎬 Video darslik qo'shish")
async def admin_add_video(m: Message, state: FSMContext):
    if m.from_user.username not in ADMINS:
        return
    await m.answer("Video sarlavhasini kiriting:")
    await state.set_state(S.admin_await_video_title)

@dp.message(S.admin_await_video_title)
async def admin_save_video_title(m: Message, state: FSMContext):
    title = m.text.strip()
    await state.update_data(title=title)
    await m.answer("Video faylini yuboring (.mp4):")
    await state.set_state(S.admin_await_video_file)

@dp.message(S.admin_await_video_file)
async def admin_save_video_file(m: Message, state: FSMContext):
    if m.from_user.username not in ADMINS:
        await state.clear()
        return
    data = await state.get_data()
    title = data.get("title", "Video")
    if not m.video:
        await m.answer("❗ Faqat video fayl yuboring!", reply_markup=get_admin_keyboard())
        return
    file_size = getattr(m.video, "file_size", None)
    if file_size and file_size > MAX_FILE_SIZE:
        await m.answer(f"❗ Fayl juda katta! Maksimal ruxsat etilgan hajm: {MAX_FILE_SIZE//(1024*1024)} MB.", reply_markup=get_admin_keyboard())
        await state.clear()
        return
    file_id = m.video.file_id
    try:
        file = await bot.get_file(file_id)
    except TelegramBadRequest:
        await m.answer("❗ Videoni olishda xatolik: fayl juda katta yoki Telegramdan olinmadi.", reply_markup=get_admin_keyboard())
        await state.clear()
        return
    except Exception:
        await m.answer("❗ Videoni olishda noma'lum xato yuz berdi.", reply_markup=get_admin_keyboard())
        await state.clear()
        return
    file_path = f"{DATA_DIR}/videos/{file_id}.mp4"
    try:
        await file.download(destination=file_path)
    except TelegramBadRequest:
        await m.answer("❗ Video yuklashda xatolik: fayl juda katta yoki yuklab bo'lmadi.", reply_markup=get_admin_keyboard())
        await state.clear()
        return
    except Exception:
        try:
            await bot.download_file(file.file_path, file_path)
        except Exception:
            await m.answer("❗ Video yuklashda xatolik yuz berdi.", reply_markup=get_admin_keyboard())
            await state.clear()
            return
    videos[file_id] = {"title": title, "desc": m.caption or "", "file_path": file_path}
    save_json(VIDEOS_META, videos)
    await m.answer(f"✅ Video darslik qo'shildi: {title}", reply_markup=get_admin_keyboard())
    await state.clear()

@dp.message(F.text == "👤 Adminga murojaat sozlash")
async def admin_set_contact_start(m: Message, state: FSMContext):
    if m.from_user.username not in ADMINS:
        return
    await m.answer("📎 Iltimos adminga murojaat uchun kontaktni kiriting.\nMasalan: @username yoki chat_id (raqam).")
    await state.set_state(S.admin_await_contact)

@dp.message(S.admin_await_contact)
async def admin_save_contact(m: Message, state: FSMContext):
    if m.from_user.username not in ADMINS:
        await state.clear()
        return
    contact = m.text.strip()
    if not contact:
        await m.answer("❗ Iltimos, to'g'ri kontakt kiriting.", reply_markup=get_admin_keyboard())
        await state.clear()
        return
    config["contact"] = contact
    save_json(CONFIG_FILE, config)
    await m.answer(f"✅ Admin kontakt saqlandi: {contact}", reply_markup=get_admin_keyboard())
    await state.clear()

# -----------------------------
# PROMOCODE admin flows
# -----------------------------
@dp.message(F.text == "🎟 Promokod qo'shish")
async def admin_add_promocode_start(m: Message, state: FSMContext):
    if m.from_user.username not in ADMINS:
        return
    await m.answer("Promokod nomini kiriting (masalan: YIL2025):")
    await state.set_state(S.admin_await_promocode_name)

@dp.message(S.admin_await_promocode_name)
async def admin_promocode_name(m: Message, state: FSMContext):
    name = m.text.strip().upper()
    if name in promocodes:
        await m.answer("❗ Bunday promokod allaqachon mavjud.")
        return
    await state.update_data(name=name)
    await m.answer("Bonus turini tanlang:\n1. views (ko'rishlar)\n2. balance (pul)\n3. referral (referal)", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="views")], [KeyboardButton(text="balance")], [KeyboardButton(text="referral")]],
        resize_keyboard=True
    ))
    await state.set_state(S.admin_await_promocode_type)

@dp.message(S.admin_await_promocode_type)
async def admin_promocode_type(m: Message, state: FSMContext):
    if m.text not in ["views", "balance", "referral"]:
        await m.answer("❌ Noto'g'ri tur. views / balance / referral kiriting.")
        return
    await state.update_data(type=m.text)
    await m.answer("Umumiy miqdorni kiriting (masalan: 10000):")
    await state.set_state(S.admin_await_promocode_amount)

@dp.message(S.admin_await_promocode_amount)
async def admin_promocode_amount(m: Message, state: FSMContext):
    if not m.text.isdigit():
        await m.answer("❗ Faqat son kiriting.")
        return
    await state.update_data(amount=int(m.text))
    await m.answer("Foydalanish limitini kiriting (nechta odam):")
    await state.set_state(S.admin_await_promocode_limit)

@dp.message(S.admin_await_promocode_limit)
async def admin_promocode_limit(m: Message, state: FSMContext):
    if not m.text.isdigit():
        await m.answer("❗ Faqat son kiriting.")
        return
    data = await state.get_data()
    promocodes[data["name"]] = {
        "type": data["type"],
        "amount": data["amount"],
        "limit": int(m.text),
        "used_by": {}
    }
    save_json(PROMOCODES_FILE, promocodes)
    await m.answer(f"✅ Promokod qo'shildi!\nKod: <b>{data['name']}</b>\nTur: {data['type']}\nMiqdor: {data['amount']}\nLimit: {m.text} ta", parse_mode="HTML", reply_markup=get_admin_keyboard())
    await state.clear()

@dp.message(F.text == "📋 Promokodlar")
async def list_promocodes(m: Message):
    if m.from_user.username not in ADMINS:
        return
    if not promocodes:
        await m.answer("🎟 Promokodlar mavjud emas.")
        return
    msg = "🎟 Promokodlar ro'yxati:\n"
    for name, pc in promocodes.items():
        used = sum(pc.get("used_by", {}).values())
        msg += f"<b>{name}</b>\nTur: {pc['type']}\nMiqdor: {pc['amount']}\nFoydalangan: {used}\nLimit: {pc['limit']} ta\n"
    await m.answer(msg, parse_mode="HTML")

@dp.message(F.text == "🗑 Promokod o'chirish")
async def admin_remove_promocode_start(m: Message, state: FSMContext):
    if m.from_user.username not in ADMINS:
        return
    if not promocodes:
        await m.answer("🎟 Promokodlar yo'q.")
        return
    await m.answer("O'chirish uchun promokod nomini kiriting:\n" + "\n".join(promocodes.keys()))
    await state.set_state(S.admin_await_remove_promocode)

@dp.message(S.admin_await_remove_promocode)
async def admin_remove_promocode(m: Message, state: FSMContext):
    code = m.text.strip().upper()
    if code in promocodes:
        del promocodes[code]
        save_json(PROMOCODES_FILE, promocodes)
        await m.answer(f"✅ {code} o'chirildi.")
    else:
        await m.answer("❌ Bunday promokod yo'q.")
    await state.clear()

# -----------------------------
# BROADCAST
# -----------------------------
@dp.message(F.text == "📢 Reklama tarqatish")
async def admin_broadcast(m: Message, state: FSMContext):
    if m.from_user.username not in ADMINS:
        return
    await m.answer("Reklama xabarini kiriting:")
    await state.set_state(S.admin_await_broadcast)

@dp.message(S.admin_await_broadcast)
async def admin_send_broadcast(m: Message, state: FSMContext):
    text = m.text.strip()
    for uid in users.keys():
        try:
            await bot.send_message(uid, text)
        except Exception:
            continue
    await m.answer("✅ Reklama tarqatildi!", reply_markup=get_admin_keyboard())
    await state.clear()

# -----------------------------
# STATISTIKA — TO'G'RI HISOB
# -----------------------------
@dp.message(F.text == "📊 Statistika")
async def show_stats(m: Message):
    if m.from_user.username not in ADMINS:
        await m.answer("Siz admin emassiz!")
        return
    users_data = load_json(USERS_FILE, {})
    total = len(users_data)
    confirmed = sum(1 for u in users_data.values() if u.get("confirmed"))
    referred_in = sum(1 for u in users_data.values() if u.get("ref_of"))        # Referal orqali kirgan
    referrers = sum(1 for u in users_data.values() if u.get("refs"))           # Referal yig'gan

    msg = (
        f"📊 <b>Bot statistikasi</b>\n\n"
        f"👥 Jami: <b>{total}</b>\n"
        f"✅ Tasdiqlangan: <b>{confirmed}</b>\n"
        f"📥 Referal orqali kirgan: <b>{referred_in}</b>\n"
        f"📤 Referal yig'gan: <b>{referrers}</b>"
    )
    await m.answer(msg, parse_mode="HTML")

# -----------------------------
# GLOBAL CANCEL / BACK
# -----------------------------
@dp.message(F.text == "❌ Bekor qilish")
async def global_cancel(m: Message, state: FSMContext):
    try:
        await state.clear()
    except Exception:
        pass
    await m.answer("Bekor qilindi. Asosiy menyu:", reply_markup=get_reply_keyboard(m.from_user.username or ""))

@dp.message(F.text == "⬅️ Ortga")
async def global_back(m: Message, state: FSMContext):
    try:
        await state.clear()
    except Exception:
        pass
    await m.answer("Orqaga qaytdingiz. Asosiy menyu:", reply_markup=get_reply_keyboard(m.from_user.username or ""))

@dp.callback_query(F.data == "cancel_any")
async def callback_cancel_any(c: types.CallbackQuery, state: FSMContext):
    try:
        await state.clear()
    except Exception:
        pass
    await c.answer()
    try:
        await c.message.answer("Bekor qilindi. Asosiy menyu:", reply_markup=get_reply_keyboard(c.from_user.username or ""))
    except Exception:
        pass

# -----------------------------
# GENERAL fallback (must be LAST)
# -----------------------------
@dp.message()
async def general_message_handler(m: Message, state: FSMContext):
    uid = str(m.from_user.id)
    current_state = await state.get_state()
    if current_state in [S.waiting_for_subscription.state, S.waiting_for_captcha.state]:
        return
    if not users.get(uid, {}).get("confirmed", False):
        not_subscribed = await get_not_subscribed(m.from_user.id)
        if not_subscribed:
            kb = make_subscribe_keyboard(not_subscribed)
            await m.answer("❗ Botdan foydalanish uchun kanallarga obuna bo'ling:", reply_markup=kb)
            await state.set_state(S.waiting_for_subscription)
            return
        c = generate_captcha()
        users.setdefault(uid, {})["captcha"] = c
        users[uid]["confirmed"] = False
        save_json(USERS_FILE, users)
        await m.answer(f"🤖 Botdan foydalanish uchun kodni kiriting:\n<b>{c}</b>", parse_mode="HTML")
        await state.set_state(S.waiting_for_captcha)
        return
    text = (m.text or "").strip()
    if text in buttons:
        await m.answer(buttons[text]["msg"], reply_markup=get_reply_keyboard(m.from_user.username or ""))
    elif text.lower() in ("menu", "/menu", "/stats"):
        if text == "/stats" and m.from_user.username in ADMINS:
            await show_stats(m)
        else:
            await m.answer("Asosiy menyu", reply_markup=get_reply_keyboard(m.from_user.username or ""))
    else:
        return

# -----------------------------
# START POLLING
# -----------------------------
if __name__ == "__main__":
    print("Bot ishga tushdi...")
    asyncio.run(dp.start_polling(bot))
