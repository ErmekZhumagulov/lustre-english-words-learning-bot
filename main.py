import telebot
from telebot import types
import logging
import sqlite3
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from pytz import timezone

BOT_TOKEN = "8397688765:AAGqeVGhMoBkYyTtTLzRb1hpgUeYaejU9B8"
DB_PATH = "words.db"

# === Интервалы напоминаний (в минутах) ===
REMINDER_INTERVALS = [
    1, 5, 20, 60, 180, 360, 720, 1440, 4320, 10080, 20160, 43200, 129600, 259200, 518400
]

scheduler = BackgroundScheduler(timezone=timezone("Asia/Bishkek"))
scheduler.start()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            english TEXT NOT NULL,
            russian TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def add_word_to_db(user_id, english, russian):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO words (user_id, english, russian, created_at)
        VALUES (?, ?, ?, ?)
    """, (user_id, english, russian, datetime.utcnow()))
    conn.commit()
    conn.close()


def get_words_from_db(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT english, russian FROM words WHERE user_id = ?
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def schedule_reminders(bot, user_id, english, russian):
    now = datetime.now(timezone("Asia/Bishkek"))
    for minutes in REMINDER_INTERVALS:
        remind_time = now + timedelta(minutes=minutes)
        scheduler.add_job(
            send_reminder,
            'date',
            run_date=remind_time,
            args=[bot, user_id, english, russian, minutes],
            id=f"{user_id}_{english}_{minutes}",
            misfire_grace_time=300  # 5 минут допустимого опоздания
        )


def send_reminder(bot, user_id, english, russian, minutes):
    bot.send_message(
        user_id,
        f"🔔 Напоминание ({minutes} мин):\n{english} — {russian}"
    )


def main():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    bot = telebot.TeleBot(BOT_TOKEN)
    user_temp_data = {}

    def main_menu():
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn1 = types.KeyboardButton("➕ Добавить слово")
        btn2 = types.KeyboardButton("📋 Список слов")
        btn3 = types.KeyboardButton("📊 Прогресс")
        btn4 = types.KeyboardButton("ℹ️ Помощь")
        markup.add(btn1, btn2)
        markup.add(btn3, btn4)
        return markup

    def confirmation_markup():
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(types.KeyboardButton("✅ Подтвердить"), types.KeyboardButton("❌ Отменить"))
        return markup

    @bot.message_handler(commands=["start"])
    def start(message):
        bot.send_message(message.chat.id, "👋 Привет! Я бот для изучения английских слов.\nВыбери действие в меню ниже.",
                         reply_markup=main_menu())

    @bot.message_handler(commands=["cancel"])
    def cancel(message):
        if message.chat.id in user_temp_data:
            user_temp_data.pop(message.chat.id)
            bot.send_message(message.chat.id, "❌ Добавление слова отменено.", reply_markup=main_menu())
        else:
            bot.send_message(message.chat.id, "ℹ️ Нет активных операций для отмены.", reply_markup=main_menu())

    @bot.message_handler(func=lambda msg: msg.text == "ℹ️ Помощь")
    def help_command(message):
        text = (
            "📌 Я помогу тебе учить английские слова по системе интервальных повторений.\n\n"
            "Каждое добавленное слово будет напоминаться через определённые интервалы:\n"
            "⏱ Через: 1 мин, 5 мин, 20 мин, 1 час, 3 часа, 6 часов, 12 часов, "
            "1 день, 3 дня, 7 дней, 14 дней, 30 дней, 90 дней, 180 дней, 360 дней.\n\n"
            "Используй кнопки:\n"
            "➕ Добавить слово — добавить новое слово\n"
            "📋 Список слов — посмотреть все слова\n"
            "📊 Прогресс — узнать свой прогресс\n"
            "ℹ️ Помощь — показать это сообщение\n\n"
            "Команда /cancel — отменить текущее добавление слова"
        )
        bot.send_message(message.chat.id, text, reply_markup=main_menu())

    @bot.message_handler(func=lambda msg: msg.text == "➕ Добавить слово")
    def add_word_step1(message):
        user_temp_data[message.chat.id] = {}
        bot.send_message(message.chat.id, "✍️ Введи слово на английском или напиши /cancel чтобы отменить:")
        bot.register_next_step_handler(message, add_word_step2)

    def add_word_step2(message):
        if message.text == "/cancel":
            cancel(message)
            return
        user_temp_data[message.chat.id]["english"] = message.text.strip()
        bot.send_message(message.chat.id, "✍️ Теперь введи перевод на русском или напиши /cancel чтобы отменить:")
        bot.register_next_step_handler(message, add_word_step3)

    def add_word_step3(message):
        if message.text == "/cancel":
            cancel(message)
            return
        user_temp_data[message.chat.id]["russian"] = message.text.strip()
        english = user_temp_data[message.chat.id]["english"]
        russian = user_temp_data[message.chat.id]["russian"]

        bot.send_message(
            message.chat.id,
            f"📌 Слово:\nАнглийский: {english}\nРусский: {russian}\n\nПодтверждаешь добавление?",
            reply_markup=confirmation_markup()
        )

    @bot.message_handler(func=lambda msg: msg.text in ["✅ Подтвердить", "❌ Отменить"])
    def confirm_word(message):
        if message.text == "✅ Подтвердить":
            english = user_temp_data[message.chat.id]["english"]
            russian = user_temp_data[message.chat.id]["russian"]
            add_word_to_db(message.chat.id, english, russian)
            schedule_reminders(bot, message.chat.id, english, russian)
            bot.send_message(message.chat.id, f"✅ Слово добавлено:\n{english} — {russian}", reply_markup=main_menu())
        else:
            bot.send_message(message.chat.id, "❌ Добавление слова отменено.", reply_markup=main_menu())

        user_temp_data.pop(message.chat.id, None)

    @bot.message_handler(func=lambda msg: msg.text == "📋 Список слов")
    def list_words(message):
        words = get_words_from_db(message.chat.id)
        if not words:
            bot.send_message(message.chat.id, "📭 У тебя пока нет слов.", reply_markup=main_menu())
            return
        text = "📋 Список слов:\n\n"
        for english, russian in words:
            text += f"🔹 {english} — {russian}\n"
        bot.send_message(message.chat.id, text, reply_markup=main_menu())

    logger.info("Бот запущен. Ожидание команд...")
    bot.infinity_polling()


if __name__ == '__main__':
    init_db()
    main()
