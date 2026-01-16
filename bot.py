import os
import logging
import asyncio
from datetime import datetime
from typing import Optional, Callable, Dict, Any, Awaitable
import io
import html

import requests
from aiogram import Bot, Dispatcher, Router, F, BaseMiddleware
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, TelegramObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from dotenv import load_dotenv

import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

if not BOT_TOKEN:
    raise ValueError("Не указан TELEGRAM_BOT_TOKEN в переменных окружения!")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

users = {}

WORKOUT_CALORIES = {
    "бег": 10, "running": 10,
    "ходьба": 4, "walking": 4,
    "велосипед": 8, "cycling": 8,
    "плавание": 9, "swimming": 9,
    "йога": 3, "yoga": 3,
    "силовая": 6, "strength": 6,
    "кардио": 8, "cardio": 8,
    "танцы": 6, "dancing": 6,
}


class ProfileStates(StatesGroup):
    waiting_for_weight = State()
    waiting_for_height = State()
    waiting_for_age = State()
    waiting_for_gender = State()
    waiting_for_activity = State()
    waiting_for_city = State()
    waiting_for_calorie_goal = State()


class FoodStates(StatesGroup):
    waiting_for_grams = State()


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if isinstance(event, Message):
            logger.info(f"User {event.from_user.id} ({event.from_user.username}): {event.text}")
        return await handler(event, data)


def esc(text) -> str:
    """Экранировать HTML"""
    return html.escape(str(text)) if text else ""


def get_weather_temperature(city: str) -> Optional[float]:
    if not WEATHER_API_KEY:
        logger.warning("OPENWEATHER_API_KEY не указан")
        return None
    try:
        url = "http://api.openweathermap.org/data/2.5/weather"
        params = {"q": city, "appid": WEATHER_API_KEY, "units": "metric"}
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()["main"]["temp"]
        logger.error(f"Ошибка получения погоды: {response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Ошибка при запросе погоды: {e}")
        return None


def get_food_info(product_name: str) -> Optional[dict]:
    try:
        url = "https://world.openfoodfacts.org/cgi/search.pl"
        params = {"action": "process", "search_terms": product_name, "json": "true"}
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            products = response.json().get('products', [])
            if products:
                p = products[0]
                return {
                    'name': p.get('product_name', product_name),
                    'calories': p.get('nutriments', {}).get('energy-kcal_100g', 0)
                }
        return None
    except Exception as e:
        logger.error(f"Ошибка при запросе продукта: {e}")
        return None


