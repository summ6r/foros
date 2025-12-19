import asyncio
import json
import logging
import os

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from dotenv import load_dotenv
from datetime import datetime, timedelta

# =========================
# CONFIG
# =========================

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

DATA_FILE = "staff_data.json"
PHOTOS_DIR = "staff_photos"

os.makedirs(PHOTOS_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# =========================
# CATEGORIES
# =========================

KITCHEN_CATEGORIES = {
    "cold_kitchen": "🥗 Холодный цех",
    "hot_kitchen": "🍲 Горячий цех",
    "pastry_kitchen": "🍕 Мучной цех",
}

ALL_CATEGORIES = {
    "waiters": "🤵 Официанты",
    "bartenders": "🍸 Бар",
    **KITCHEN_CATEGORIES,
}

# =========================
# FSM
# =========================

class ReviewStates(StatesGroup):
    rating = State()
    text = State()

# =========================
# DATA
# =========================

def load_staff_data():
    if not os.path.exists(DATA_FILE):
        data = {}
        for k in ALL_CATEGORIES:
            if k in KITCHEN_CATEGORIES:
                data[k] = {"rating": 0, "reviews": []}
            else:
                data[k] = {}
        return data

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    for k in ALL_CATEGORIES:
        if k in KITCHEN_CATEGORIES:
            data.setdefault(k, {})
            data[k].setdefault("rating", 0)
            data[k].setdefault("reviews", [])
        else:
            data.setdefault(k, {})

    return data


def save_staff_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(staff_data, f, ensure_ascii=False, indent=2)


staff_data = load_staff_data()

# =========================
# HELPERS
# =========================
def get_top_staff(min_reviews=3, limit=10):
    result = []

    for category, staff_list in staff_data.items():
        # пропускаем кухонные цеха (они не сотрудники)
        if category in KITCHEN_CATEGORIES:
            continue

        for staff_id, staff in staff_list.items():
            if staff.get("rating", 0) > 0 and len(staff.get("reviews", [])) >= min_reviews:
                result.append({
                    "name": staff["name"],
                    "rating": staff["rating"],
                    "reviews": len(staff["reviews"]),
                    "category": ALL_CATEGORIES.get(category, category)
                })

    result.sort(key=lambda x: x["rating"], reverse=True)
    return result[:limit]

def get_photo_path(category, staff_id):
    photo = staff_data[category][staff_id].get("photo")
    if not photo:
        return None
    path = os.path.join(PHOTOS_DIR, photo)
    return path if os.path.exists(path) else None

def can_leave_review(obj, user_id):
    now = datetime.now()
    for r in obj["reviews"]:
        if r.get("user_id") == user_id:
            last_time = datetime.fromisoformat(r["date"])
            if now - last_time < timedelta(days=1):
                return False
    return True

async def smart_edit(cb: types.CallbackQuery, text: str, keyboard):
    if cb.message.photo:
        # ⛔ НЕ редактируем сообщение с фото
        await replace_message(cb, text, keyboard)
    else:
        await cb.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=keyboard
        )


# =========================
# KEYBOARDS
# =========================

def start_keyboard():
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="🚀 START"))
    return kb.as_markup(resize_keyboard=True)


def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="👥 Выбрать категорию", callback_data="select_category")
    kb.button(text="🏆 Топ сотрудников", callback_data="top_staff")
    kb.adjust(1)
    return kb.as_markup()


def category_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🤵 Официанты", callback_data="category_waiters")
    kb.button(text="👨‍🍳 Кухня", callback_data="select_kitchen")
    kb.button(text="🍸 Бар", callback_data="category_bartenders")
    kb.button(text="↩️ Назад", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()


def kitchen_keyboard():
    kb = InlineKeyboardBuilder()
    for key, name in KITCHEN_CATEGORIES.items():
        kb.button(text=name, callback_data=f"category_{key}")
    kb.button(text="↩️ Назад", callback_data="select_category")
    kb.adjust(1)
    return kb.as_markup()


def staff_list_keyboard(category):
    kb = InlineKeyboardBuilder()
    for staff_id, staff in staff_data[category].items():
        kb.button(text=staff["name"], callback_data=f"staff_{category}_{staff_id}")
    kb.button(text="↩️ Назад", callback_data="select_category")
    kb.adjust(1)
    return kb.as_markup()


def staff_actions_keyboard(category, staff_id):
    kb = InlineKeyboardBuilder()
    kb.button(text="⭐ Отзывы", callback_data=f"reviews_{category}_{staff_id}")
    kb.button(text="📝 Оставить отзыв", callback_data=f"review_{category}_{staff_id}")
    kb.button(text="↩️ Назад", callback_data=f"category_{category}")
    kb.adjust(1)
    return kb.as_markup()


def workshop_keyboard(category):
    kb = InlineKeyboardBuilder()
    kb.button(text="⭐ Отзывы", callback_data=f"reviews_workshop_{category}")
    kb.button(text="📝 Оставить отзыв", callback_data=f"review_workshop_{category}")
    kb.button(text="↩️ Назад", callback_data="select_kitchen")
    kb.adjust(1)
    return kb.as_markup()

# =========================
# HANDLERS
# =========================
@dp.callback_query(F.data == "main_menu")
async def back_to_main_menu(cb: types.CallbackQuery):
    await replace_message(
        cb,
        "📋 Главное меню\n\nВыберите действие:",
        main_menu()
    )
    await cb.answer()

async def replace_message(cb: types.CallbackQuery, text: str, keyboard):
    await cb.message.delete()
    await cb.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("🍇 Добро пожаловать в бот ресторана «Форос»! 🍷 \n\nСпасибо, что заглянули!\nЗдесь вы можете сделать две простые, но очень важные для нас вещи:\n\n1️⃣ Оставить отзыв о вашем посещении — поделитесь впечатлениями о кухне, обслуживании и атмосфере. Это поможет другим гостям и нам самим становиться лучше.\n\n2️⃣ Поддержать нашу команду чаевыми, если у вас остались тёплые эмоции после визита!", reply_markup=start_keyboard())

@dp.callback_query(F.data == "top_staff")
async def show_top_staff(cb: types.CallbackQuery):
    top = get_top_staff()

    if not top:
        text = "Пока нет сотрудников с достаточным количеством отзывов 😔"
    else:
        text = "<b>🏆 ТОП сотрудников</b>\n\n"
        for i, s in enumerate(top, start=1):
            text += (
                f"{i}. <b>{s['name']}</b>\n"
                f"   {s['category']}\n"
                f"   ⭐ {s['rating']} | 📝 {s['reviews']} отзывов\n\n"
            )

    kb = InlineKeyboardBuilder()
    kb.button(text="↩️ Назад", callback_data="select_category")

    await smart_edit(cb, text, kb.as_markup())
    await cb.answer()


@dp.message(F.text == "🚀 START")
async def start_pressed(message: types.Message):
    await message.answer("📋 Главное меню\n\nЗдесь вы можете поделиться своим мнением о визите в ресторан «Форос». Выберите действие:\n\n⭐ Топ сотрудников\n\nПосмотрите рейтинг наших коллег, отмеченных в отзывах гостей. Узнайте, кто создаёт самые тёплые впечатления!\n\n📝 Оставить отзыв или поддержать нашу команду\nВыберите категорию, чтобы ваша благодарность или совет попали точно адресату:", reply_markup=main_menu())


@dp.callback_query(F.data == "select_category")
async def select_category(cb: types.CallbackQuery):
    await replace_message(cb, "Выберите категорию чтобы оставить отзыв 🗨️ или оставить на чай ☕:", category_keyboard())
    await cb.answer()


@dp.callback_query(F.data == "select_kitchen")
async def select_kitchen(cb: types.CallbackQuery):
    await replace_message(cb, "Выберите цех кухни:", kitchen_keyboard())
    await cb.answer()


@dp.callback_query(F.data.startswith("category_"))
async def show_category(cb: types.CallbackQuery):
    category = cb.data.replace("category_", "")

    if category in KITCHEN_CATEGORIES:
        workshop = staff_data[category]
        text = (
            f"<b>{KITCHEN_CATEGORIES[category]}</b>\n"
            f"⭐ Рейтинг: {workshop['rating']}/5\n"
            f"📝 Отзывов: {len(workshop['reviews'])}"
        )
        await smart_edit(cb, text, workshop_keyboard(category))
        await cb.answer()
        return

    await smart_edit(cb, "Выберите сотрудника:", staff_list_keyboard(category))
    await cb.answer()


@dp.callback_query(F.data.startswith("staff_"))
async def show_staff(cb: types.CallbackQuery):
    parts = cb.data.split("_")
    staff_id = parts[-1]
    category = "_".join(parts[1:-1])

    staff = staff_data[category][staff_id]
    photo = get_photo_path(category, staff_id)

    text = (
        f"<b>{staff['name']}</b>\n"
        f"💳 Чаевые официанту: {staff['phone']}\n"
        f"⭐ Рейтинг: {staff['rating']}/5"
    )

    # ⛔ НИКОГДА не пытаемся менять фото у сообщения
    await cb.message.delete()

    if photo:
        await cb.message.answer_photo(
            photo=types.FSInputFile(photo),
            caption=text,
            parse_mode="HTML",
            reply_markup=staff_actions_keyboard(category, staff_id)
        )
    else:
        await cb.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=staff_actions_keyboard(category, staff_id)
        )

    await cb.answer()

# =========================
# REVIEWS VIEW
# =========================