def calculate_water_goal(weight: float, activity_minutes: int, temperature: Optional[float]) -> int:
    base = weight * 30
    activity_bonus = (activity_minutes // 30) * 500
    heat_bonus = 0
    if temperature is not None:
        if temperature > 30:
            heat_bonus = 1000
        elif temperature > 25:
            heat_bonus = 500
    return int(base + activity_bonus + heat_bonus)


def calculate_calorie_goal(weight: float, height: float, age: int, gender: str, activity_minutes: int) -> int:
    if gender.lower() in ['м', 'мужской', 'male', 'm']:
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    
    if activity_minutes < 15:
        activity_factor = 1.2
    elif activity_minutes < 30:
        activity_factor = 1.375
    elif activity_minutes < 60:
        activity_factor = 1.55
    elif activity_minutes < 90:
        activity_factor = 1.725
    else:
        activity_factor = 1.9
    return int(bmr * activity_factor)


def get_user_data(user_id: int) -> dict:
    if user_id not in users:
        users[user_id] = {
            "weight": None, "height": None, "age": None, "gender": None,
            "activity": 0, "city": None,
            "water_goal": 2000, "calorie_goal": 2000,
            "logged_water": 0, "logged_calories": 0, "burned_calories": 0,
            "last_reset": datetime.now().date(),
            "water_history": [], "calorie_history": [],
        }
    
    user_data = users[user_id]
    today = datetime.now().date()
    if user_data.get("last_reset") != today:
        if user_data.get("logged_water", 0) > 0 or user_data.get("logged_calories", 0) > 0:
            user_data["water_history"].append({
                "date": str(user_data.get("last_reset")),
                "logged": user_data.get("logged_water", 0),
                "goal": user_data.get("water_goal", 2000)
            })
            user_data["calorie_history"].append({
                "date": str(user_data.get("last_reset")),
                "logged": user_data.get("logged_calories", 0),
                "burned": user_data.get("burned_calories", 0),
                "goal": user_data.get("calorie_goal", 2000)
            })
        user_data["logged_water"] = 0
        user_data["logged_calories"] = 0
        user_data["burned_calories"] = 0
        user_data["last_reset"] = today
    return user_data


def update_goals(user_id: int):
    user_data = get_user_data(user_id)
    if all([user_data["weight"], user_data["height"], user_data["age"], user_data["gender"]]):
        temperature = get_weather_temperature(user_data["city"]) if user_data["city"] else None
        user_data["water_goal"] = calculate_water_goal(user_data["weight"], user_data["activity"], temperature)
        user_data["calorie_goal"] = calculate_calorie_goal(
            user_data["weight"], user_data["height"], user_data["age"], user_data["gender"], user_data["activity"]
        )


@router.message(CommandStart())
async def cmd_start(message: Message):
    logger.info(f"User {message.from_user.id} started the bot")
    await message.answer(
        "👋 <b>Привет! Я бот для трекинга воды и калорий!</b>\n\n"
        "🎯 Я помогу тебе:\n"
        "• Рассчитать дневную норму воды и калорий\n"
        "• Отслеживать потребление воды и еды\n"
        "• Фиксировать тренировки\n\n"
        "📝 <b>Доступные команды:</b>\n\n"
        "/set_profile — Настроить профиль\n"
        "/log_water &lt;мл&gt; — Записать воду\n"
        "/log_food &lt;продукт&gt; — Записать еду\n"
        "/log_workout &lt;тип&gt; &lt;мин&gt; — Записать тренировку\n"
        "/check_progress — Посмотреть прогресс\n"
        "/progress_chart — График прогресса\n"
        "/recommendations — Получить рекомендации\n"
        "/help — Справка\n\n"
        "<i>Начни с настройки профиля командой /set_profile</i>",
        parse_mode=ParseMode.HTML
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    logger.info(f"User {message.from_user.id} requested help")
    await message.answer(
        "📖 <b>Справка по командам:</b>\n\n"
        "<b>Настройка профиля:</b>\n"
        "/set_profile — Настроить вес, рост, возраст, город и активность\n\n"
        "<b>Логирование:</b>\n"
        "/log_water 500 — Записать 500 мл воды\n"
        "/log_food банан — Записать еду (бот найдёт калорийность)\n"
        "/log_workout бег 30 — Записать 30 минут бега\n\n"
        "<b>Типы тренировок:</b>\n"
        "бег, ходьба, велосипед, плавание, йога, силовая, кардио, танцы\n\n"
        "<b>Статистика:</b>\n"
        "/check_progress — Текущий прогресс по воде и калориям\n"
        "/progress_chart — Графики за последние дни\n\n"
        "<b>Дополнительно:</b>\n"
        "/recommendations — Рекомендации по питанию и тренировкам",
        parse_mode=ParseMode.HTML
    )


@router.message(Command("set_profile"))
async def cmd_set_profile(message: Message, state: FSMContext):
    logger.info(f"User {message.from_user.id} started profile setup")
    await state.set_state(ProfileStates.waiting_for_weight)
    await message.answer("⚙️ <b>Настройка профиля</b>\n\nВведите ваш вес (в кг):", parse_mode=ParseMode.HTML)


@router.message(ProfileStates.waiting_for_weight)
async def process_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text.replace(",", "."))
        if weight < 20 or weight > 300:
            await message.answer("❌ Введите корректный вес (от 20 до 300 кг):")
            return
        await state.update_data(weight=weight)
        await state.set_state(ProfileStates.waiting_for_height)
        await message.answer("📏 Введите ваш рост (в см):")
    except ValueError:
        await message.answer("❌ Введите число. Например: 70")


@router.message(ProfileStates.waiting_for_height)
async def process_height(message: Message, state: FSMContext):
    try:
        height = float(message.text.replace(",", "."))
        if height < 100 or height > 250:
            await message.answer("❌ Введите корректный рост (от 100 до 250 см):")
            return
        await state.update_data(height=height)
        await state.set_state(ProfileStates.waiting_for_age)
        await message.answer("🎂 Введите ваш возраст:")
    except ValueError:
        await message.answer("❌ Введите число. Например: 184")


@router.message(ProfileStates.waiting_for_age)
async def process_age(message: Message, state: FSMContext):
    try:
        age = int(message.text)
        if age < 10 or age > 120:
            await message.answer("❌ Введите корректный возраст (от 10 до 120):")
            return
        await state.update_data(age=age)
        await state.set_state(ProfileStates.waiting_for_gender)
        await message.answer("👤 Введите ваш пол (М/Ж):")
    except ValueError:
        await message.answer("❌ Введите число. Например: 26")


@router.message(ProfileStates.waiting_for_gender)
async def process_gender(message: Message, state: FSMContext):
    gender = message.text.strip().lower()
    if gender not in ['м', 'ж', 'мужской', 'женский', 'm', 'f', 'male', 'female']:
        await message.answer("❌ Введите М или Ж:")
        return
    await state.update_data(gender=gender)
    await state.set_state(ProfileStates.waiting_for_activity)
    await message.answer("🏃 Сколько минут активности у вас в день в среднем?")


@router.message(ProfileStates.waiting_for_activity)
async def process_activity(message: Message, state: FSMContext):
    try:
        activity = int(message.text)
        if activity < 0 or activity > 480:
            await message.answer("❌ Введите корректное время (от 0 до 480 минут):")
            return
        await state.update_data(activity=activity)
        await state.set_state(ProfileStates.waiting_for_city)
        await message.answer("🌍 В каком городе вы находитесь? (на английском, например: Moscow)")
    except ValueError:
        await message.answer("❌ Введите число. Например: 45")


@router.message(ProfileStates.waiting_for_city)
async def process_city(message: Message, state: FSMContext):
    city = message.text.strip()
    await state.update_data(city=city)
    await state.set_state(ProfileStates.waiting_for_calorie_goal)
    data = await state.get_data()
    suggested = calculate_calorie_goal(data["weight"], data["height"], data["age"], data["gender"], data["activity"])
    await message.answer(
        f"🎯 Рекомендуемая норма калорий: <b>{suggested} ккал</b>\n\n"
        "Введите желаемую цель калорий или нажмите /skip для использования рекомендуемой:",
        parse_mode=ParseMode.HTML
    )


@router.message(ProfileStates.waiting_for_calorie_goal)
async def process_calorie_goal(message: Message, state: FSMContext):
    data = await state.get_data()
    calorie_goal = None
    if message.text != "/skip":
        try:
            calorie_goal = int(message.text)
            if calorie_goal < 1000 or calorie_goal > 5000:
                await message.answer("❌ Введите корректную цель (от 1000 до 5000 ккал) или /skip:")
                return
        except ValueError:
            await message.answer("❌ Введите число или /skip:")
            return
    
    user_id = message.from_user.id
    user_data = get_user_data(user_id)
    user_data.update({
        "weight": data["weight"], "height": data["height"], "age": data["age"],
        "gender": data["gender"], "activity": data["activity"], "city": data["city"]
    })
    if calorie_goal:
        user_data["calorie_goal"] = calorie_goal
    update_goals(user_id)
    await state.clear()
    
    temp_info = ""
    if user_data["city"]:
        temp = get_weather_temperature(user_data["city"])
        if temp is not None:
            temp_info = f"🌡️ Температура в {esc(user_data['city'])}: {temp}°C\n"
    
    logger.info(f"User {user_id} completed profile setup")
    await message.answer(
        f"✅ <b>Профиль сохранён!</b>\n\n"
        f"👤 Вес: {user_data['weight']} кг\n"
        f"📏 Рост: {user_data['height']} см\n"
        f"🎂 Возраст: {user_data['age']} лет\n"
        f"👫 Пол: {esc(user_data['gender'])}\n"
        f"🏃 Активность: {user_data['activity']} мин/день\n"
        f"🌍 Город: {esc(user_data['city'])}\n\n"
        f"{temp_info}"
        f"💧 Норма воды: <b>{user_data['water_goal']} мл</b>\n"
        f"🔥 Норма калорий: <b>{user_data['calorie_goal']} ккал</b>",
        parse_mode=ParseMode.HTML
    )


@router.message(Command("log_water"))
async def cmd_log_water(message: Message):
    logger.info(f"User {message.from_user.id} logging water: {message.text}")
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Укажите количество воды.\nПример: <code>/log_water 500</code>", parse_mode=ParseMode.HTML)
        return
    try:
        amount = int(args[1])
        if amount <= 0:
            await message.answer("❌ Количество должно быть положительным!")
            return
        if amount > 5000:
            await message.answer("❌ Слишком много за один раз! Максимум 5000 мл.")
            return
    except ValueError:
        await message.answer("❌ Введите число. Пример: <code>/log_water 500</code>", parse_mode=ParseMode.HTML)
        return
    
    user_id = message.from_user.id
    user_data = get_user_data(user_id)
    update_goals(user_id)
    user_data["logged_water"] += amount
    remaining = max(0, user_data["water_goal"] - user_data["logged_water"])
    progress = min(100, (user_data["logged_water"] / user_data["water_goal"]) * 100)
    
    if progress >= 100:
        emoji, status = "🎉", "Цель достигнута!"
    elif progress >= 75:
        emoji, status = "💪", "Отлично, почти готово!"
    elif progress >= 50:
        emoji, status = "👍", "Больше половины пути!"
    else:
        emoji, status = "💧", "Продолжай в том же духе!"
    
    await message.answer(
        f"{emoji} Записано: <b>+{amount} мл воды</b>\n\n"
        f"📊 Прогресс: {user_data['logged_water']} / {user_data['water_goal']} мл ({progress:.0f}%)\n"
        f"💧 Осталось: {remaining} мл\n\n"
        f"<i>{status}</i>",
        parse_mode=ParseMode.HTML
    )


@router.message(Command("log_food"))
async def cmd_log_food(message: Message, state: FSMContext):
    logger.info(f"User {message.from_user.id} logging food: {message.text}")
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❌ Укажите название продукта.\nПример: <code>/log_food банан</code>", parse_mode=ParseMode.HTML)
        return
    
    product_name = args[1].strip()
    food_info = get_food_info(product_name)
    
    if not food_info or not food_info.get("calories"):
        await message.answer(
            f"🔍 Продукт <b>{esc(product_name)}</b> не найден в базе.\n\n"
            "Введите калорийность вручную (ккал на 100г) или /cancel для отмены:",
            parse_mode=ParseMode.HTML
        )
        await state.update_data(product_name=product_name, manual_calories=True)
        await state.set_state(FoodStates.waiting_for_grams)
        return
    
    await state.update_data(product_name=food_info["name"] or product_name, calories_per_100g=food_info["calories"])
    await state.set_state(FoodStates.waiting_for_grams)
    await message.answer(
        f"🍽️ <b>{esc(food_info['name'] or product_name)}</b> — {food_info['calories']:.0f} ккал на 100 г.\n\n"
        "Сколько грамм вы съели?",
        parse_mode=ParseMode.HTML
    )


@router.message(FoodStates.waiting_for_grams)
async def process_food_grams(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено.")
        return
    
    data = await state.get_data()
    if data.get("manual_calories"):
        try:
            calories_per_100g = float(message.text.replace(",", "."))
            await state.update_data(calories_per_100g=calories_per_100g, manual_calories=False)
            await message.answer("Теперь введите количество грамм:")
            return
        except ValueError:
            await message.answer("❌ Введите число (калории на 100г) или /cancel:")
            return
    
    try:
        grams = float(message.text.replace(",", "."))
        if grams <= 0:
            await message.answer("❌ Количество должно быть положительным!")
            return
        if grams > 5000:
            await message.answer("❌ Слишком много! Максимум 5000 грамм.")
            return
    except ValueError:
        await message.answer("❌ Введите число. Например: 150")
        return
    
    total_calories = (data.get("calories_per_100g", 0) * grams) / 100
    user_id = message.from_user.id
    user_data = get_user_data(user_id)
    user_data["logged_calories"] += total_calories
    await state.clear()
    
    logger.info(f"User {user_id} logged food: {data['product_name']}, {grams}g, {total_calories:.1f} kcal")
    await message.answer(
        f"✅ Записано: <b>{esc(data['product_name'])}</b>\n\n"
        f"🍽️ Порция: {grams:.0f} г\n"
        f"🔥 Калории: +{total_calories:.1f} ккал\n\n"
        f"📊 Всего за день: {user_data['logged_calories']:.0f} / {user_data['calorie_goal']} ккал",
        parse_mode=ParseMode.HTML
    )


@router.message(Command("log_workout"))
async def cmd_log_workout(message: Message):
    logger.info(f"User {message.from_user.id} logging workout: {message.text}")
    args = message.text.split()
    if len(args) < 3:
        workout_types = ", ".join(WORKOUT_CALORIES.keys())
        await message.answer(
            f"❌ Укажите тип тренировки и время.\n"
            f"Пример: <code>/log_workout бег 30</code>\n\n"
            f"Доступные типы: {workout_types}",
            parse_mode=ParseMode.HTML
        )
        return
    
    workout_type = args[1].lower()
    try:
        duration = int(args[2])
        if duration <= 0:
            await message.answer("❌ Время должно быть положительным!")
            return
        if duration > 480:
            await message.answer("❌ Слишком долго! Максимум 480 минут.")
            return
    except ValueError:
        await message.answer("❌ Введите время в минутах. Пример: <code>/log_workout бег 30</code>", parse_mode=ParseMode.HTML)
        return
    
    cal_per_min = WORKOUT_CALORIES.get(workout_type, 5)
    burned_calories = cal_per_min * duration
    extra_water = (duration // 30) * 200
    if duration % 30 >= 15:
        extra_water += 100
    
    user_id = message.from_user.id
    user_data = get_user_data(user_id)
    user_data["burned_calories"] += burned_calories
    user_data["water_goal"] += extra_water
    
    workout_emoji = {
        "бег": "🏃‍♂️", "running": "🏃‍♂️", "ходьба": "🚶", "walking": "🚶",
        "велосипед": "🚴", "cycling": "🚴", "плавание": "🏊", "swimming": "🏊",
        "йога": "🧘", "yoga": "🧘", "силовая": "💪", "strength": "💪",
        "кардио": "❤️", "cardio": "❤️", "танцы": "💃", "dancing": "💃",
    }
    emoji = workout_emoji.get(workout_type, "🏋️")
    
    logger.info(f"User {user_id} logged workout: {workout_type}, {duration} min, {burned_calories} kcal burned")
    await message.answer(
        f"{emoji} <b>{esc(workout_type.capitalize())}</b> — {duration} минут\n\n"
        f"🔥 Сожжено: <b>{burned_calories} ккал</b>\n"
        f"💧 Дополнительно выпейте: <b>{extra_water} мл воды</b>\n\n"
        f"📊 Всего сожжено за день: {user_data['burned_calories']} ккал",
        parse_mode=ParseMode.HTML
    )


@router.message(Command("check_progress"))
async def cmd_check_progress(message: Message):
    logger.info(f"User {message.from_user.id} checking progress")
    user_id = message.from_user.id
    user_data = get_user_data(user_id)
    update_goals(user_id)
    
    water_logged = user_data["logged_water"]
    water_goal = user_data["water_goal"]
    water_remaining = max(0, water_goal - water_logged)
    water_progress = min(100, (water_logged / water_goal) * 100) if water_goal > 0 else 0
    
    cal_logged = user_data["logged_calories"]
    cal_goal = user_data["calorie_goal"]
    cal_burned = user_data["burned_calories"]
    cal_balance = cal_logged - cal_burned
    cal_remaining = max(0, cal_goal - cal_balance)
    cal_progress = min(100, (cal_balance / cal_goal) * 100) if cal_goal > 0 else 0
    
    def progress_bar(percent):
        filled = int(percent / 10)
        return "▓" * filled + "░" * (10 - filled)
    
    weather_info = ""
    if user_data.get("city"):
        temp = get_weather_temperature(user_data["city"])
        if temp is not None:
            weather_info = f"🌡️ <b>Погода в {esc(user_data['city'])}:</b> {temp}°C\n\n"
    
    await message.answer(
        f"📊 <b>Ваш прогресс на сегодня:</b>\n\n"
        f"{weather_info}"
        f"💧 <b>Вода:</b>\n"
        f"{progress_bar(water_progress)} {water_progress:.0f}%\n"
        f"• Выпито: {water_logged} мл из {water_goal} мл\n"
        f"• Осталось: {water_remaining} мл\n\n"
        f"🔥 <b>Калории:</b>\n"
        f"{progress_bar(cal_progress)} {cal_progress:.0f}%\n"
        f"• Потреблено: {cal_logged:.0f} ккал\n"
        f"• Сожжено: {cal_burned} ккал\n"
        f"• Баланс: {cal_balance:.0f} ккал из {cal_goal} ккал\n"
        f"• До цели: {cal_remaining:.0f} ккал",
        parse_mode=ParseMode.HTML
    )


@router.message(Command("progress_chart"))
async def cmd_progress_chart(message: Message):
    logger.info(f"User {message.from_user.id} requesting progress chart")
    user_id = message.from_user.id
    user_data = get_user_data(user_id)
    
    water_history = user_data.get("water_history", [])
    calorie_history = user_data.get("calorie_history", [])
    
    today_water = {"date": str(datetime.now().date()), "logged": user_data.get("logged_water", 0), "goal": user_data.get("water_goal", 2000)}
    today_calories = {"date": str(datetime.now().date()), "logged": user_data.get("logged_calories", 0), "burned": user_data.get("burned_calories", 0), "goal": user_data.get("calorie_goal", 2000)}
    
    water_data = water_history[-6:] + [today_water]
    calorie_data = calorie_history[-6:] + [today_calories]
    
    if len(water_data) < 2 and len(calorie_data) < 2:
        await message.answer("📊 Недостаточно данных для построения графика.\nИспользуйте бота несколько дней, чтобы увидеть статистику!")
        return
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    fig.patch.set_facecolor('#1a1a2e')
    
    if water_data:
        dates = [d["date"][-5:] for d in water_data]
        logged = [d["logged"] for d in water_data]
        goals = [d["goal"] for d in water_data]
        ax1.set_facecolor('#16213e')
        ax1.bar(dates, logged, color='#4fc3f7', label='Выпито', alpha=0.8)
        ax1.plot(dates, goals, color='#ff6b6b', marker='o', linestyle='--', label='Цель', linewidth=2)
        ax1.set_xlabel('Дата', color='white')
        ax1.set_ylabel('Вода (мл)', color='white')
        ax1.set_title('💧 Потребление воды', color='white', fontsize=14)
        ax1.legend(facecolor='#16213e', edgecolor='white', labelcolor='white')
        ax1.tick_params(colors='white')
        for spine in ax1.spines.values():
            spine.set_edgecolor('white')
    
    if calorie_data:
        dates = [d["date"][-5:] for d in calorie_data]
        logged = [d["logged"] for d in calorie_data]
        burned = [d["burned"] for d in calorie_data]
        goals = [d["goal"] for d in calorie_data]
        ax2.set_facecolor('#16213e')
        x = range(len(dates))
        width = 0.35
        ax2.bar([i - width/2 for i in x], logged, width, color='#ffa726', label='Потреблено', alpha=0.8)
        ax2.bar([i + width/2 for i in x], burned, width, color='#66bb6a', label='Сожжено', alpha=0.8)
        ax2.plot(dates, goals, color='#ff6b6b', marker='o', linestyle='--', label='Цель', linewidth=2)
        ax2.set_xlabel('Дата', color='white')
        ax2.set_ylabel('Калории (ккал)', color='white')
        ax2.set_title('🔥 Калории', color='white', fontsize=14)
        ax2.set_xticks(x)
        ax2.set_xticklabels(dates)
        ax2.legend(facecolor='#16213e', edgecolor='white', labelcolor='white')
        ax2.tick_params(colors='white')
        for spine in ax2.spines.values():
            spine.set_edgecolor('white')
    
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor='#1a1a2e', edgecolor='none', dpi=100)
    buf.seek(0)
    plt.close()
    
    from aiogram.types import BufferedInputFile
    photo = BufferedInputFile(buf.read(), filename="progress.png")
    await message.answer_photo(photo, caption="📊 Ваш прогресс за последние дни")


@router.message(Command("recommendations"))
async def cmd_recommendations(message: Message):
    logger.info(f"User {message.from_user.id} requesting recommendations")
    user_id = message.from_user.id
    user_data = get_user_data(user_id)
    
    recommendations = []
    water_percent = (user_data["logged_water"] / user_data["water_goal"]) * 100 if user_data["water_goal"] > 0 else 0
    if water_percent < 25:
        recommendations.append("💧 Вы выпили мало воды! Попробуйте пить по стакану каждый час.")
    elif water_percent < 50:
        recommendations.append("💧 Хорошо! Не забывайте пить воду регулярно.")
    elif water_percent >= 100:
        recommendations.append("💧 Отлично! Цель по воде достигнута! 🎉")
    
    cal_balance = user_data["logged_calories"] - user_data["burned_calories"]
    cal_percent = (cal_balance / user_data["calorie_goal"]) * 100 if user_data["calorie_goal"] > 0 else 0
    if cal_percent > 100:
        recommendations.append("🔥 Превышена норма калорий! Рекомендуем:\n   • Лёгкая тренировка (ходьба, йога)\n   • Низкокалорийные продукты на ужин")
    elif cal_percent > 80:
        recommendations.append("🔥 Вы почти у цели по калориям. Выбирайте лёгкие продукты.")
    elif cal_percent < 50:
        recommendations.append("🔥 Вы съели мало. Добавьте полезный перекус!")
    
    if user_data["burned_calories"] == 0:
        recommendations.append("🏃 Сегодня ещё не было тренировки! Рекомендуем:\n   • 30 мин ходьбы (~120 ккал)\n   • 20 мин йоги (~60 ккал)\n   • 15 мин бега (~150 ккал)")
    elif user_data["burned_calories"] > 500:
        recommendations.append("🏃 Отличная активность сегодня! Не забудьте восполнить воду.")
    
    low_cal_foods = ["🥒 Огурец (15 ккал/100г)", "🍅 Помидор (18 ккал/100г)", "🥬 Салат (14 ккал/100г)", "🍓 Клубника (32 ккал/100г)", "🍊 Апельсин (43 ккал/100г)"]
    recommendations.append("<b>🥗 Низкокалорийные продукты:</b>\n" + "\n".join(low_cal_foods))
    
    await message.answer("💡 <b>Рекомендации для вас:</b>\n\n" + "\n\n".join(recommendations), parse_mode=ParseMode.HTML)


async def main():
    logger.info("Starting bot...")
    router.message.middleware(LoggingMiddleware())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