@dp.callback_query(F.data.startswith("reviews_workshop_"))
async def show_workshop_reviews(cb: types.CallbackQuery):
    category = cb.data.replace("reviews_workshop_", "")
    workshop = staff_data[category]

    if not workshop["reviews"]:
        text = "Пока нет отзывов."
    else:
        text = "<b>Отзывы о цехе:</b>\n\n"
        for r in workshop["reviews"][-5:]:
            text += f"⭐ {r['rating']} — {r['user']}\n{r['text']}\n\n"

    await smart_edit(cb, text, workshop_keyboard(category))
    await cb.answer()


@dp.callback_query(F.data.startswith("reviews_"))
async def show_staff_reviews(cb: types.CallbackQuery):
    parts = cb.data.split("_")
    staff_id = parts[-1]
    category = "_".join(parts[1:-1])

    staff = staff_data[category][staff_id]

    if not staff["reviews"]:
        text = "Пока нет отзывов."
    else:
        text = "<b>Отзывы:</b>\n\n"
        for r in staff["reviews"][-5:]:
            text += f"⭐ {r['rating']} — {r['user']}\n{r['text']}\n\n"

    kb = InlineKeyboardBuilder()
    kb.button(text="↩️ Назад", callback_data=f"staff_{category}_{staff_id}")

    await smart_edit(cb, text, kb.as_markup())
    await cb.answer()

# =========================
# REVIEWS ADD
# =========================

@dp.callback_query(F.data.startswith("review_workshop_"))
async def review_workshop_start(cb: types.CallbackQuery, state: FSMContext):
    category = cb.data.replace("review_workshop_", "")
    obj = staff_data[category]

    if not can_leave_review(obj, cb.from_user.id):
        await cb.answer(
            "❌ Вы уже оставляли отзыв этому цеху сегодня",
            show_alert=True
        )
        return

    await state.update_data(category=category, workshop=True)
    await state.set_state(ReviewStates.rating)

    kb = InlineKeyboardBuilder()
    for i in range(1, 6):
        kb.button(text=f"{i} ⭐", callback_data=f"rate_{i}")
    kb.adjust(5)

    await smart_edit(cb, "Оцените цех:", kb.as_markup())
    await cb.answer()

@dp.callback_query(F.data.startswith("review_"))
async def review_staff_start(cb: types.CallbackQuery, state: FSMContext):
    parts = cb.data.split("_")
    staff_id = parts[-1]
    category = "_".join(parts[1:-1])
    obj = staff_data[category][staff_id]

    if not can_leave_review(obj, cb.from_user.id):
        await cb.answer(
            "❌ Вы уже оставляли отзыв этому сотруднику сегодня",
            show_alert=True
        )
        return

    await state.update_data(category=category, staff_id=staff_id)
    await state.set_state(ReviewStates.rating)

    kb = InlineKeyboardBuilder()
    for i in range(1, 6):
        kb.button(text=f"{i} ⭐", callback_data=f"rate_{i}")
    kb.adjust(5)

    await smart_edit(cb, "Выберите оценку:", kb.as_markup())
    await cb.answer()


@dp.callback_query(ReviewStates.rating, F.data.startswith("rate_"))
async def review_rating(cb: types.CallbackQuery, state: FSMContext):
    rating = int(cb.data.replace("rate_", ""))
    await state.update_data(rating=rating)
    await state.set_state(ReviewStates.text)
    await smart_edit(cb, "Напишите отзыв:", None)
    await cb.answer()


@dp.message(ReviewStates.text)
async def review_text(message: types.Message, state: FSMContext):
    data = await state.get_data()

    if data.get("workshop"):
        obj = staff_data[data["category"]]
    else:
        obj = staff_data[data["category"]][data["staff_id"]]

    obj["reviews"].append({
    "user_id": message.from_user.id,
    "user": message.from_user.full_name,
    "rating": data["rating"],
    "text": message.text,
    "date": datetime.now().isoformat()
    })

    obj["rating"] = round(
        sum(r["rating"] for r in obj["reviews"]) / len(obj["reviews"]), 1
    )

    save_staff_data()
    await state.clear()

    # ✅ ВАЖНО: возвращаем кнопку START
    await message.answer(
        "✅ Отзыв сохранён!\n\nНажмите 🚀 START, чтобы оставить отзыв или оставить на чай!",
        reply_markup=start_keyboard()
    )

# =========================
# FALLBACK (кнопка START всегда видна)
# =========================

@dp.message()
async def fallback(message: types.Message):
    # Если пользователь не находится в FSM (не пишет отзыв)
    state = dp.fsm.get_context(bot, message.chat.id, message.from_user.id)
    current_state = await state.get_state()

    if current_state is None:
        await message.answer(
            "Нажмите 🚀 START для начала работы",
            reply_markup=start_keyboard()
        )

# =========================
# RUN
# =========================

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
